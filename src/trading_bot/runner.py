from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from trading_bot.bot import (
    get_account_view,
    get_position_views,
    preview_targets,
    run_once,
)
from trading_bot.config import Settings, load_settings
from trading_bot.llm import llm_configured
from trading_bot.models import CycleResult

log = logging.getLogger(__name__)


class LogBuffer(logging.Handler):
    def __init__(self, capacity: int = 200) -> None:
        super().__init__(level=logging.INFO)
        self.records: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(self.format(record))
        except Exception:
            self.handleError(record)

    def lines(self) -> list[str]:
        return list(self.records)


class BotRunner:
    def __init__(self) -> None:
        self.settings: Settings = load_settings()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.last_cycle: CycleResult | None = None
        self.last_error: str | None = None
        self.last_run_at: str | None = None
        self.logs = LogBuffer()
        self.logs.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(self.logs)
        logging.getLogger().setLevel(logging.INFO)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict[str, Any]:
        from trading_bot.research import enrich_positions, research_links

        account = None
        positions: list[dict[str, Any]] = []
        news: list[dict[str, Any]] = []
        cycle = self.last_cycle.to_dict() if self.last_cycle else None
        try:
            account = get_account_view(self.settings).__dict__
            positions = [p.__dict__ for p in get_position_views(self.settings)]
            extra: list[str] = []
            if cycle:
                extra.extend([t["symbol"] for t in cycle.get("longs") or []])
                extra.extend([t["symbol"] for t in cycle.get("shorts") or []])
            positions, news = enrich_positions(self.settings, positions, extra)
            if cycle:
                for key in ("longs", "shorts"):
                    for t in cycle.get(key) or []:
                        t["links"] = research_links(t["symbol"])
        except Exception as exc:
            self.last_error = str(exc)
            log.exception("Status fetch failed")

        return {
            "running": self.running,
            "dry_run": self.settings.dry_run,
            "paper": self.settings.paper,
            "poll_seconds": self.settings.poll_seconds,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
            "last_cycle": cycle,
            "account": account,
            "positions": positions,
            "news": news,
            "llm": {
                "configured": llm_configured(),
                "used": bool(cycle.get("llm_used")) if cycle else False,
                "rationale": (cycle or {}).get("llm_rationale") or "",
                "universe_size": (cycle or {}).get("universe_size") or 0,
            },
            "risk": {
                "risk_per_position_pct": self.settings.risk_per_position_pct,
                "max_daily_loss_pct": self.settings.max_daily_loss_pct,
                "stop_loss_pct": self.settings.stop_loss_pct,
                "take_profit_pct": self.settings.take_profit_pct,
                "long_slots": self.settings.long_slots,
                "short_slots": self.settings.short_slots,
                "min_price": self.settings.min_price,
            },
            "logs": self.logs.lines()[-80:],
        }

    def set_dry_run(self, enabled: bool) -> None:
        with self._lock:
            self.settings = replace(self.settings, dry_run=enabled)

    def set_poll_seconds(self, seconds: int) -> None:
        seconds = max(30, min(seconds, 3600))
        with self._lock:
            self.settings = replace(self.settings, poll_seconds=seconds)

    def start(self) -> dict[str, Any]:
        if self.running:
            return {"ok": True, "message": "Already running"}
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bot-loop", daemon=True)
        self._thread.start()
        return {"ok": True, "message": "Bot started"}

    def stop(self) -> dict[str, Any]:
        if not self.running:
            return {"ok": True, "message": "Bot already stopped"}
        self._stop.set()
        return {"ok": True, "message": "Stop requested"}

    def run_once_now(self) -> dict[str, Any]:
        try:
            result = run_once(self.settings)
            self.last_cycle = result
            self.last_run_at = datetime.now(timezone.utc).isoformat()
            self.last_error = None
            return {"ok": True, "cycle": result.to_dict()}
        except Exception as exc:
            self.last_error = str(exc)
            log.exception("Manual cycle failed")
            return {"ok": False, "message": str(exc)}

    def preview(self) -> dict[str, Any]:
        try:
            result = preview_targets(self.settings)
            return {"ok": True, "cycle": result.to_dict()}
        except Exception as exc:
            log.exception("Preview failed")
            return {"ok": False, "message": str(exc)}

    def flatten(self) -> dict[str, Any]:
        from trading_bot.clients import make_trading_client

        if self.settings.dry_run:
            return {"ok": True, "message": "Dry run — no flatten executed"}
        try:
            trading = make_trading_client(self.settings)
            trading.close_all_positions(cancel_orders=True)
            return {"ok": True, "message": "Flatten submitted"}
        except Exception as exc:
            log.exception("Flatten failed")
            return {"ok": False, "message": str(exc)}

    def _loop(self) -> None:
        log.info("Bot loop thread started")
        while not self._stop.is_set():
            try:
                with self._lock:
                    settings = self.settings
                result = run_once(settings)
                self.last_cycle = result
                self.last_run_at = datetime.now(timezone.utc).isoformat()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("Cycle failed")
            self._stop.wait(self.settings.poll_seconds)
        log.info("Bot loop thread stopped")
        self._thread = None


runner = BotRunner()
