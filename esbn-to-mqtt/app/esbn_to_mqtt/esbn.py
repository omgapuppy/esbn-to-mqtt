from __future__ import annotations

import csv
import json
import logging
import re
from http.cookiejar import LoadError, MozillaCookieJar
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .captcha import CaptchaSolveError, CaptchaSolver
from .models import EsbnCredentials

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://myaccount.esbnetworks.ie"
ROOT_URL = f"{BASE_URL}/"
LOGIN_BASE_URL = "https://login.esbnetworks.ie"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0"
BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}
AJAX_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-IE,en;q=0.9",
    "Origin": LOGIN_BASE_URL,
    "X-Requested-With": "XMLHttpRequest",
}
MAX_CSV_BYTES = 10 * 1024 * 1024
SELF_ASSERTED_PATH = (
    "/esbntwkscustportalprdb2c01.onmicrosoft.com/"
    "B2C_1A_signup_signin/SelfAsserted"
)
CONFIRMED_PATH = (
    "/esbntwkscustportalprdb2c01.onmicrosoft.com/"
    "B2C_1A_signup_signin/api/CombinedSigninAndSignup/confirmed"
)
CHALLENGE_MESSAGE = (
    "ESBN requested browser verification; automated login paused until next configured poll"
)


class EsbnError(RuntimeError):
    pass


class EsbnAuthenticationError(EsbnError):
    pass


