from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
JOURNAL_PATH = DATA_DIR / "journal.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self, path: Path = JOURNAL_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"llm_events": [], "trades": [], "cycles": []})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"llm_events": [], "trades": [], "cycles": []}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_llm_event(
        self,
        stage: str,
        detail: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            store = self._read()
            store.setdefault("llm_events", []).append(
                {
                    "ts": _now(),
                    "stage": stage,
                    "detail": detail,
                    "data": data or {},
                }
            )
            store["llm_events"] = store["llm_events"][-300:]
            self._write(store)

    def add_cycle(self, cycle: dict[str, Any]) -> None:
        with self._lock:
            store = self._read()
            store.setdefault("cycles", []).append({"ts": _now(), **cycle})
            store["cycles"] = store["cycles"][-100:]
            self._write(store)

    def add_trade(self, trade: dict[str, Any]) -> None:
        with self._lock:
            store = self._read()
            store.setdefault("trades", []).append({"ts": _now(), **trade})
            store["trades"] = store["trades"][-500:]
            self._write(store)

    def llm_feed(self, limit: int = 80) -> list[dict[str, Any]]:
        with self._lock:
            events = self._read().get("llm_events", [])
        return list(reversed(events[-limit:]))

    def cycles(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            cycles = self._read().get("cycles", [])
        return list(reversed(cycles[-limit:]))

    def trades(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            trades = self._read().get("trades", [])
        return list(reversed(trades[-limit:]))

    def summary(self) -> dict[str, Any]:
        trades = self.trades(limit=500)
        cycles = self.cycles(limit=100)
        buys = [t for t in trades if str(t.get("side", "")).lower() in {"buy", "long"}]
        sells = [t for t in trades if str(t.get("side", "")).lower() in {"sell", "short"}]
        symbols: dict[str, int] = {}
        for t in trades:
            sym = str(t.get("symbol", "?"))
            symbols[sym] = symbols.get(sym, 0) + 1
        top = sorted(symbols.items(), key=lambda x: x[1], reverse=True)[:8]
        llm_cycles = [c for c in cycles if c.get("llm_used")]
        return {
            "total_trades": len(trades),
            "buys": len(buys),
            "sells": len(sells),
            "cycles": len(cycles),
            "llm_cycles": len(llm_cycles),
            "top_symbols": [{"symbol": s, "count": n} for s, n in top],
            "latest_rationale": next(
                (c.get("llm_rationale") for c in cycles if c.get("llm_rationale")),
                "",
            ),
            "latest_cycle_message": cycles[0].get("message") if cycles else "",
            "recent_trades": trades[:12],
            "recent_cycles": cycles[:8],
        }


journal = Journal()
