import time
from dataclasses import dataclass

import httpx

from app.config import settings

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _phase_advanced_filter(phase: str) -> str:
    return f"AREA[Phase]{phase}"


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
        self._max_retries = settings.ctgov_max_retries
        self._retry_backoff_seconds = settings.ctgov_retry_backoff_seconds
        self._last_request = 0.0
        self._client = httpx.Client(timeout=30.0)

    def fetch_study(self, nct_id: str) -> dict:
        return self._get_json(f"{self._base_url}/studies/{nct_id}")

    def search_studies(self, condition: str | None = None, status: str | None = None,
                       phase: str | None = None, limit: int = 25,
                       page_token: str | None = None) -> SearchStudiesResult:
        params: dict = {"pageSize": limit, "countTotal": "true"}
        if condition:
            params["query.cond"] = condition
        if status:
            params["filter.overallStatus"] = status
        if phase:
            params["filter.advanced"] = _phase_advanced_filter(phase)
        if page_token:
            params["pageToken"] = page_token
        payload = self._get_json(f"{self._base_url}/studies", params=params)
        total_count = payload.get("totalCount")
        return SearchStudiesResult(
            studies=payload.get("studies", []),
            total_count=int(total_count) if total_count is not None else None,
            next_page_token=payload.get("nextPageToken"),
        )

    def _get_json(self, url: str, params: dict | None = None) -> dict:
        for attempt in range(self._max_retries + 1):
            self._rate_limit_wait()
            try:
                response = self._client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_STATUS_CODES or attempt == self._max_retries:
                    raise
                self._retry_wait(attempt, exc.response)
            except httpx.RequestError:
                if attempt == self._max_retries:
                    raise
                self._retry_wait(attempt)

        raise RuntimeError("ClinicalTrials.gov request retries exhausted without raising")

    def _retry_wait(self, attempt: int, response: httpx.Response | None = None) -> None:
        retry_after = response.headers.get("Retry-After") if response else None
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = self._retry_backoff_seconds * (2 ** attempt)
        else:
            delay = self._retry_backoff_seconds * (2 ** attempt)
        time.sleep(delay)

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_request
        wait = (1.0 / self._rate_limit) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()
