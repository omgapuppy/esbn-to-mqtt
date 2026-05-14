from __future__ import annotations

import csv
import json
import re
from io import StringIO

import httpx
from bs4 import BeautifulSoup

from .models import EsbnCredentials

BASE_URL = "https://myaccount.esbnetworks.ie"
ROOT_URL = f"{BASE_URL}/"
LOGIN_BASE_URL = "https://login.esbnetworks.ie"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_CSV_BYTES = 10 * 1024 * 1024
SELF_ASSERTED_PATH = (
    "/esbntwkscustportalprdb2c01.onmicrosoft.com/"
    "B2C_1A_signup_signin/SelfAsserted"
)
CONFIRMED_PATH = (
    "/esbntwkscustportalprdb2c01.onmicrosoft.com/"
    "B2C_1A_signup_signin/api/CombinedSigninAndSignup/confirmed"
)


class EsbnError(RuntimeError):
    pass


class EsbnAuthenticationError(EsbnError):
    pass


class EsbnChallengeError(EsbnError):
    pass


class EsbnClient:
    def __init__(
        self,
        credentials: EsbnCredentials,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._confirmed_html = ""
        self._client = httpx.Client(
            base_url=BASE_URL,
            follow_redirects=True,
            timeout=60.0,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self._client.close()

    def download_30_min_kwh_hdf(self) -> str:
        settings = self._load_settings()
        self._submit_credentials(settings["csrf"], settings["transId"])
        self._confirm_sign_in(settings["csrf"], settings["transId"])
        self._complete_form_post()
        self._client.get(ROOT_URL)
        self._client.get(f"{BASE_URL}/Api/HistoricConsumption")
        token = self._load_xsrf_token()
        csv_response = self._download_csv(token)
        return self._validate_csv(csv_response)

    def _load_settings(self) -> dict[str, str]:
        response = self._client.get(ROOT_URL)
        self._ensure_success(response)
        match = re.search(r"var SETTINGS\s*=\s*(\{.*?\});", response.text, re.DOTALL)
        if match is None:
            raise EsbnAuthenticationError("ESBN settings not found on landing page")
        try:
            settings = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise EsbnAuthenticationError("ESBN settings were invalid") from exc

        csrf = settings.get("csrf")
        trans_id = settings.get("transId")
        if not isinstance(csrf, str) or not csrf or not isinstance(trans_id, str) or not trans_id:
            raise EsbnAuthenticationError("ESBN settings missing csrf or transId")
        return {"csrf": csrf, "transId": trans_id}

    def _submit_credentials(self, csrf: str, trans_id: str) -> None:
        url = (
            f"{LOGIN_BASE_URL}{SELF_ASSERTED_PATH}"
            f"?tx={trans_id}&p=B2C_1A_signup_signin"
        )
        response = self._client.post(
            url,
            data={
                "signInName": self._credentials.username,
                "password": self._credentials.password,
                "request_type": "RESPONSE",
            },
            headers={"x-csrf-token": csrf},
            follow_redirects=False,
        )
        self._ensure_success(response)

    def _confirm_sign_in(self, csrf: str, trans_id: str) -> None:
        response = self._client.get(
            f"{LOGIN_BASE_URL}{CONFIRMED_PATH}",
            params={
                "rememberMe": "false",
                "csrf_token": csrf,
                "tx": trans_id,
                "p": "B2C_1A_signup_signin",
            },
        )
        self._ensure_success(response)
        body = response.text.lower()
        if "g-recaptcha-response" in body or "captcha.html" in body or "not a robot" in body:
            raise EsbnChallengeError("ESBN sign in challenge detected")
        self._confirmed_html = response.text

    def _complete_form_post(self) -> None:
        soup = BeautifulSoup(self._confirmed_html, "html.parser")
        form = soup.find("form", id="auto")
        if form is None:
            raise EsbnAuthenticationError("ESBN confirmation form was not found")

        action = form.get("action")
        if not isinstance(action, str) or not action:
            raise EsbnAuthenticationError("ESBN confirmation form missing action")

        values: dict[str, str] = {}
        for name in ("state", "client_info", "code"):
            tag = form.find(attrs={"name": name})
            value = tag.get("value") if tag is not None else None
            if not isinstance(value, str) or not value:
                raise EsbnAuthenticationError(f"ESBN confirmation form missing {name}")
            values[name] = value

        response = self._client.post(
            action,
            data=values,
            follow_redirects=False,
        )
        if response.status_code not in {302, 303, 307, 308}:
            raise EsbnAuthenticationError("ESBN confirmation form post failed")
        location = response.headers.get("location")
        if not isinstance(location, str) or not location:
            raise EsbnAuthenticationError("ESBN confirmation form post failed")

        resolved_location = response.request.url.join(httpx.URL(location))
        if (
            resolved_location.scheme != "https"
            or resolved_location.host != "myaccount.esbnetworks.ie"
        ):
            raise EsbnAuthenticationError("ESBN confirmation form post failed")

    def _load_xsrf_token(self) -> str:
        response = self._client.get(f"{BASE_URL}/af/t")
        self._ensure_success(response)
        try:
            token = response.json()["token"]
        except (KeyError, json.JSONDecodeError, TypeError) as exc:
            raise EsbnAuthenticationError("ESBN XSRF token was not available") from exc
        if not isinstance(token, str) or not token:
            raise EsbnAuthenticationError("ESBN XSRF token was not available")
        return token

    def _download_csv(self, token: str) -> httpx.Response:
        return self._client.post(
            f"{BASE_URL}/DataHub/DownloadHdfPeriodic",
            json={
                "mprn": self._credentials.mprn,
                "searchType": "intervalkwh",
            },
            headers={"X-Xsrf-Token": token},
        )

    def _validate_csv(self, response: httpx.Response) -> str:
        self._ensure_success(response)
        content_type = response.headers.get("content-type", "").lower()
        body = response.content
        if len(body) > MAX_CSV_BYTES:
            raise EsbnError("ESBN CSV export exceeds 10 MiB")
        if "html" in content_type or body.lstrip().startswith(b"<"):
            raise EsbnError("ESBN export was HTML instead of CSV")

        try:
            text = body.decode(response.encoding or "utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EsbnError("ESBN export was not valid CSV text") from exc

        reader = csv.reader(StringIO(text))
        try:
            first_row = next(reader)
        except StopIteration as exc:
            raise EsbnError("ESBN export was empty or not CSV") from exc
        if len(first_row) < 2:
            raise EsbnError("ESBN export did not look like CSV")
        return text

    @staticmethod
    def _ensure_success(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EsbnError(f"ESBN request failed with {response.status_code}") from exc
