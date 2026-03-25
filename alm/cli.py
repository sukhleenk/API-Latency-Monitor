import click
import yaml
from collections import defaultdict
from pathlib import Path

from .config import load_config, DEFAULT_CONFIG_PATH
from .storage import init_db, get_all_endpoint_stats, get_endpoint_stats, clear_all, get_checks_since
from .monitor import run_monitor
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
        endpoints = load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if not endpoints:
        click.echo("No endpoints found in config. Use `alm add` to add one.")
        raise SystemExit(0)

    conn = init_db()
    try:
        run_monitor(endpoints, conn, interval=interval)
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

    click.echo(f"\n  Name:      {name}")
    click.echo(f"  URL:       {url}")
    click.echo(f"  Method:    {method}")
    click.echo(f"  Threshold: {threshold_ms}ms")

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

    data["endpoints"].append({
        "name": name,
        "url": url,
        "method": method,
        "threshold_ms": threshold_ms,
    })

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    click.echo(f"Added '{name}' to {config_path}.")
