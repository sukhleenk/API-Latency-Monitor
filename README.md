# alm — API Latency Monitor

A small CLI tool for keeping an eye on HTTP endpoints. It polls them on an interval, stores the results in a local SQLite database, and prints a summary table whenever you want one. Nothing fancy — no servers, no dashboards, no accounts.

## Motivation

I got tired of finding out an API was slow from a user complaint. Our internal dashboards tracked uptime but latency was a blind spot — things would be technically "up" while responding in 2-3 seconds instead of 200ms, and nobody would notice until customers started complaining. I wanted something I could point at any endpoint, leave running in a terminal, and get a warning before it became an incident. This is that tool.

## Install

```bash
git clone https://github.com/yourusername/alm
cd alm
pip install -e .
```

For dev (includes pytest):

```bash
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

## How it works

- Retries failed requests up to 3 times with exponential backoff (1s, 2s) before marking a check as failed
- Degradation detection compares the latest reading against the rolling average of the last 10 successful checks — if it's more than 50% above average, it prints a warning
- All data lives in `alm_data.db` (SQLite) in the current directory

## Tests

```bash
pytest tests/ -v
```

No network access needed — storage tests use an in-memory SQLite db and monitor tests mock `requests`.
