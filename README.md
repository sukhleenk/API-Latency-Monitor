# ALM: API Latency Monitor

[![Tests](https://github.com/sukhleenk/API-Latency-Monitor/actions/workflows/tests.yml/badge.svg)](https://github.com/sukhleenk/API-Latency-Monitor/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/api-latency-monitor)](https://pypi.org/project/api-latency-monitor/)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A command-line tool for watching HTTP endpoints. It polls them on an interval, records every check in a local SQLite file, warns you when response times drift away from normal, and prints a summary table when you ask for one. 

<!-- ```
                    API Latency Report
╭─────────────────┬────────┬──────────┬─────────┬───────┬───────┬──────────┬──────────╮
│ Endpoint        │ Checks │ Success% │ Avg(ms) │   Min │   Max │ Breaches │  Status  │
├─────────────────┼────────┼──────────┼─────────┼───────┼───────┼──────────┼──────────┤
│ Weather NYC     │     42 │   100.0% │   187.3 │ 134.1 │ 312.5 │        0 │ HEALTHY  │
│ Weather SLC     │     42 │    97.6% │   431.8 │ 201.4 │ 891.2 │        7 │ DEGRADED │
╰─────────────────┴────────┴──────────┴─────────┴───────┴───────┴──────────┴──────────╯
``` -->

## Contents

- [Why](#why)
- [Install](#install)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Commands](#commands)
- [Telegram alerts](#telegram-alerts)
- [How it works](#how-it-works)
- [Where the data lives](#where-the-data-lives)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Why

I got tired of finding out an API was slow from a user complaint. Our internal dashboards tracked uptime, but latency was a blind spot. Services were technically "up" while responding in 2-3 seconds instead of 200ms, and nobody noticed until customers started asking questions. I wanted something I could point at any endpoint, leave running in a terminal, and get a warning from before it turned into an incident.

## Install

```bash
pip install api-latency-monitor
```

Requires Python 3.10 or newer. To work on the code instead:

```bash
git clone https://github.com/sukhleenk/API-Latency-Monitor
cd API-Latency-Monitor
pip install -e ".[dev]"
```

## Quick start

```bash
cp config.example.yaml config.yaml   # start from the sample config
alm add                              # or build an endpoint interactively
alm ping "Weather SLC"               # one-off check, nothing recorded
alm monitor                          # poll every 60s until Ctrl+C
alm report                           # summary of everything recorded
```

## Configuration

Endpoints live in `config.yaml` in the directory you run `alm` from. Point somewhere else with `--config path/to/file.yaml` on any command.

```yaml
endpoints:
  - name: "Weather SLC"
    url: "https://api.open-meteo.com/v1/forecast?latitude=40.76&longitude=-111.89&current_weather=true"
    method: GET
    threshold_ms: 500

  - name: "Auth Service"
    url: "https://auth.example.com/ping"
    method: GET
    headers:
      Authorization: "Bearer your-token"
    threshold_ms: 200

  - name: "Search API"
    url: "https://api.example.com/search"
    method: POST
    headers:
      Content-Type: "application/json"
    body:
      query: "hello"
    threshold_ms: 300
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `name` | yes | | Label used in output, reports and alerts |
| `url` | yes | | Full URL, query string included |
| `method` | no | `GET` | Any HTTP verb |
| `headers` | no | none | Sent with every request |
| `body` | no | none | Sent as a JSON body on POST, PUT and PATCH |
| `threshold_ms` | no | `500` | Response times above this count as a breach |

`config.yaml` is gitignored, so tokens you put in it stay on your machine.

## Commands

Every command takes `--help`. Run `alm --help` for the full list.

### `alm monitor`

Polls all configured endpoints in a loop and writes each result to the database.

```bash
alm monitor                       # every 60 seconds
alm monitor --interval 30         # every 30 seconds
alm monitor --config ./prod.yaml  # a different config file
```

Output is color coded per check: green `[OK]`, yellow `[WARN]` when the response time is well above the recent average, red `[FAIL]` when the request errored or returned a non-2xx status. `Ctrl+C` stops the loop.

```
ALM - API Latency Monitor
Monitoring 2 endpoint(s) every 60s. Press Ctrl+C to stop.

--- Poll at 2026-04-09 19:26:08 UTC ---
  [OK] Weather NYC | HTTP 200 | 187.3ms
  [WARN] Weather SLC | HTTP 200 | 891.2ms (degraded)
```

### `alm report`

Aggregates the recorded history into a table.

```bash
alm report
alm report --endpoint "Weather SLC"   # one endpoint
alm report --failures-only            # only endpoints with breaches
alm report --since 24                 # last 24 hours
alm report --export out.csv           # also write a CSV
```

Status is **HEALTHY** when the success rate is 80% or better with no threshold breaches, **DEGRADED** when there are breaches, and **DOWN** when the success rate falls below 80%.

The CSV holds one row per endpoint with the columns `endpoint_name`, `total_checks`, `success_count`, `success_rate`, `avg_ms`, `min_ms`, `max_ms`, `breach_count` and `status`. Filters apply to the export as well.

### `alm status`

The most recent check for each endpoint, which is useful for a quick look without scrolling back through the monitor loop.

```
╭─────────────────┬─────────────────────┬─────────────┬──────────┬────────╮
│ Endpoint        │          Last Check │ Status Code │  Latency │ Result │
├─────────────────┼─────────────────────┼─────────────┼──────────┼────────┤
│ Weather NYC     │ 2026-04-09 19:26:08 │         200 │  187.3ms │   OK   │
│ Weather SLC     │ 2026-04-09 19:26:15 │         200 │  891.2ms │  SLOW  │
╰─────────────────┴─────────────────────┴─────────────┴──────────┴────────╯
```

### `alm ping`

A single check against one endpoint. Pass a name from your config to reuse its method, headers, body and threshold, or pass a raw URL to check something that is not configured at all.

```bash
alm ping "Weather SLC"
alm ping https://example.com/health
```

```
Pinging Weather SLC...
SLOW  HTTP 200  607.8ms  (exceeded 500ms threshold)
```

Nothing is written to the database, so pings never affect your report numbers.

### `alm add`

Prompts for a name, URL, method, threshold and optional JSON body, shows you the result, and appends it to `config.yaml` after you confirm.

### `alm clear`

Deletes every recorded check. It asks for confirmation first.

## Telegram alerts

ALM can message you on Telegram when an endpoint degrades or fails, and again when it recovers. Alerts are sent from the `alm monitor` loop.

1. Message [@BotFather](https://t.me/BotFather), send `/newbot`, follow the prompts, and save the bot token it gives you.
2. Search for your new bot in Telegram and send it any message, so it is allowed to reply to you.
3. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID.
4. Put both in `config.yaml`:

```yaml
notifications:
  telegram:
    token: "your-bot-token-here"
    chat_id: "your-chat-id-here"
```

Environment variables work too, and take precedence over the config file:

```bash
export ALM_TELEGRAM_TOKEN="your-bot-token-here"
export ALM_TELEGRAM_CHAT_ID="your-chat-id-here"
```

With neither set, monitoring runs silently and no alerts are sent.

| Message | Sent when |
|---|---|
| 🚨 Alert | First degraded poll for an endpoint |
| ⚠️ Still degraded | Every 5th consecutive degraded poll after that |
| 🔴 Alert | First failed poll, then every 5th consecutive failure |
| ✅ Recovery | First healthy poll after an alert |

The counter resets on recovery, so a flapping endpoint will not send one message per poll.

## How it works

**Requests.** Each check sends the configured method, headers and body with a 10 second timeout. Timeouts and connection errors are retried up to 3 attempts with a 1s then 2s backoff. An HTTP response counts as a failure when the status is not 2xx, and is not retried, since the endpoint clearly answered.

**Threshold breaches.** Any successful response slower than the endpoint's `threshold_ms` is flagged as a breach. Breaches drive the `Breaches` column and the DEGRADED status in reports, and show up as `SLOW` in `alm status` and `alm ping`.

**Degradation.** Separately from the fixed threshold, `alm monitor` compares each new reading against the average of the successful checks among the last 10 for that endpoint. More than 1.5x that average prints `[WARN]` and triggers a Telegram alert. At least 3 successful readings are needed before this kicks in, so a fresh database will not warn on the first few polls. This is what catches an endpoint that is slowing down while still sitting under its threshold.

## Where the data lives

Checks are stored in `alm_data.db`, a SQLite file created in the directory you run `alm` from. One row per check in a `checks` table: endpoint name, URL, UTC timestamp, response time, status code, success flag and breach flag. Query it directly whenever the built-in report is not enough.

```bash
sqlite3 alm_data.db "SELECT timestamp, response_time_ms FROM checks WHERE endpoint_name='Weather SLC' ORDER BY timestamp DESC LIMIT 10;"
```

The file is gitignored. Delete it or run `alm clear` to start over.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests need no network access. Storage tests run against an in-memory SQLite database and monitor tests mock `requests`. CI runs the suite on Python 3.10, 3.11 and 3.12.

```
alm/
  cli.py        command definitions
  config.py     YAML parsing into Endpoint objects
  monitor.py    polling loop, request retries, degradation detection
  notifier.py   Telegram alerting and alert state
  report.py     report table and CSV export
  storage.py    SQLite schema and queries
```

## Contributing

Every piece of work is better with collaboration, more so for code. Issues and pull requests are welcome, whether that is a new feature, a bug fix or a rough idea you want to talk through.

## License

MIT. See [LICENSE](LICENSE).
