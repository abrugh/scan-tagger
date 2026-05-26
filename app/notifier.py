import json
import logging
import socket
import threading
import time
import traceback
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime

logger = logging.getLogger(__name__)


@dataclass
class Stats:
    """Simple daily stats tracker."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _date: str = ""
    success: int = 0
    failure: int = 0
    renames: list = field(default_factory=list)

    def _reset_if_new_day(self):
        today = date.today().isoformat()
        if self._date != today:
            self._date = today
            self.success = 0
            self.failure = 0
            self.renames.clear()

    def record_success(self, old_name: str, new_name: str):
        with self._lock:
            self._reset_if_new_day()
            self.success += 1
            self.renames.append((old_name, new_name))

    def record_failure(self, filename: str, error: str):
        with self._lock:
            self._reset_if_new_day()
            self.failure += 1

    def snapshot(self) -> dict:
        with self._lock:
            self._reset_if_new_day()
            return {
                "date": self._date,
                "success": self.success,
                "failure": self.failure,
                "renames": list(self.renames),
            }


class Notifier:
    def __init__(self, config):
        self.config = config
        self.stats = Stats()

    def notify_success(self, old_name: str, new_name: str):
        self.stats.record_success(old_name, new_name)
        if not self.config.notify_on_success:
            return
        msg = f"✅ **Scan tagged**: `{old_name}` → `{new_name}`"
        self._send(msg)

    def notify_failure(self, filename: str, error: Exception):
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        short_err = str(error)[:200]
        self.stats.record_failure(filename, short_err)
        msg = f"❌ **Scan tagger failed** on `{filename}`\n```\n{short_err}\n```"
        self._send(msg)

    def notify_startup(self):
        self._send("🟢 **scan-tagger** started — watching for new scans")

    def send_daily_summary(self):
        snap = self.stats.snapshot()
        if snap["success"] == 0 and snap["failure"] == 0:
            return
        lines = [f"📊 **scan-tagger daily summary** ({snap['date']})"]
        lines.append(f"  Processed: **{snap['success']}** success, **{snap['failure']}** failed")
        if snap["renames"]:
            lines.append("  Recent renames:")
            for old, new in snap["renames"][-5:]:
                lines.append(f"  • `{old}` → `{new}`")
        self._send("\n".join(lines))

    def _send(self, message: str):
        """Send to all configured channels."""
        if self.config.discord_webhook_url:
            self._send_discord(message)
        if self.config.signal_recipient:
            self._send_signal(message)

    def _send_discord(self, message: str):
        try:
            payload = json.dumps({"content": message}).encode()
            req = urllib.request.Request(
                self.config.discord_webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    logger.warning("Discord webhook returned %d", resp.status)
        except Exception:
            logger.exception("Failed to send Discord notification")

    def _send_signal(self, message: str):
        """Send via signal-cli daemon JSON-RPC on localhost."""
        # Strip markdown formatting for Signal
        plain = message.replace("**", "").replace("`", "").replace("```\n", "").replace("\n```", "")
        try:
            request = {
                "jsonrpc": "2.0",
                "method": "send",
                "id": 1,
                "params": {
                    "message": plain,
                    "recipient": [self.config.signal_recipient],
                },
            }
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect(("localhost", self.config.signal_port))
            sock.sendall((json.dumps(request) + "\n").encode())
            # Read response (best-effort)
            try:
                sock.recv(4096)
            except socket.timeout:
                pass
            sock.close()
        except Exception:
            logger.exception("Failed to send Signal notification")


class DailySummaryThread(threading.Thread):
    """Background thread that sends a daily summary at a configured hour."""

    def __init__(self, notifier, summary_hour: int = 20):
        super().__init__(daemon=True)
        self.notifier = notifier
        self.summary_hour = summary_hour
        self._stop_event = threading.Event()

    def run(self):
        last_sent = None
        while not self._stop_event.is_set():
            now = datetime.now()
            today = now.date()
            if now.hour >= self.summary_hour and last_sent != today:
                self.notifier.send_daily_summary()
                last_sent = today
            self._stop_event.wait(300)  # check every 5 minutes

    def stop(self):
        self._stop_event.set()
