from __future__ import annotations

import json

import httpx
import pytest
from esbn_to_mqtt.captcha import CaptchaSolveError, TwoCaptchaSolver


def test_two_captcha_solver_returns_recaptcha_token_after_polling() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if str(request.url) == "https://api.2captcha.com/createTask":
            assert payload == {
                "clientKey": "api-key",
                "task": {
                    "type": "RecaptchaV2TaskProxyless",
                    "websiteURL": "https://login.esbnetworks.ie/challenge",
                    "websiteKey": "site-key",
                },
            }
            return httpx.Response(200, json={"errorId": 0, "taskId": 123})
        if str(request.url) == "https://api.2captcha.com/getTaskResult":
            assert payload == {"clientKey": "api-key", "taskId": 123}
            if len(requests) == 2:
                return httpx.Response(200, json={"errorId": 0, "status": "processing"})
            return httpx.Response(
                200,
                json={
                    "errorId": 0,
                    "status": "ready",
                    "solution": {"gRecaptchaResponse": "captcha-token"},
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    solver = TwoCaptchaSolver(
        "api-key",
        timeout_seconds=30,
        poll_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    token = solver.solve_recaptcha_v2(
        website_url="https://login.esbnetworks.ie/challenge",
        site_key="site-key",
    )

    assert token == "captcha-token"


def test_two_captcha_solver_raises_on_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "errorId": 1,
                "errorCode": "ERROR_ZERO_BALANCE",
                "errorDescription": "Zero balance",
            },
        )

    solver = TwoCaptchaSolver(
        "api-key",
        timeout_seconds=30,
        poll_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CaptchaSolveError, match="ERROR_ZERO_BALANCE"):
        solver.solve_recaptcha_v2(
            website_url="https://login.esbnetworks.ie/challenge",
            site_key="site-key",
        )


def test_two_captcha_solver_raises_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://api.2captcha.com/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 123})
        return httpx.Response(200, json={"errorId": 0, "status": "processing"})

    solver = TwoCaptchaSolver(
        "api-key",
        timeout_seconds=0,
        poll_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CaptchaSolveError, match="timed out"):
        solver.solve_recaptcha_v2(
            website_url="https://login.esbnetworks.ie/challenge",
            site_key="site-key",
        )