class EsbnChallengeError(EsbnError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class EsbnClient:
    def __init__(
        self,
        credentials: EsbnCredentials,
        transport: httpx.BaseTransport | None = None,
        cookie_jar_path: Path | None = None,
        captcha_solver: CaptchaSolver | None = None,
    ) -> None:
        self._credentials = credentials
        self._confirmed_html = ""
        self._cookie_jar_path = cookie_jar_path
        self._captcha_solver = captcha_solver
        self._last_auth_path = "unknown"
        self._captcha_used = False
        self._cookie_jar = MozillaCookieJar(
            str(cookie_jar_path) if cookie_jar_path is not None else None
        )
        if cookie_jar_path is not None and cookie_jar_path.exists():
            try:
                self._cookie_jar.load(ignore_discard=True, ignore_expires=True)
            except (LoadError, OSError):
                self._cookie_jar.clear()

        self._client = httpx.Client(
            base_url=BASE_URL,
            follow_redirects=True,
            timeout=60.0,
            transport=transport,
            headers=BASE_HEADERS,
            cookies=self._cookie_jar,
        )

    def close(self) -> None:
        self._client.close()

    @property
    def last_auth_path(self) -> str:
        return self._last_auth_path

    @property
    def captcha_used(self) -> bool:
        return self._captcha_used

    def download_30_min_kwh_hdf(self) -> str:
        if (csv_content := self._download_with_existing_session()) is not None:
            self._save_cookies()
            return csv_content

        settings = self._load_settings()
        self._last_auth_path = "login"
        self._captcha_used = False
        self._submit_credentials(settings["csrf"], settings["transId"])
        self._confirm_sign_in(settings["csrf"], settings["transId"])
        self._complete_form_post()
        csv_content = self._download_authenticated_hdf(refresh_root=True)
        self._save_cookies()
        return csv_content

    def _download_with_existing_session(self) -> str | None:
        if not any(self._cookie_jar):
            return None

        response = self._client.get(ROOT_URL)
        self._ensure_success(response)
        if self._is_login_response(response):
            return None

        try:
            csv_content = self._download_authenticated_hdf(refresh_root=False)
            self._last_auth_path = "cookie"
            self._captcha_used = False
            return csv_content
        except EsbnAuthenticationError:
            return None

    def _download_authenticated_hdf(self, *, refresh_root: bool) -> str:
        if refresh_root:
            LOGGER.info("Refreshing ESBN portal session before HDF download")
            response = self._get(ROOT_URL, step="refresh portal session")
            self._ensure_success(response)
        LOGGER.info("Opening ESBN historic consumption page")
        self._get(f"{BASE_URL}/Api/HistoricConsumption", step="historic consumption page")
        token = self._load_xsrf_token()
        csv_response = self._download_csv(token)
        csv_content = self._validate_csv(csv_response)
        LOGGER.info("ESBN HDF export received")
        return csv_content

    def _save_cookies(self) -> None:
        if self._cookie_jar_path is None:
            return
        self._cookie_jar_path.parent.mkdir(parents=True, exist_ok=True)
        self._cookie_jar.save(
            str(self._cookie_jar_path),
            ignore_discard=True,
            ignore_expires=True,
        )
        self._cookie_jar_path.chmod(0o600)

    @staticmethod
    def _is_login_response(response: httpx.Response) -> bool:
        return (
            response.url.host == "login.esbnetworks.ie"
            or re.search(r"var SETTINGS\s*=", response.text) is not None
        )

    def _load_settings(self) -> dict[str, str]:
        response = self._client.get(ROOT_URL)
        self._ensure_success(response)
        return self._extract_settings(response.text)

    @staticmethod
    def _extract_settings(body: str) -> dict[str, str]:
        match = re.search(r"var SETTINGS\s*=\s*(\{.*?\});", body, re.DOTALL)
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
        string_settings = {
            key: value
            for key, value in settings.items()
            if isinstance(key, str) and isinstance(value, str)
        }
        string_settings["csrf"] = csrf
        string_settings["transId"] = trans_id
        return string_settings

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
            headers={**AJAX_HEADERS, "x-csrf-token": csrf},
            follow_redirects=False,
        )
        self._ensure_success(response)

    def _confirm_sign_in(self, csrf: str, trans_id: str) -> None:
        response = self._get_confirmed(csrf, trans_id)
        if self._is_challenge_body(response.text):
            response = self._solve_challenge_response(response)
        self._confirmed_html = response.text

    def _get_confirmed(self, csrf: str, trans_id: str) -> httpx.Response:
        response = self._get(
            f"{LOGIN_BASE_URL}{CONFIRMED_PATH}",
            step="sign-in confirmation",
            params={
                "rememberMe": "false",
                "csrf_token": csrf,
                "tx": trans_id,
                "p": "B2C_1A_signup_signin",
            },
        )
        self._ensure_success(response)
        return response

    @staticmethod
    def _is_challenge_body(body: str) -> bool:
        normalized = body.lower()
        return (
            "g-recaptcha-response" in normalized
            or "captcha.html" in normalized
            or "not a robot" in normalized
        )

    def _solve_challenge_response(self, response: httpx.Response) -> httpx.Response:
        if self._captcha_solver is None:
            raise EsbnChallengeError(CHALLENGE_MESSAGE)

        self._last_auth_path = "login+captcha"
        self._captcha_used = True
        settings = self._extract_settings(response.text)
        claim_id = self._extract_captcha_claim_id(response.text)
        site_key = self._extract_recaptcha_site_key(response.text, settings)
        LOGGER.info("ESBN CAPTCHA challenge detected; requesting 2Captcha solution")
        try:
            captcha_token = self._captcha_solver.solve_recaptcha_v2(
                website_url=str(response.url),
                site_key=site_key,
            )
        except CaptchaSolveError as exc:
            raise EsbnChallengeError(f"ESBN CAPTCHA solve failed: {exc}") from exc

        self._submit_captcha_token(settings["csrf"], settings["transId"], claim_id, captcha_token)
        LOGGER.info("2Captcha solution submitted to ESBN")
        LOGGER.info("Requesting ESBN confirmation after CAPTCHA")
        confirmed_response = self._get_confirmed(settings["csrf"], settings["transId"])
        LOGGER.info("ESBN confirmation response received after CAPTCHA")
        if self._is_challenge_body(confirmed_response.text):
            raise EsbnChallengeError("ESBN CAPTCHA challenge remained after solver response")
        return confirmed_response

    def _submit_captcha_token(
        self,
        csrf: str,
        trans_id: str,
        claim_id: str,
        captcha_token: str,
    ) -> None:
        response = self._post(
            f"{LOGIN_BASE_URL}{SELF_ASSERTED_PATH}?tx={trans_id}&p=B2C_1A_signup_signin",
            step="CAPTCHA token submission",
            data={
                claim_id: captcha_token,
                "request_type": "RESPONSE",
            },
            headers={**AJAX_HEADERS, "x-csrf-token": csrf},
            follow_redirects=False,
        )
        self._ensure_success(response)

    def _extract_recaptcha_site_key(self, body: str, settings: dict[str, str]) -> str:
        site_key = self._find_recaptcha_site_key(body)
        if site_key is not None:
            return site_key

        remote_resource = settings.get("remoteResource")
        if not isinstance(remote_resource, str) or not remote_resource:
            raise EsbnAuthenticationError("ESBN CAPTCHA page did not expose a site key")

        template_response = self._client.get(remote_resource)
        self._ensure_success(template_response)
        site_key = self._find_recaptcha_site_key(template_response.text)
        if site_key is not None:
            return site_key

        for script_url in self._extract_script_urls(template_response.text, remote_resource):
            script_response = self._client.get(script_url)
            self._ensure_success(script_response)
            site_key = self._find_recaptcha_site_key(script_response.text)
            if site_key is not None:
                return site_key

        raise EsbnAuthenticationError("ESBN CAPTCHA page did not expose a site key")

    @staticmethod
    def _find_recaptcha_site_key(body: str) -> str | None:
        patterns = [
            r"sitekey\s*:\s*['\"]([^'\"]+)['\"]",
            r"data-sitekey\s*=\s*['\"]([^'\"]+)['\"]",
        ]
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match is not None:
                return match.group(1)
        return None

    @staticmethod
    def _extract_script_urls(body: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(body, "html.parser")
        urls: list[str] = []
        for script in soup.find_all("script"):
            source = script.get("src")
            if isinstance(source, str) and source:
                urls.append(str(httpx.URL(base_url).join(source)))
        urls.extend(
            match.group(1)
            for match in re.finditer(r"import\s+[^'\"]*['\"]([^'\"]+)['\"]", body)
        )
        return urls

    @staticmethod
    def _extract_captcha_claim_id(body: str) -> str:
        match = re.search(r"var SA_FIELDS\s*=\s*(\{.*?\});", body, re.DOTALL)
        if match is None:
            return "g-recaptcha-response-toms"
        try:
            fields = json.loads(match.group(1))
        except json.JSONDecodeError:
            return "g-recaptcha-response-toms"
        attribute_fields = fields.get("AttributeFields")
        if not isinstance(attribute_fields, list):
            return "g-recaptcha-response-toms"
        for field in attribute_fields:
            if not isinstance(field, dict):
                continue
            field_id = field.get("ID")
            if isinstance(field_id, str) and "recaptcha" in field_id.lower():
                return field_id
        return "g-recaptcha-response-toms"

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

        LOGGER.info("Posting ESBN confirmation form")
        response = self._post(
            action,
            step="confirmation form post",
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
        LOGGER.info("ESBN confirmation form accepted")

    def _load_xsrf_token(self) -> str:
        response = self._get(f"{BASE_URL}/af/t", step="XSRF token")
        self._ensure_success(response)
        try:
            token = response.json()["token"]
        except (KeyError, json.JSONDecodeError, TypeError) as exc:
            raise EsbnAuthenticationError("ESBN XSRF token was not available") from exc
        if not isinstance(token, str) or not token:
            raise EsbnAuthenticationError("ESBN XSRF token was not available")
        return token

    def _download_csv(self, token: str) -> httpx.Response:
        LOGGER.info("Downloading ESBN HDF export")
        return self._post(
            f"{BASE_URL}/DataHub/DownloadHdfPeriodic",
            step="HDF export download",
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

    def _get(self, url: str, *, step: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.get(url, **kwargs)
        except httpx.TimeoutException as exc:
            raise EsbnError(f"ESBN request timed out during {step}") from exc
        except httpx.RequestError as exc:
            raise EsbnError(f"ESBN request failed during {step}: {exc.__class__.__name__}") from exc

    def _post(self, url: str, *, step: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.post(url, **kwargs)
        except httpx.TimeoutException as exc:
            raise EsbnError(f"ESBN request timed out during {step}") from exc
        except httpx.RequestError as exc:
            raise EsbnError(f"ESBN request failed during {step}: {exc.__class__.__name__}") from exc

    @staticmethod
    def _ensure_success(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EsbnError(f"ESBN request failed with {response.status_code}") from exc
