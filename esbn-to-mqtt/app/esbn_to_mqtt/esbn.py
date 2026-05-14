from __future__ import annotations

import httpx

from .models import EsbnCredentials

BASE_URL = "https://myaccount.esbnetworks.ie"


class EsbnError(RuntimeError):
    pass


class EsbnAuthenticationError(EsbnError):
    pass


class EsbnChallengeError(EsbnError):
    pass


class EsbnClient:
    def __init__(self, credentials: EsbnCredentials) -> None:
        self._credentials = credentials
        self._client = httpx.Client(
            base_url=BASE_URL,
            follow_redirects=True,
            timeout=60.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )

    def close(self) -> None:
        self._client.close()

    def download_30_min_kwh_hdf(self) -> str:
        raise EsbnError(
            "ESBN live download is not implemented until a current authenticated export "
            "flow is captured locally and encoded without secrets"
        )
