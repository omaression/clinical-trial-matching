import time

import httpx

from app.config import settings


class CTGovClient:
    """ClinicalTrials.gov V2 API client with rate limiting."""

    def __init__(self):
        self._base_url = settings.ctgov_base_url
        self._rate_limit = settings.ctgov_rate_limit
        self._last_request = 0.0
        self._client = httpx.Client(timeout=30.0)

    def fetch_study(self, nct_id: str) -> dict:
        self._rate_limit_wait()
        response = self._client.get(f"{self._base_url}/studies/{nct_id}")
        response.raise_for_status()
        return response.json()

    def search_studies(self, condition: str | None = None, status: str | None = None,
                       phase: str | None = None, limit: int = 25) -> list[dict]:
        self._rate_limit_wait()
        params: dict = {"pageSize": limit}
        if condition:
            params["query.cond"] = condition
        if status:
            params["filter.overallStatus"] = status
        if phase:
            params["filter.phase"] = phase
        response = self._client.get(f"{self._base_url}/studies", params=params)
        response.raise_for_status()
        return response.json().get("studies", [])

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_request
        wait = (1.0 / self._rate_limit) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()
