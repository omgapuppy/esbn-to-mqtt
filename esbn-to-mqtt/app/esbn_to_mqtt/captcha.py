from __future__ import annotations

import time
from typing import Protocol

import httpx

from .models import CaptchaConfig


class CaptchaSolveError(RuntimeError):
    pass


class CaptchaSolver(Protocol):
    def solve_recaptcha_v2(self, *, website_url: str, site_key: str) -> str:
        pass


class TwoCaptchaSolver:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: int = 120,
        poll_interval_seconds: int = 5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._client = httpx.Client(
            base_url="https://api.2captcha.com",
            timeout=30.0,
            transport=transport,
        )

    def solve_recaptcha_v2(self, *, website_url: str, site_key: str) -> str:
        task_id = self._create_task(website_url=website_url, site_key=site_key)
        deadline = time.monotonic() + self._timeout_seconds

        while time.monotonic() <= deadline:
            payload = self._post_json(
                "/getTaskResult",
                {"clientKey": self._api_key, "taskId": task_id},
            )
            self._raise_for_api_error(payload, "getTaskResult")
            if payload.get("status") == "ready":
                solution = payload.get("solution")
                if not isinstance(solution, dict):
                    raise CaptchaSolveError("2Captcha returned a ready task without a solution")
                token = solution.get("gRecaptchaResponse")
                if not isinstance(token, str) or not token:
                    raise CaptchaSolveError("2Captcha returned an empty reCAPTCHA token")
                return token
            if payload.get("status") != "processing":
                raise CaptchaSolveError("2Captcha returned an unknown task status")
            if self._poll_interval_seconds > 0:
                time.sleep(self._poll_interval_seconds)

        raise CaptchaSolveError("2Captcha task timed out")

    def _create_task(self, *, website_url: str, site_key: str) -> int:
        payload = self._post_json(
            "/createTask",
            {
                "clientKey": self._api_key,
                "task": {
                    "type": "RecaptchaV2TaskProxyless",
                    "websiteURL": website_url,
                    "websiteKey": site_key,
                },
            },
        )
        self._raise_for_api_error(payload, "createTask")
        task_id = payload.get("taskId")
        if isinstance(task_id, bool) or not isinstance(task_id, int):
            raise CaptchaSolveError("2Captcha createTask response did not include taskId")
        integer_task_id: int = task_id
        return integer_task_id

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise CaptchaSolveError(f"2Captcha request failed: {exc}") from exc
        except ValueError as exc:
            raise CaptchaSolveError("2Captcha returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise CaptchaSolveError("2Captcha returned a non-object response")
        return data

    @staticmethod
    def _raise_for_api_error(payload: object, operation: str) -> None:
        if not isinstance(payload, dict):
            raise CaptchaSolveError(f"2Captcha {operation} returned a non-object response")
        error_id = payload.get("errorId", 0)
        if error_id == 0:
            return
        error_code = payload.get("errorCode")
        error_description = payload.get("errorDescription")
        if isinstance(error_code, str) and error_code:
            detail = error_code
        elif isinstance(error_description, str) and error_description:
            detail = error_description
        else:
            detail = str(error_id)
        raise CaptchaSolveError(f"2Captcha {operation} failed: {detail}")


def build_captcha_solver(config: CaptchaConfig) -> CaptchaSolver | None:
    if config.solver == "disabled":
        return None
    if config.solver == "2captcha" and config.two_captcha_api_key is not None:
        return TwoCaptchaSolver(
            config.two_captcha_api_key,
            timeout_seconds=config.two_captcha_timeout_seconds,
        )
    raise CaptchaSolveError("unsupported CAPTCHA solver configuration")
