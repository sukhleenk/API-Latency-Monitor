import os
import requests

FOLLOWUP_EVERY = 5  # re-alert after every N consecutive degraded/failed polls


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        # Per-endpoint state: {name: {"consecutive": int, "alerted": bool}}
        self._state: dict[str, dict] = {}

    def _send(self, text: str) -> None:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5,
            )
            if not r.ok:
                from rich.console import Console
                Console().print(f"  [dim red][Telegram] {r.status_code}: {r.text}[/dim red]")
        except Exception as e:
            from rich.console import Console
            Console().print(f"  [dim red][Telegram] request failed: {e}[/dim red]")

    def on_warn(self, endpoint_name: str, response_ms: float, threshold_ms: int, reason: str) -> None:
        state = self._state.setdefault(endpoint_name, {"consecutive": 0, "alerted": False})
        state["consecutive"] += 1
        n = state["consecutive"]

        if n == 1:
            self._send(
                f"🚨 <b>ALM Alert — {endpoint_name}</b>\n"
                f"Status: {reason}\n"
                f"Response: {response_ms:.0f}ms  (threshold: {threshold_ms}ms)"
            )
            state["alerted"] = True
        elif n % FOLLOWUP_EVERY == 0:
            self._send(
                f"⚠️ <b>ALM Alert — {endpoint_name}</b>\n"
                f"Still {reason.lower()} for {n} consecutive polls\n"
                f"Response: {response_ms:.0f}ms  (threshold: {threshold_ms}ms)"
            )

    def on_fail(self, endpoint_name: str, status_code) -> None:
        state = self._state.setdefault(endpoint_name, {"consecutive": 0, "alerted": False})
        state["consecutive"] += 1
        n = state["consecutive"]
        code_str = str(status_code) if status_code is not None else "no response"

        if n == 1:
            self._send(
                f"🔴 <b>ALM Alert — {endpoint_name}</b>\n"
                f"Status: Failed (HTTP {code_str})"
            )
            state["alerted"] = True
        elif n % FOLLOWUP_EVERY == 0:
            self._send(
                f"🔴 <b>ALM Alert — {endpoint_name}</b>\n"
                f"Still failing for {n} consecutive polls (HTTP {code_str})"
            )

    def on_ok(self, endpoint_name: str, response_ms: float) -> None:
        state = self._state.get(endpoint_name)
        if state and state["alerted"]:
            n = state["consecutive"]
            self._send(
                f"✅ <b>ALM Recovery — {endpoint_name}</b>\n"
                f"Back to normal after {n} degraded poll(s)\n"
                f"Response: {response_ms:.0f}ms"
            )
        self._state[endpoint_name] = {"consecutive": 0, "alerted": False}


def load_notifier(config_notifications: dict | None) -> TelegramNotifier | None:
    """
    Build a TelegramNotifier from env vars and/or config.yaml notifications block.
    Env vars take precedence over config file values.

    Required:
      ALM_TELEGRAM_TOKEN   (or notifications.telegram.token in config.yaml)
      ALM_TELEGRAM_CHAT_ID (or notifications.telegram.chat_id in config.yaml)
    """
    cfg_tg = (config_notifications or {}).get("telegram", {}) or {}

    token = os.getenv("ALM_TELEGRAM_TOKEN") or cfg_tg.get("token")
    chat_id = os.getenv("ALM_TELEGRAM_CHAT_ID") or cfg_tg.get("chat_id")

    if not token or not chat_id:
        return None

    return TelegramNotifier(token=str(token), chat_id=str(chat_id))
