import pytest
from datetime import datetime, timezone, timedelta
from alm.storage import (
    init_db,
    save_check,
    get_recent_checks,
    get_all_endpoint_stats,
    get_endpoint_stats,
    clear_all,
    get_checks_since,
)


@pytest.fixture
def conn():
    """Provide an in-memory SQLite connection for each test."""
    connection = init_db(":memory:")
    yield connection
    connection.close()


def _ts(offset_minutes=0):
    """Return a UTC ISO timestamp offset by some minutes from now."""
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()


class TestInitDb:
    def test_creates_checks_table(self, conn):
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checks'")
        result = cursor.fetchone()
        assert result is not None, "checks table should exist after init_db"


class TestSaveCheck:
    def test_saves_successful_check(self, conn):
        save_check(
            conn=conn,
            endpoint_name="test-api",
            url="https://example.com",
            timestamp=_ts(),
            response_time_ms=123.4,
            status_code=200,
            success=True,
            threshold_breached=False,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM checks")
        count = cursor.fetchone()[0]
        assert count == 1

    def test_saves_failed_check(self, conn):
        save_check(
            conn=conn,
            endpoint_name="test-api",
            url="https://example.com",
            timestamp=_ts(),
            response_time_ms=None,
            status_code=None,
            success=False,
            threshold_breached=False,
        )
        rows = get_recent_checks(conn, "test-api")
        assert len(rows) == 1
        assert rows[0]["success"] == 0
        assert rows[0]["response_time_ms"] is None

    def test_saves_threshold_breached(self, conn):
        save_check(
            conn=conn,
            endpoint_name="slow-api",
            url="https://slow.example.com",
            timestamp=_ts(),
            response_time_ms=999.9,
            status_code=200,
            success=True,
            threshold_breached=True,
        )
        rows = get_recent_checks(conn, "slow-api")
        assert rows[0]["threshold_breached"] == 1


class TestGetRecentChecks:
    def test_returns_most_recent_first(self, conn):
        for i in range(5):
            save_check(
                conn=conn,
                endpoint_name="api",
                url="https://example.com",
                timestamp=_ts(offset_minutes=i),
                response_time_ms=100.0 + i,
                status_code=200,
                success=True,
                threshold_breached=False,
            )
        rows = get_recent_checks(conn, "api", limit=5)
        assert len(rows) == 5
        # Most recent should have the highest response time (4 minutes offset -> 104.0ms)
        assert rows[0]["response_time_ms"] == pytest.approx(104.0)

    def test_respects_limit(self, conn):
        for i in range(10):
            save_check(
                conn=conn,
                endpoint_name="api",
                url="https://example.com",
                timestamp=_ts(offset_minutes=i),
                response_time_ms=float(i),
                status_code=200,
                success=True,
                threshold_breached=False,
            )
        rows = get_recent_checks(conn, "api", limit=3)
        assert len(rows) == 3

    def test_filters_by_endpoint_name(self, conn):
        save_check(conn, "api-a", "https://a.com", _ts(), 100.0, 200, True, False)
        save_check(conn, "api-b", "https://b.com", _ts(), 200.0, 200, True, False)
        rows = get_recent_checks(conn, "api-a")
        assert all(r["endpoint_name"] == "api-a" for r in rows)

    def test_returns_empty_for_unknown_endpoint(self, conn):
        rows = get_recent_checks(conn, "nonexistent")
        assert rows == []


class TestGetAllEndpointStats:
    def test_basic_stats(self, conn):
        save_check(conn, "api", "https://example.com", _ts(), 100.0, 200, True, False)
        save_check(conn, "api", "https://example.com", _ts(), 200.0, 200, True, False)
        save_check(conn, "api", "https://example.com", _ts(), None, None, False, False)

        stats = get_all_endpoint_stats(conn)
        assert len(stats) == 1
        s = stats[0]
        assert s["endpoint_name"] == "api"
        assert s["total_checks"] == 3
        assert s["success_count"] == 2
        assert s["success_rate"] == pytest.approx(66.666, rel=1e-2)
        assert s["avg_ms"] == pytest.approx(150.0)
        assert s["min_ms"] == pytest.approx(100.0)
        assert s["max_ms"] == pytest.approx(200.0)
        assert s["breach_count"] == 0

    def test_breach_count(self, conn):
        save_check(conn, "api", "https://example.com", _ts(), 600.0, 200, True, True)
        save_check(conn, "api", "https://example.com", _ts(), 100.0, 200, True, False)
        stats = get_all_endpoint_stats(conn)
        assert stats[0]["breach_count"] == 1

    def test_multiple_endpoints(self, conn):
        save_check(conn, "api-a", "https://a.com", _ts(), 100.0, 200, True, False)
        save_check(conn, "api-b", "https://b.com", _ts(), 200.0, 200, True, False)
        stats = get_all_endpoint_stats(conn)
        names = {s["endpoint_name"] for s in stats}
        assert names == {"api-a", "api-b"}

    def test_empty_db_returns_empty_list(self, conn):
        stats = get_all_endpoint_stats(conn)
        assert stats == []

    def test_no_successful_checks_avg_is_none(self, conn):
        save_check(conn, "api", "https://example.com", _ts(), None, None, False, False)
        stats = get_all_endpoint_stats(conn)
        assert stats[0]["avg_ms"] is None
        assert stats[0]["min_ms"] is None
        assert stats[0]["max_ms"] is None


class TestGetEndpointStats:
    def test_returns_stats_for_endpoint(self, conn):
        save_check(conn, "api", "https://example.com", _ts(), 150.0, 200, True, False)
        stat = get_endpoint_stats(conn, "api")
        assert stat is not None
        assert stat["endpoint_name"] == "api"
        assert stat["total_checks"] == 1

    def test_returns_none_for_unknown(self, conn):
        result = get_endpoint_stats(conn, "nonexistent")
        assert result is None


class TestClearAll:
    def test_clears_all_rows(self, conn):
        save_check(conn, "api", "https://example.com", _ts(), 100.0, 200, True, False)
        save_check(conn, "api2", "https://example2.com", _ts(), 200.0, 200, True, False)
        clear_all(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM checks")
        count = cursor.fetchone()[0]
        assert count == 0

    def test_clear_idempotent_on_empty(self, conn):
        clear_all(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM checks")
        count = cursor.fetchone()[0]
        assert count == 0


class TestGetChecksSince:
    def test_filters_by_time(self, conn):
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()

        save_check(conn, "api", "https://example.com", old_ts, 100.0, 200, True, False)
        save_check(conn, "api", "https://example.com", recent_ts, 200.0, 200, True, False)

        rows = get_checks_since(conn, since_hours=1)
        assert len(rows) == 1
        assert rows[0]["response_time_ms"] == pytest.approx(200.0)

    def test_filters_by_endpoint_name(self, conn):
        recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        save_check(conn, "api-a", "https://a.com", recent_ts, 100.0, 200, True, False)
        save_check(conn, "api-b", "https://b.com", recent_ts, 200.0, 200, True, False)

        rows = get_checks_since(conn, since_hours=1, endpoint_name="api-a")
        assert len(rows) == 1
        assert rows[0]["endpoint_name"] == "api-a"

    def test_returns_all_recent_without_endpoint_filter(self, conn):
        recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        save_check(conn, "api-a", "https://a.com", recent_ts, 100.0, 200, True, False)
        save_check(conn, "api-b", "https://b.com", recent_ts, 200.0, 200, True, False)

        rows = get_checks_since(conn, since_hours=1)
        assert len(rows) == 2

    def test_returns_empty_when_no_recent_checks(self, conn):
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        save_check(conn, "api", "https://example.com", old_ts, 100.0, 200, True, False)

        rows = get_checks_since(conn, since_hours=1)
        assert rows == []
