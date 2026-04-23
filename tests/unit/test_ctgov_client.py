from unittest.mock import Mock, patch

import httpx
import pytest

from app.ingestion.ctgov_client import CTGovClient


def _response(status_code: int, *, json_body=None, headers=None, url="https://clinicaltrials.gov/api/v2/studies"):
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        headers=headers,
        request=httpx.Request("GET", url),
    )


@pytest.fixture
def client():
    client = CTGovClient()
    client._rate_limit_wait = Mock()
    return client


class TestFetchStudyRetries:
    def test_fetch_study_retries_retryable_status_and_succeeds(self, client):
        client._client.get = Mock(
            side_effect=[
                _response(503, json_body={"detail": "retry later"}),
                _response(200, json_body={"id": "ok"}),
            ]
        )

        with patch("app.ingestion.ctgov_client.time.sleep") as sleep:
            result = client.fetch_study("NCT00000001")

        assert result == {"id": "ok"}
        assert client._client.get.call_count == 2
        sleep.assert_called_once_with(1.0)

    def test_fetch_study_honors_retry_after_header(self, client):
        client._client.get = Mock(
            side_effect=[
                _response(429, json_body={"detail": "slow down"}, headers={"Retry-After": "7"}),
                _response(200, json_body={"id": "ok"}),
            ]
        )

        with patch("app.ingestion.ctgov_client.time.sleep") as sleep:
            result = client.fetch_study("NCT00000001")

        assert result == {"id": "ok"}
        sleep.assert_called_once_with(7.0)

    def test_fetch_study_raises_after_retry_budget_exhausted(self, client):
        client._client.get = Mock(side_effect=[_response(503), _response(503), _response(503)])

        with patch("app.ingestion.ctgov_client.time.sleep") as sleep:
            with pytest.raises(httpx.HTTPStatusError):
                client.fetch_study("NCT00000001")

        assert client._client.get.call_count == 3
        assert sleep.call_count == 2

    def test_fetch_study_retries_request_errors(self, client):
        client._client.get = Mock(
            side_effect=[
                httpx.ConnectError("boom"),
                _response(200, json_body={"id": "ok"}),
            ]
        )

        with patch("app.ingestion.ctgov_client.time.sleep") as sleep:
            result = client.fetch_study("NCT00000001")

        assert result == {"id": "ok"}
        assert client._client.get.call_count == 2
        sleep.assert_called_once_with(1.0)


class TestSearchStudies:
    def test_search_studies_returns_pagination_metadata(self, client):
        client._client.get = Mock(
            return_value=_response(
                200,
                json_body={
                    "studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}}}],
                    "totalCount": 17,
                    "nextPageToken": "cursor-2",
                },
            )
        )

        result = client.search_studies(condition="lung cancer", limit=5, page_token="cursor-1")

        assert result.studies == [{"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}}}]
        assert result.total_count == 17
        assert result.next_page_token == "cursor-2"
        client._client.get.assert_called_once()
        _, kwargs = client._client.get.call_args
        assert kwargs["params"]["query.cond"] == "lung cancer"
        assert kwargs["params"]["pageSize"] == 5
        assert kwargs["params"]["pageToken"] == "cursor-1"
        assert kwargs["params"]["countTotal"] == "true"

    def test_search_studies_translates_phase_to_supported_advanced_filter(self, client):
        client._client.get = Mock(
            return_value=_response(
                200,
                json_body={
                    "studies": [],
                    "totalCount": 0,
                },
            )
        )

        client.search_studies(condition="breast cancer", status="RECRUITING", phase="PHASE2", limit=2)

        client._client.get.assert_called_once()
        _, kwargs = client._client.get.call_args
        params = kwargs["params"]
        assert params["query.cond"] == "breast cancer"
        assert params["filter.overallStatus"] == "RECRUITING"
        assert params["filter.advanced"] == "AREA[Phase]PHASE2"
        assert "filter.phase" not in params
