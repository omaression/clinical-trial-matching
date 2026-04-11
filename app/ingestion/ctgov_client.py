import time
from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass
class SearchStudiesResult:
    studies: list[dict]
    total_count: int | None = None
    next_page_token: str | None = None


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
                       phase: str | None = None, limit: int = 25,
                       page_token: str | None = None) -> SearchStudiesResult:
        self._rate_limit_wait()
        params: dict = {"pageSize": limit, "countTotal": "true"}
        if condition:
            params["query.cond"] = condition
        if status:
            params["filter.overallStatus"] = status
        if phase:
            params["filter.phase"] = phase
        if page_token:
            params["pageToken"] = page_token
        response = self._client.get(f"{self._base_url}/studies", params=params)
        response.raise_for_status()
        payload = response.json()
        total_count = payload.get("totalCount")
        return SearchStudiesResult(
            studies=payload.get("studies", []),
            total_count=int(total_count) if total_count is not None else None,
            next_page_token=payload.get("nextPageToken"),
        )

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_request
        wait = (1.0 / self._rate_limit) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()
