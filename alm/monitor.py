import time
import requests
from datetime import datetime, timezone
from rich.console import Console

console = Console()


def check_endpoint(endpoint, timeout=10, max_retries=3):
    result = {
        "endpoint_name": endpoint.name,
        "url": endpoint.url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "response_time_ms": None,
        "status_code": None,
        "success": False,
        "threshold_breached": False,
    }

    for attempt in range(max_retries):
        if attempt > 0:
            time.sleep(2 ** (attempt - 1))

        try:
            start = time.perf_counter()
            response = requests.request(
                method=endpoint.method,
                url=endpoint.url,
                headers=endpoint.headers,
                json=endpoint.body if endpoint.body else None,
                timeout=timeout,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            result["response_time_ms"] = elapsed_ms
            result["status_code"] = response.status_code
            result["success"] = response.ok
            result["threshold_breached"] = elapsed_ms > endpoint.threshold_ms
            return result

        except (requests.Timeout, requests.ConnectionError):
            continue

    return result


def detect_degradation(endpoint_name, latest_ms, recent_checks):
    # need at least 3 data points before flagging anything
    times = [
        r["response_time_ms"]
        for r in recent_checks
        if r.get("success") and r.get("response_time_ms") is not None
    ]

    if len(times) < 3:
        return False

    avg = sum(times) / len(times)
    return latest_ms > avg * 1.5


def run_monitor(endpoints, storage_conn, interval=60):
    from .storage import save_check, get_recent_checks

    console.print("[bold cyan]ALM - API Latency Monitor[/bold cyan]")
    console.print(f"Monitoring {len(endpoints)} endpoint(s) every {interval}s. Press Ctrl+C to stop.\n")

    try:
        while True:
            poll_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            console.print(f"[dim]--- Poll at {poll_time} ---[/dim]")

            for endpoint in endpoints:
                result = check_endpoint(endpoint)

                save_check(
                    conn=storage_conn,
                    endpoint_name=result["endpoint_name"],
                    url=result["url"],
                    timestamp=result["timestamp"],
                    response_time_ms=result["response_time_ms"],
                    status_code=result["status_code"],
                    success=result["success"],
                    threshold_breached=result["threshold_breached"],
                )

                ms_str = f"{result['response_time_ms']:.1f}ms" if result["response_time_ms"] is not None else "N/A"
                status_str = str(result["status_code"]) if result["status_code"] is not None else "N/A"

                if not result["success"]:
                    console.print(f"  [bold red][FAIL][/bold red] {endpoint.name} | HTTP {status_str} | {ms_str}")
                else:
                    recent = get_recent_checks(storage_conn, endpoint.name, limit=10)
                    is_degraded = (
                        result["response_time_ms"] is not None
                        and detect_degradation(endpoint.name, result["response_time_ms"], recent)
                    )

                    if is_degraded:
                        console.print(f"  [bold yellow][WARN][/bold yellow] {endpoint.name} | HTTP {status_str} | {ms_str} (degraded)")
                    else:
                        console.print(f"  [bold green][OK][/bold green] {endpoint.name} | HTTP {status_str} | {ms_str}")

            console.print()
            time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[bold cyan]Monitoring stopped.[/bold cyan]")
