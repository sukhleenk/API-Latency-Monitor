import sqlite3
from datetime import datetime, timedelta, timezone


def init_db(db_path="alm_data.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_name TEXT NOT NULL,
            url TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            response_time_ms REAL,
            status_code INTEGER,
            success BOOLEAN NOT NULL,
            threshold_breached BOOLEAN NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_check(conn, endpoint_name, url, timestamp, response_time_ms, status_code, success, threshold_breached):
    conn.execute(
        """
        INSERT INTO checks
            (endpoint_name, url, timestamp, response_time_ms, status_code, success, threshold_breached)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (endpoint_name, url, timestamp, response_time_ms, status_code,
         int(bool(success)), int(bool(threshold_breached)))
    )
    conn.commit()


def get_recent_checks(conn, endpoint_name, limit=10):
    rows = conn.execute(
        """
        SELECT * FROM checks
        WHERE endpoint_name = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (endpoint_name, limit)
    ).fetchall()
    return [dict(row) for row in rows]


def get_all_endpoint_stats(conn):
    rows = conn.execute(
        """
        SELECT
            endpoint_name,
            COUNT(*) AS total_checks,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS success_count,
            AVG(response_time_ms) AS avg_ms,
            MIN(response_time_ms) AS min_ms,
            MAX(response_time_ms) AS max_ms,
            SUM(CASE WHEN threshold_breached = 1 THEN 1 ELSE 0 END) AS breach_count
        FROM checks
        GROUP BY endpoint_name
        ORDER BY endpoint_name
        """
    ).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        total = d["total_checks"] or 0
        d["success_rate"] = (d["success_count"] / total * 100.0) if total > 0 else 0.0
        results.append(d)
    return results


def get_endpoint_stats(conn, endpoint_name):
    row = conn.execute(
        """
        SELECT
            endpoint_name,
            COUNT(*) AS total_checks,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS success_count,
            AVG(response_time_ms) AS avg_ms,
            MIN(response_time_ms) AS min_ms,
            MAX(response_time_ms) AS max_ms,
            SUM(CASE WHEN threshold_breached = 1 THEN 1 ELSE 0 END) AS breach_count
        FROM checks
        WHERE endpoint_name = ?
        GROUP BY endpoint_name
        """,
        (endpoint_name,)
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    total = d["total_checks"] or 0
    d["success_rate"] = (d["success_count"] / total * 100.0) if total > 0 else 0.0
    return d


def clear_all(conn):
    conn.execute("DELETE FROM checks")
    conn.commit()


def get_checks_since(conn, since_hours, endpoint_name=None):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    if endpoint_name:
        rows = conn.execute(
            """
            SELECT * FROM checks
            WHERE timestamp >= ? AND endpoint_name = ?
            ORDER BY timestamp DESC
            """,
            (cutoff, endpoint_name)
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM checks
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (cutoff,)
        ).fetchall()
    return [dict(row) for row in rows]
