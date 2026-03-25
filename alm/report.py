from rich.console import Console
from rich.table import Table
from rich import box
import csv

console = Console()


def status_label(success_rate, breach_count, total_checks):
    if success_rate < 80.0:
        return "DOWN", "red"
    elif breach_count > 0:
        return "DEGRADED", "yellow"
    return "HEALTHY", "green"


def print_report(stats_list):
    if not stats_list:
        console.print("[yellow]No monitoring data available.[/yellow]")
        return

    table = Table(
        title="API Latency Report",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Endpoint", style="bold", min_width=15)
    table.add_column("Checks", justify="right")
    table.add_column("Success%", justify="right")
    table.add_column("Avg(ms)", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Breaches", justify="right")
    table.add_column("Status", justify="center")

    for stat in stats_list:
        total = stat.get("total_checks", 0)
        success_rate = stat.get("success_rate", 0.0)
        avg_ms = stat.get("avg_ms")
        min_ms = stat.get("min_ms")
        max_ms = stat.get("max_ms")
        breach_count = stat.get("breach_count", 0)

        label, style = status_label(success_rate, breach_count, total)

        table.add_row(
            stat.get("endpoint_name", ""),
            str(total),
            f"{success_rate:.1f}%",
            f"{avg_ms:.1f}" if avg_ms is not None else "N/A",
            f"{min_ms:.1f}" if min_ms is not None else "N/A",
            f"{max_ms:.1f}" if max_ms is not None else "N/A",
            str(breach_count),
            f"[{style}]{label}[/{style}]",
        )

    console.print(table)


def export_csv(stats_list, path):
    fieldnames = ["endpoint_name", "total_checks", "success_count", "success_rate",
                  "avg_ms", "min_ms", "max_ms", "breach_count", "status"]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for stat in stats_list:
            total = stat.get("total_checks", 0)
            success_rate = stat.get("success_rate", 0.0)
            breach_count = stat.get("breach_count", 0)
            label, _ = status_label(success_rate, breach_count, total)
            avg_ms = stat.get("avg_ms")
            min_ms = stat.get("min_ms")
            max_ms = stat.get("max_ms")

            writer.writerow({
                "endpoint_name": stat.get("endpoint_name", ""),
                "total_checks": total,
                "success_count": stat.get("success_count", 0),
                "success_rate": f"{success_rate:.1f}",
                "avg_ms": f"{avg_ms:.1f}" if avg_ms is not None else "",
                "min_ms": f"{min_ms:.1f}" if min_ms is not None else "",
                "max_ms": f"{max_ms:.1f}" if max_ms is not None else "",
                "breach_count": breach_count,
                "status": label,
            })
