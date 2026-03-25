import pytest
from unittest.mock import patch, MagicMock
import requests

from alm.config import Endpoint
from alm.monitor import check_endpoint, detect_degradation


def make_endpoint(name="test-api", url="https://example.com", method="GET", threshold_ms=500):
    return Endpoint(name=name, url=url, method=method, threshold_ms=threshold_ms)


class TestCheckEndpoint:
    def test_successful_check_returns_correct_fields(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True

        with patch("alm.monitor.requests.request", return_value=mock_response) as mock_req:
            result = check_endpoint(make_endpoint())

        assert result["endpoint_name"] == "test-api"
        assert result["url"] == "https://example.com"
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["response_time_ms"] is not None
        assert isinstance(result["response_time_ms"], float)
        assert "timestamp" in result

    def test_successful_check_no_threshold_breach(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True

        with patch("alm.monitor.requests.request", return_value=mock_response):
            with patch("alm.monitor.time.perf_counter", side_effect=[0.0, 0.1]):
                result = check_endpoint(make_endpoint(threshold_ms=500))

        assert result["response_time_ms"] == pytest.approx(100.0)
        assert result["threshold_breached"] is False

    def test_threshold_breach_detected(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True

        with patch("alm.monitor.requests.request", return_value=mock_response):
            # perf_counter: start=0.0, end=0.8 => 800ms
            with patch("alm.monitor.time.perf_counter", side_effect=[0.0, 0.8]):
                result = check_endpoint(make_endpoint(threshold_ms=500))

        assert result["response_time_ms"] == pytest.approx(800.0)
        assert result["threshold_breached"] is True

    def test_timeout_all_retries_fail(self):
        with patch("alm.monitor.requests.request", side_effect=requests.Timeout):
            with patch("alm.monitor.time.sleep"):
                result = check_endpoint(make_endpoint(), max_retries=3)

        assert result["success"] is False
        assert result["response_time_ms"] is None
        assert result["status_code"] is None
        assert result["threshold_breached"] is False

    def test_connection_error_all_retries_fail(self):
        with patch("alm.monitor.requests.request", side_effect=requests.ConnectionError):
            with patch("alm.monitor.time.sleep"):
                result = check_endpoint(make_endpoint(), max_retries=3)

        assert result["success"] is False
        assert result["response_time_ms"] is None
        assert result["status_code"] is None

    def test_retry_succeeds_on_third_attempt(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True

        side_effects = [requests.Timeout, requests.ConnectionError, mock_response]

        with patch("alm.monitor.requests.request", side_effect=side_effects):
            with patch("alm.monitor.time.sleep"):
                result = check_endpoint(make_endpoint(), max_retries=3)

        assert result["success"] is True
        assert result["status_code"] == 200

    def test_retry_count_respected(self):
        """Ensure requests.request is called at most max_retries times."""
        with patch("alm.monitor.requests.request", side_effect=requests.Timeout) as mock_req:
            with patch("alm.monitor.time.sleep"):
                check_endpoint(make_endpoint(), max_retries=2)

        assert mock_req.call_count == 2

    def test_non_ok_http_response_is_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.ok = False

        with patch("alm.monitor.requests.request", return_value=mock_response):
            result = check_endpoint(make_endpoint())

        assert result["success"] is False
        assert result["status_code"] == 503

    def test_uses_correct_http_method(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True

        endpoint = make_endpoint(method="POST")
        with patch("alm.monitor.requests.request", return_value=mock_response) as mock_req:
            check_endpoint(endpoint)

        call_kwargs = mock_req.call_args
        assert call_kwargs[1]["method"] == "POST" or call_kwargs[0][0] == "POST"

    def test_passes_headers(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True

        endpoint = Endpoint(
            name="auth-api",
            url="https://example.com",
            headers={"Authorization": "Bearer token123"},
            threshold_ms=500,
        )
        with patch("alm.monitor.requests.request", return_value=mock_response) as mock_req:
            check_endpoint(endpoint)

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"] == {"Authorization": "Bearer token123"}

    def test_exponential_backoff_sleep_calls(self):
        """Verify sleep is called with exponential backoff: 1s, 2s on 2nd and 3rd attempts."""
        with patch("alm.monitor.requests.request", side_effect=requests.Timeout):
            with patch("alm.monitor.time.sleep") as mock_sleep:
                check_endpoint(make_endpoint(), max_retries=3)

        # First attempt has no sleep, 2nd attempt sleeps 1s, 3rd sleeps 2s
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2]


class TestDetectDegradation:
    def _make_checks(self, times, success=True):
        return [
            {"response_time_ms": t, "success": success}
            for t in times
        ]

    def test_returns_false_if_fewer_than_3_successful_checks(self):
        recent = self._make_checks([100.0, 200.0])
        assert detect_degradation("api", 500.0, recent) is False

    def test_returns_false_if_no_successful_checks(self):
        recent = [{"response_time_ms": 100.0, "success": False}] * 5
        assert detect_degradation("api", 500.0, recent) is False

    def test_degradation_detected_when_above_1_5x_rolling_avg(self):
        # avg = 100ms, threshold = 150ms; 160ms > 150ms => degraded
        recent = self._make_checks([100.0, 100.0, 100.0])
        assert detect_degradation("api", 160.0, recent) is True

    def test_no_degradation_when_within_1_5x_rolling_avg(self):
        # avg = 100ms; 140ms < 150ms => not degraded
        recent = self._make_checks([100.0, 100.0, 100.0])
        assert detect_degradation("api", 140.0, recent) is False

    def test_exactly_at_1_5x_is_not_degraded(self):
        # avg = 100ms; 150ms is NOT strictly greater than 150ms
        recent = self._make_checks([100.0, 100.0, 100.0])
        assert detect_degradation("api", 150.0, recent) is False

    def test_ignores_failed_checks_in_avg(self):
        # Only successful checks count. avg of [100, 100, 100] = 100ms
        failed = [{"response_time_ms": 1000.0, "success": False}] * 5
        successful = self._make_checks([100.0, 100.0, 100.0])
        recent = failed + successful
        assert detect_degradation("api", 160.0, recent) is True

    def test_ignores_none_response_times(self):
        recent = [
            {"response_time_ms": None, "success": True},
            {"response_time_ms": None, "success": True},
            {"response_time_ms": 100.0, "success": True},
            {"response_time_ms": 100.0, "success": True},
            {"response_time_ms": 100.0, "success": True},
        ]
        # avg of [100, 100, 100] = 100ms; 160ms > 150ms => degraded
        assert detect_degradation("api", 160.0, recent) is True

    def test_degradation_with_variable_history(self):
        # avg = (50+100+150+200+250)/5 = 150ms; threshold = 225ms; 300ms > 225ms => degraded
        recent = self._make_checks([50.0, 100.0, 150.0, 200.0, 250.0])
        assert detect_degradation("api", 300.0, recent) is True

    def test_no_degradation_with_variable_history(self):
        # avg = 150ms; threshold = 225ms; 220ms < 225ms => not degraded
        recent = self._make_checks([50.0, 100.0, 150.0, 200.0, 250.0])
        assert detect_degradation("api", 220.0, recent) is False
