# ALM — API Latency Monitor

![Tests](https://github.com/sukhleenk/API-Latency-Monitor/actions/workflows/tests.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/api-latency-monitor)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A small CLI tool for keeping an eye on HTTP endpoints. It polls them on an interval, stores the results in a local SQLite database, and prints a summary table whenever you want one. Nothing fancy and no servers, no dashboards, no accounts.

## Motivation

I got tired of finding out an API was slow from a user complaint. Our internal dashboards tracked uptime but latency was a blind spot. Things would be technically "up" while responding in 2-3 seconds instead of 200ms, and nobody would notice until customers started complaining. I wanted something I could point at any endpoint, leave running in a terminal, and get a warning before it became an incident. This is that tool.

## Install

```bash
pip install api-latency-monitor
```

Or clone and install locally for development:

```bash
git clone https://github.com/sukhleenk/API-Latency-Monitor
cd API-Latency-Monitor
pip install -e ".[dev]"
```

## Setup

Copy the example config and edit it, or use `alm add` to build it interactively:

```bash
cp config.example.yaml config.yaml
```

```yaml
endpoints:
  - name: "Weather SLC"
    url: "https://api.open-meteo.com/v1/forecast?latitude=40.7608&longitude=-111.8910&current_weather=true"
    method: GET
    threshold_ms: 500

  - name: "Auth Service"
    url: "https://auth.example.com/ping"
    method: GET
    headers:
      Authorization: "Bearer your-token"
    threshold_ms: 200
```

`threshold_ms` is the latency limit you care about — anything over it gets counted as a breach. Defaults to 500ms if you leave it out.

## Usage

**Start monitoring:**
```bash
alm monitor                      # polls every 60 seconds
alm monitor --interval 30        # poll every 30 seconds
alm monitor --config ./prod.yaml # use a different config
```

The terminal output is color-coded: `[OK]` is green, `[WARN]` is yellow (response time spiked more than 1.5x the rolling average), `[FAIL]` is red. Press `Ctrl+C` to stop.

**View a report:**
```bash
alm report
alm report --endpoint "Weather SLC"   # one endpoint only
alm report --failures-only            # only endpoints with breaches
alm report --since 24                 # last 24 hours
alm report --export out.csv           # export to CSV
```

Example output:
```
                    API Latency Report
╭─────────────────┬────────┬──────────┬─────────┬───────┬───────┬──────────┬──────────╮
│ Endpoint        │ Checks │ Success% │ Avg(ms) │   Min │   Max │ Breaches │   Status │
├─────────────────┼────────┼──────────┼─────────┼───────┼───────┼──────────┼──────────┤
│ Weather NYC     │     42 │   100.0% │   187.3 │ 134.1 │ 312.5 │        0 │  HEALTHY │
│ Weather SLC     │     42 │    97.6% │   431.8 │ 201.4 │ 891.2 │        7 │ DEGRADED │
╰─────────────────┴────────┴──────────┴─────────┴───────┴───────┴──────────┴──────────╯
```

Status is **HEALTHY** (green) if success rate ≥ 80% and no threshold breaches, **DEGRADED** (yellow) if there have been breaches, and **DOWN** (red) if success rate drops below 80%.

**Add an endpoint interactively:**
```bash
alm add
```

**Clear history:**
```bash
alm clear
```

## Telegram Alert Integration

ALM can send you Telegram messages when an endpoint degrades or fails, and again when it recovers.

**Setup:**

1. Open Telegram and search for [@api_latency_bot](https://t.me/api_latency_bot) — send it any message to start a conversation
2. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot), which will reply with your user ID
3. Add a `notifications` block to your `config.yaml`:

```yaml
notifications:
  telegram:
    token: "8776424559:AAH5o0iMb-yLqGUnftO9EKpSq6xCB0VpNDk"
    chat_id: "your-chat-id-here"
```

Or use environment variables instead:

```bash
export ALM_TELEGRAM_TOKEN="8776424559:AAH5o0iMb-yLqGUnftO9EKpSq6xCB0VpNDk"
export ALM_TELEGRAM_CHAT_ID="your-chat-id-here"
```

Each user gets their own alerts. The bot routes messages by chat ID, so you only receive notifications for your own monitored endpoints.

**Alert behavior:**

| Message | When |
|---|---|
| 🚨 Alert | First degraded or failed poll |
| ⚠️ Still degraded | Every 5 consecutive degraded polls after that |
| ✅ Recovery | First successful poll after an alert |

## How it works

- Retries failed requests up to 3 times with exponential backoff (1s, 2s) before marking a check as failed
- Degradation detection compares the latest reading against the rolling average of the last 10 successful checks — if it's more than 50% above average, it prints a warning
- All data lives in `alm_data.db` (SQLite) in the current directory

## Tests

```bash
pytest tests/ -v
```

No network access needed. Storage tests use an in-memory SQLite db and monitor tests mock `requests`.

## Contributing
I believe every piece of work on earth is better with collaboration, even more so for technological advancements and code. Feel free to suggest new features, or create pull requests to contribute to the project!
