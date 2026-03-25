import pytest
import csv
import io
import os
import tempfile
from io import StringIO

from rich.console import Console

from alm.report import status_label, print_report, export_csv


class TestStatusLabel:
    def test_healthy_when_100_percent_success_no_breaches(self):
        label, style = status_label(success_rate=100.0, breach_count=0, total_checks=10)
        assert label == "HEALTHY"
        assert style == "green"

    def test_healthy_when_above_80_percent_no_breaches(self):
        label, style = status_label(success_rate=90.0, breach_count=0, total_checks=10)
        assert label == "HEALTHY"
        assert style == "green"

    def test_healthy_exactly_80_percent_no_breaches(self):
        label, style = status_label(success_rate=80.0, breach_count=0, total_checks=10)
        assert label == "HEALTHY"
        assert style == "green"

    def test_down_when_below_80_percent_success(self):
        label, style = status_label(success_rate=79.9, breach_count=0, total_checks=10)
        assert label == "DOWN"
        assert style == "red"

    def test_down_when_0_percent_success(self):
        label, style = status_label(success_rate=0.0, breach_count=0, total_checks=5)
        assert label == "DOWN"
        assert style == "red"

    def test_degraded_when_breach_count_above_zero(self):
        label, style = status_label(success_rate=100.0, breach_count=1, total_checks=10)
        assert label == "DEGRADED"
        assert style == "yellow"

    def test_degraded_when_multiple_breaches(self):
        label, style = status_label(success_rate=95.0, breach_count=5, total_checks=10)
        assert label == "DEGRADED"
        assert style == "yellow"

    def test_down_takes_priority_over_degraded(self):
        # success_rate < 80% should return DOWN even if there are breaches
        label, style = status_label(success_rate=50.0, breach_count=3, total_checks=10)
        assert label == "DOWN"
        assert style == "red"

    def test_zero_checks(self):
        # 0 checks => success_rate = 0.0 => DOWN
        label, style = status_label(success_rate=0.0, breach_count=0, total_checks=0)
        assert label == "DOWN"
        assert style == "red"


class TestPrintReport:
    def _capture_output(self, stats_list):
        """Capture rich console output to a string."""
        string_io = StringIO()
        test_console = Console(file=string_io, no_color=True, width=120)
        # Temporarily replace the module-level console
        import alm.report as report_module
        original_console = report_module.console
        report_module.console = test_console
        try:
            print_report(stats_list)
        finally:
            report_module.console = original_console
        return string_io.getvalue()

    def test_empty_stats_list_prints_no_data_message(self):
        output = self._capture_output([])
        assert "No monitoring data available" in output

    def test_healthy_endpoint_appears_in_output(self):
        stats = [{
            "endpoint_name": "my-api",
            "total_checks": 10,
            "success_count": 10,
            "success_rate": 100.0,
            "avg_ms": 123.4,
            "min_ms": 50.0,
            "max_ms": 200.0,
            "breach_count": 0,
        }]
        output = self._capture_output(stats)
        assert "my-api" in output
        assert "HEALTHY" in output
        assert "10" in output

    def test_down_endpoint_shows_down_status(self):
        stats = [{
            "endpoint_name": "broken-api",
            "total_checks": 10,
            "success_count": 5,
            "success_rate": 50.0,
            "avg_ms": 200.0,
            "min_ms": 100.0,
            "max_ms": 300.0,
            "breach_count": 0,
        }]
        output = self._capture_output(stats)
        assert "DOWN" in output

    def test_degraded_endpoint_shows_degraded_status(self):
        stats = [{
            "endpoint_name": "slow-api",
            "total_checks": 20,
            "success_count": 20,
            "success_rate": 100.0,
            "avg_ms": 600.0,
            "min_ms": 400.0,
            "max_ms": 800.0,
            "breach_count": 5,
        }]
        output = self._capture_output(stats)
        assert "DEGRADED" in output

    def test_none_avg_ms_shows_na(self):
        stats = [{
            "endpoint_name": "flaky-api",
            "total_checks": 5,
            "success_count": 0,
            "success_rate": 0.0,
            "avg_ms": None,
            "min_ms": None,
            "max_ms": None,
            "breach_count": 0,
        }]
        output = self._capture_output(stats)
        assert "N/A" in output

    def test_multiple_endpoints_all_shown(self):
        stats = [
            {
                "endpoint_name": "api-a",
                "total_checks": 5,
                "success_count": 5,
                "success_rate": 100.0,
                "avg_ms": 100.0,
                "min_ms": 80.0,
                "max_ms": 120.0,
                "breach_count": 0,
            },
            {
                "endpoint_name": "api-b",
                "total_checks": 5,
                "success_count": 3,
                "success_rate": 60.0,
                "avg_ms": 500.0,
                "min_ms": 300.0,
                "max_ms": 700.0,
                "breach_count": 2,
            },
        ]
        output = self._capture_output(stats)
        assert "api-a" in output
        assert "api-b" in output

    def test_success_percentage_formatted(self):
        stats = [{
            "endpoint_name": "api",
            "total_checks": 4,
            "success_count": 3,
            "success_rate": 75.0,
            "avg_ms": 100.0,
            "min_ms": 80.0,
            "max_ms": 120.0,
            "breach_count": 0,
        }]
        output = self._capture_output(stats)
        assert "75.0%" in output


