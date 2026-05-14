from __future__ import annotations

import json
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from esbn_to_mqtt.esbn import (
    EsbnAuthenticationError,
    EsbnChallengeError,
    EsbnClient,
    EsbnError,
)
from esbn_to_mqtt.models import EsbnCredentials


def _credentials() -> EsbnCredentials:
    return EsbnCredentials(
        username="esbn-user",
        password="esbn-pass",
        mprn="12345678901",
    )


def _html_response(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, text=content, headers={"content-type": "text/html"})


def _csv_response(content: str) -> httpx.Response:
    return httpx.Response(status_code=200, text=content, headers={"content-type": "text/csv"})


def _write_session_cookie(path: Path) -> None:
    jar = MozillaCookieJar(str(path))
    jar.set_cookie(
        Cookie(
            version=0,
            name="session",
            value="abc",
            port=None,
            port_specified=False,
            domain="myaccount.esbnetworks.ie",
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": None},
            rfc2109=False,
        )
    )
    jar.save(ignore_discard=True, ignore_expires=True)


def test_download_30_min_kwh_hdf_performs_live_login_and_download_flow(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []
    login_root_gets = 0
    cookie_path = tmp_path / "esbn-cookies.txt"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_root_gets
        requests.append(request)
        url = str(request.url)

        if url == "https://myaccount.esbnetworks.ie/":
            assert request.method == "GET"
            assert request.headers["user-agent"].startswith("Mozilla/5.0")
            if login_root_gets == 0:
                login_root_gets += 1
                return _html_response(
                    """
                    <html><head><script>
                    var SETTINGS = {"csrf":"csrf-token","transId":"trans-id"};
                    </script></head><body>ok</body></html>
                    """
                )
            if login_root_gets == 1:
                login_root_gets += 1
                return httpx.Response(
                    200,
                    text="<html><body>portal</body></html>",
                    headers={
                        "content-type": "text/html",
                        "set-cookie": "session=abc; Path=/; Secure; HttpOnly",
                    },
                )
            raise AssertionError("unexpected extra root GET")

        if url.startswith(
            "https://login.esbnetworks.ie/esbntwkscustportalprdb2c01.onmicrosoft.com/"
        ) and "SelfAsserted" in url:
            assert request.method == "POST"
            assert request.headers["x-csrf-token"] == "csrf-token"
            body = parse_qs(request.content.decode())
            assert body == {
                "signInName": ["esbn-user"],
                "password": ["esbn-pass"],
                "request_type": ["RESPONSE"],
            }
            assert "tx=trans-id" in url
            return _html_response("signed in")

        if url == (
            "https://login.esbnetworks.ie/"
            "esbntwkscustportalprdb2c01.onmicrosoft.com/"
            "B2C_1A_signup_signin/api/CombinedSigninAndSignup/confirmed"
            "?rememberMe=false&csrf_token=csrf-token&tx=trans-id&p=B2C_1A_signup_signin"
        ):
            assert request.method == "GET"
            return _html_response(
                """
                <html><body>
                <form id="auto" action="https://login.esbnetworks.ie/continue">
                    <input name="state" value="state-token">
                    <input name="client_info" value="client-info-token">
                    <input name="code" value="code-token">
                </form>
                </body></html>
                """
            )

        if url == "https://login.esbnetworks.ie/continue":
            assert request.method == "POST"
            assert request.headers.get("accept") is not None
            assert request.content == (
                b"state=state-token&client_info=client-info-token&code=code-token"
            )
            return httpx.Response(302, headers={"location": "https://myaccount.esbnetworks.ie/"})

        if url == "https://myaccount.esbnetworks.ie/Api/HistoricConsumption":
            assert request.method == "GET"
            return _html_response("<html><body>historic</body></html>")

        if url == "https://myaccount.esbnetworks.ie/af/t":
            assert request.method == "GET"
            return httpx.Response(200, json={"token": "xsrf-token"})

        if url == "https://myaccount.esbnetworks.ie/DataHub/DownloadHdfPeriodic":
            assert request.method == "POST"
            assert request.headers["x-xsrf-token"] == "xsrf-token"
            assert json.loads(request.content) == {
                "mprn": "12345678901",
                "searchType": "intervalkwh",
            }
            return _csv_response("Read Date and End Time,Import kWh\n2026-05-12 00:30,0.123\n")

        raise AssertionError(f"unexpected request: {request.method} {url}")

    client = EsbnClient(
        _credentials(),
        transport=httpx.MockTransport(handler),
        cookie_jar_path=cookie_path,
    )
    try:
        csv_content = client.download_30_min_kwh_hdf()
    finally:
        client.close()

    assert csv_content.startswith("Read Date and End Time")
    assert "session" in cookie_path.read_text(encoding="utf-8")
    assert [str(request.url) for request in requests] == [
        "https://myaccount.esbnetworks.ie/",
        "https://login.esbnetworks.ie/"
        "esbntwkscustportalprdb2c01.onmicrosoft.com/"
        "B2C_1A_signup_signin/SelfAsserted?tx=trans-id&p=B2C_1A_signup_signin",
        "https://login.esbnetworks.ie/"
        "esbntwkscustportalprdb2c01.onmicrosoft.com/"
        "B2C_1A_signup_signin/api/CombinedSigninAndSignup/confirmed"
        "?rememberMe=false&csrf_token=csrf-token&tx=trans-id&p=B2C_1A_signup_signin",
        "https://login.esbnetworks.ie/continue",
        "https://myaccount.esbnetworks.ie/",
        "https://myaccount.esbnetworks.ie/Api/HistoricConsumption",
        "https://myaccount.esbnetworks.ie/af/t",
        "https://myaccount.esbnetworks.ie/DataHub/DownloadHdfPeriodic",
    ]


def test_download_30_min_kwh_hdf_uses_persisted_session_cookie(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []
    cookie_path = tmp_path / "esbn-cookies.txt"
    _write_session_cookie(cookie_path)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        if request.url.host == "login.esbnetworks.ie":
            raise AssertionError("persisted session should avoid login")
        if url == "https://myaccount.esbnetworks.ie/":
            assert "session=abc" in request.headers.get("cookie", "")
            return _html_response("<html><body>portal</body></html>")
        if url == "https://myaccount.esbnetworks.ie/Api/HistoricConsumption":
            return _html_response("<html><body>historic</body></html>")
        if url == "https://myaccount.esbnetworks.ie/af/t":
            return httpx.Response(200, json={"token": "xsrf-token"})
        if url == "https://myaccount.esbnetworks.ie/DataHub/DownloadHdfPeriodic":
            return _csv_response("Read Date and End Time,Import kWh\n2026-05-12 00:30,0.123\n")
        raise AssertionError(f"unexpected request: {request.method} {url}")

    client = EsbnClient(
        _credentials(),
        transport=httpx.MockTransport(handler),
        cookie_jar_path=cookie_path,
    )
    try:
        csv_content = client.download_30_min_kwh_hdf()
    finally:
        client.close()

    assert csv_content.startswith("Read Date and End Time")
    assert [str(request.url) for request in requests] == [
        "https://myaccount.esbnetworks.ie/",
        "https://myaccount.esbnetworks.ie/Api/HistoricConsumption",
        "https://myaccount.esbnetworks.ie/af/t",
        "https://myaccount.esbnetworks.ie/DataHub/DownloadHdfPeriodic",
    ]


def test_download_30_min_kwh_hdf_raises_on_challenge_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://myaccount.esbnetworks.ie/":
            return _html_response(
                """
                <html><body>var SETTINGS = {"csrf":"csrf-token","transId":"trans-id"};</body></html>
                """
            )
        if "SelfAsserted" in str(request.url):
            return _html_response("signed in")
        if "confirmed" in str(request.url):
            return _html_response("<html><body>not a robot captcha.html</body></html>")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = EsbnClient(_credentials(), transport=httpx.MockTransport(handler))
    with pytest.raises(EsbnChallengeError, match="browser verification"):
        client.download_30_min_kwh_hdf()
    client.close()


def test_download_30_min_kwh_hdf_rejects_missing_settings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://myaccount.esbnetworks.ie/":
            return _html_response("<html><body>no settings here</body></html>")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = EsbnClient(_credentials(), transport=httpx.MockTransport(handler))
    with pytest.raises(EsbnAuthenticationError, match="settings"):
        client.download_30_min_kwh_hdf()
    client.close()


def test_download_30_min_kwh_hdf_rejects_non_csv_download() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://myaccount.esbnetworks.ie/":
            return _html_response(
                '<html><script>var SETTINGS = '
                '{"csrf":"csrf-token","transId":"trans-id"};</script></html>'
            )
        if "SelfAsserted" in url:
            return _html_response("signed in")
        if "confirmed" in url:
            return _html_response(
                '<html><form id="auto" action="https://login.esbnetworks.ie/continue">'
                '<input name="state" value="state-token">'
                '<input name="client_info" value="client-info-token">'
                '<input name="code" value="code-token">'
                "</form></html>"
            )
        if url == "https://login.esbnetworks.ie/continue":
            return httpx.Response(302, headers={"location": "https://myaccount.esbnetworks.ie/"})
        if url == "https://myaccount.esbnetworks.ie/":
            return _html_response("<html><body>portal</body></html>")
        if url == "https://myaccount.esbnetworks.ie/Api/HistoricConsumption":
            return _html_response("<html><body>historic</body></html>")
        if url == "https://myaccount.esbnetworks.ie/af/t":
            return httpx.Response(200, json={"token": "xsrf-token"})
        if url == "https://myaccount.esbnetworks.ie/DataHub/DownloadHdfPeriodic":
            return _html_response("<html><body>export unavailable</body></html>")
        raise AssertionError(f"unexpected request: {request.method} {url}")

    client = EsbnClient(_credentials(), transport=httpx.MockTransport(handler))
    with pytest.raises(EsbnError, match="CSV"):
        client.download_30_min_kwh_hdf()
    client.close()


def test_download_30_min_kwh_hdf_rejects_non_redirect_confirm_post() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://myaccount.esbnetworks.ie/":
            return _html_response(
                '<html><script>var SETTINGS = '
                '{"csrf":"csrf-token","transId":"trans-id"};</script></html>'
            )
        if "SelfAsserted" in url:
            return _html_response("signed in")
        if "confirmed" in url:
            return _html_response(
                '<html><form id="auto" action="https://login.esbnetworks.ie/continue">'
                '<input name="state" value="state-token">'
                '<input name="client_info" value="client-info-token">'
                '<input name="code" value="code-token">'
                "</form></html>"
            )
        if url == "https://login.esbnetworks.ie/continue":
            return _html_response("<html><body>not redirected</body></html>")
        raise AssertionError(f"unexpected request: {request.method} {url}")

    client = EsbnClient(_credentials(), transport=httpx.MockTransport(handler))
    with pytest.raises(EsbnAuthenticationError, match="confirmation form post failed"):
        client.download_30_min_kwh_hdf()
    client.close()
