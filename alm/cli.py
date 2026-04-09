import click
import yaml
from collections import defaultdict
from pathlib import Path

from .config import load_config, Endpoint, DEFAULT_CONFIG_PATH
from .notifier import load_notifier
from .storage import init_db, get_all_endpoint_stats, get_endpoint_stats, clear_all, get_checks_since, get_last_check_per_endpoint
from .monitor import run_monitor, check_endpoint
from .report import print_report, export_csv


@click.group()
def cli():
    """ALM - API Latency Monitor"""
    pass


@cli.command()
@click.option("--interval", default=60, show_default=True, help="Poll interval in seconds")
@click.option("--config", default="config.yaml", help="Path to config file")
def monitor(interval, config):
    """Start monitoring all configured endpoints."""
    config_path = Path(config)
    try:
        endpoints, notifications = load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if not endpoints:
        click.echo("No endpoints found in config. Use `alm add` to add one.")
        raise SystemExit(0)

    notifier = load_notifier(notifications)

    conn = init_db()
    try:
        run_monitor(endpoints, conn, interval=interval, notifier=notifier)
    finally:
        conn.close()


@cli.command()
@click.option("--endpoint", default=None, help="Filter to a specific endpoint")
@click.option("--failures-only", is_flag=True, default=False, help="Only show endpoints with threshold breaches")
@click.option("--export", default=None, help="Export to CSV at this path")
@click.option("--since", default=None, type=int, help="Only include checks from the last N hours")
@click.option("--config", default="config.yaml", help="Path to config file")
def report(endpoint, failures_only, export, since, config):
    """Show a latency report for all monitored endpoints."""
    conn = init_db()
    try:
        if since is not None:
            rows = get_checks_since(conn, since_hours=since, endpoint_name=endpoint)
            stats_list = _compute_stats_from_rows(rows)
        elif endpoint is not None:
            stat = get_endpoint_stats(conn, endpoint)
            stats_list = [stat] if stat else []
        else:
            stats_list = get_all_endpoint_stats(conn)

        if failures_only:
            stats_list = [s for s in stats_list if s.get("breach_count", 0) > 0]

        print_report(stats_list)

        if export:
            export_csv(stats_list, export)
            click.echo(f"Report exported to {export}")
    finally:
        conn.close()


def _compute_stats_from_rows(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["endpoint_name"]].append(row)

    stats_list = []
    for ep_name, checks in grouped.items():
        total = len(checks)
        success_count = sum(1 for c in checks if c.get("success"))
        breach_count = sum(1 for c in checks if c.get("threshold_breached"))
        times = [c["response_time_ms"] for c in checks if c.get("response_time_ms") is not None]

        stats_list.append({
            "endpoint_name": ep_name,
            "total_checks": total,
            "success_count": success_count,
            "success_rate": (success_count / total * 100.0) if total > 0 else 0.0,
            "avg_ms": sum(times) / len(times) if times else None,
            "min_ms": min(times) if times else None,
            "max_ms": max(times) if times else None,
            "breach_count": breach_count,
        })

    return stats_list


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
def status(config):
    """Show the most recent check for each endpoint."""
    conn = init_db()
    try:
        rows = get_last_check_per_endpoint(conn)
    finally:
        conn.close()

    if not rows:
        click.echo("No data yet. Run `alm monitor` first.")
        return

    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Endpoint", style="bold", min_width=15)
    table.add_column("Last Check", justify="right")
    table.add_column("Status Code", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Result", justify="center")

    for row in rows:
        ts = row["timestamp"][:19].replace("T", " ")
        ms = f"{row['response_time_ms']:.1f}ms" if row["response_time_ms"] is not None else "N/A"
        code = str(row["status_code"]) if row["status_code"] is not None else "N/A"

        if not row["success"]:
            result = "[bold red]FAIL[/bold red]"
        elif row["threshold_breached"]:
            result = "[bold yellow]SLOW[/bold yellow]"
        else:
            result = "[bold green]OK[/bold green]"

        table.add_row(row["endpoint_name"], ts, code, ms, result)

    console.print(table)


@cli.command()
@click.argument("name_or_url")
@click.option("--config", default="config.yaml", help="Path to config file")
def ping(name_or_url, config):
    """Run a one-off check against an endpoint. Pass a name from config or a raw URL."""
    from rich.console import Console
    console = Console()

    endpoint = None

    config_path = Path(config)
    if config_path.exists():
        try:
            endpoints, _ = load_config(config_path)
            endpoint = next((e for e in endpoints if e.name == name_or_url), None)
        except Exception:
            pass

    if endpoint is None:
        endpoint = Endpoint(name=name_or_url, url=name_or_url)

    console.print(f"Pinging [bold]{endpoint.name}[/bold]...")
    result = check_endpoint(endpoint)

    ms = f"{result['response_time_ms']:.1f}ms" if result["response_time_ms"] is not None else "N/A"
    code = str(result["status_code"]) if result["status_code"] is not None else "N/A"

    if not result["success"]:
        console.print(f"[bold red]FAIL[/bold red]  HTTP {code}  {ms}")
    elif result["threshold_breached"]:
        console.print(f"[bold yellow]SLOW[/bold yellow]  HTTP {code}  {ms}  (exceeded {endpoint.threshold_ms}ms threshold)")
    else:
        console.print(f"[bold green]OK[/bold green]    HTTP {code}  {ms}")


@cli.command()
def clear():
    """Clear all stored monitoring history."""
    conn = init_db()
    if click.confirm("This will delete all recorded checks. Continue?"):
        clear_all(conn)
        click.echo("History cleared.")
    conn.close()


@cli.command()
@click.option("--config", default="config.yaml", help="Path to config file")
def add(config):
    """Interactively add a new endpoint to config.yaml."""
    config_path = Path(config)

    name = click.prompt("Endpoint name")
    url = click.prompt("URL")
    method = click.prompt("HTTP method", default="GET").upper()
    threshold_ms = click.prompt("Threshold (ms)", default=500, type=int)

    body_str = None
    if method in ("POST", "PUT", "PATCH"):
        if click.confirm("Add a JSON request body?", default=False):
            body_str = click.prompt("JSON body")

    click.echo(f"\n  Name:      {name}")
    click.echo(f"  URL:       {url}")
    click.echo(f"  Method:    {method}")
    click.echo(f"  Threshold: {threshold_ms}ms")
    if body_str:
        click.echo(f"  Body:      {body_str}")

    if not click.confirm("\nSave to config?"):
        click.echo("Aborted.")
        return

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    if not data.get("endpoints"):
        data["endpoints"] = []

    entry = {"name": name, "url": url, "method": method, "threshold_ms": threshold_ms}
    if body_str:
        import json
        try:
            entry["body"] = json.loads(body_str)
        except json.JSONDecodeError:
            click.echo("Warning: body was not valid JSON, skipping it.")

    data["endpoints"].append(entry)

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    click.echo(f"Added '{name}' to {config_path}.")