class TestExportCsv:
    def test_exports_correct_headers(self, tmp_path):
        stats = [{
            "endpoint_name": "api",
            "total_checks": 10,
            "success_count": 10,
            "success_rate": 100.0,
            "avg_ms": 100.0,
            "min_ms": 80.0,
            "max_ms": 120.0,
            "breach_count": 0,
        }]
        path = str(tmp_path / "report.csv")
        export_csv(stats, path)

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
        assert "endpoint_name" in headers
        assert "total_checks" in headers
        assert "success_rate" in headers
        assert "avg_ms" in headers
        assert "min_ms" in headers
        assert "max_ms" in headers
        assert "breach_count" in headers
        assert "status" in headers

    def test_exports_correct_data(self, tmp_path):
        stats = [{
            "endpoint_name": "my-service",
            "total_checks": 20,
            "success_count": 18,
            "success_rate": 90.0,
            "avg_ms": 250.0,
            "min_ms": 100.0,
            "max_ms": 600.0,
            "breach_count": 2,
        }]
        path = str(tmp_path / "report.csv")
        export_csv(stats, path)

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]
        assert row["endpoint_name"] == "my-service"
        assert row["total_checks"] == "20"
        assert row["breach_count"] == "2"
        assert row["status"] == "DEGRADED"

    def test_exports_healthy_status(self, tmp_path):
        stats = [{
            "endpoint_name": "healthy-api",
            "total_checks": 10,
            "success_count": 10,
            "success_rate": 100.0,
            "avg_ms": 100.0,
            "min_ms": 80.0,
            "max_ms": 120.0,
            "breach_count": 0,
        }]
        path = str(tmp_path / "report.csv")
        export_csv(stats, path)

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0]["status"] == "HEALTHY"

    def test_exports_down_status(self, tmp_path):
        stats = [{
            "endpoint_name": "down-api",
            "total_checks": 10,
            "success_count": 2,
            "success_rate": 20.0,
            "avg_ms": None,
            "min_ms": None,
            "max_ms": None,
            "breach_count": 0,
        }]
        path = str(tmp_path / "report.csv")
        export_csv(stats, path)

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0]["status"] == "DOWN"
        assert rows[0]["avg_ms"] == ""

    def test_exports_multiple_rows(self, tmp_path):
        stats = [
            {
                "endpoint_name": "api-a",
                "total_checks": 5,
                "success_count": 5,
                "success_rate": 100.0,
                "avg_ms": 50.0,
                "min_ms": 30.0,
                "max_ms": 70.0,
                "breach_count": 0,
            },
            {
                "endpoint_name": "api-b",
                "total_checks": 5,
                "success_count": 5,
                "success_rate": 100.0,
                "avg_ms": 150.0,
                "min_ms": 130.0,
                "max_ms": 170.0,
                "breach_count": 1,
            },
        ]
        path = str(tmp_path / "report.csv")
        export_csv(stats, path)

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        names = {r["endpoint_name"] for r in rows}
        assert names == {"api-a", "api-b"}
