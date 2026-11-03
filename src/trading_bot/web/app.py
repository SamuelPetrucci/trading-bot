from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from trading_bot.charts import fetch_bars
from trading_bot.journal import journal
from trading_bot.runner import runner

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="Trading Bot Dashboard", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class DryRunBody(BaseModel):
    enabled: bool


class PollBody(BaseModel):
    seconds: int = Field(ge=30, le=3600)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def api_health() -> dict:
    return {"ok": True, "service": "trading-bot"}


@app.get("/api/status")
def api_status() -> dict:
    return runner.status()


@app.post("/api/start")
def api_start() -> dict:
    return runner.start()


@app.post("/api/stop")
def api_stop() -> dict:
    return runner.stop()


@app.post("/api/once")
def api_once() -> dict:
    return runner.run_once_now()


@app.post("/api/preview")
def api_preview() -> dict:
    return runner.preview()


@app.post("/api/flatten")
def api_flatten() -> dict:
    return runner.flatten()


@app.post("/api/dry-run")
def api_dry_run(body: DryRunBody) -> dict:
    runner.set_dry_run(body.enabled)
    return {"ok": True, "dry_run": runner.settings.dry_run}


@app.post("/api/poll")
def api_poll(body: PollBody) -> dict:
    runner.set_poll_seconds(body.seconds)
    return {"ok": True, "poll_seconds": runner.settings.poll_seconds}


@app.get("/api/bars")
def api_bars(
    symbol: str = Query(..., min_length=1, max_length=12),
    timeframe: str = Query("5Min"),
    limit: int = Query(120, ge=20, le=500),
) -> dict:
    try:
        bars = fetch_bars(runner.settings, symbol, timeframe=timeframe, limit=limit)
        return {"ok": True, "symbol": symbol.upper(), "timeframe": timeframe, "bars": bars}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/llm/activity")
def api_llm_activity(limit: int = Query(80, ge=1, le=300)) -> dict:
    return {
        "ok": True,
        "configured": runner.status().get("llm", {}).get("configured"),
        "events": journal.llm_feed(limit=limit),
        "cycles": journal.cycles(limit=20),
    }


@app.get("/api/trades/summary")
def api_trades_summary() -> dict:
    summary = journal.summary()
    # Enrich with live Alpaca orders when possible
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        from trading_bot.clients import make_trading_client

        trading = make_trading_client(runner.settings)
        orders = trading.get_orders(
            filter=GetOrdersRequest(status=QueryOrderStatus.ALL, limit=30)
        )
        summary["broker_orders"] = [
            {
                "id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value if hasattr(o.side, "value") else str(o.side),
                "qty": float(o.qty or 0),
                "filled_qty": float(o.filled_qty or 0),
                "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                "submitted_at": str(o.submitted_at),
                "filled_avg_price": float(o.filled_avg_price)
                if o.filled_avg_price
                else None,
            }
            for o in orders
        ]
    except Exception as exc:
        summary["broker_orders_error"] = str(exc)
        summary["broker_orders"] = []
    return {"ok": True, "summary": summary}


@app.on_event("startup")
def _maybe_autostart() -> None:
    if os.getenv("AUTO_START", "").lower() in {"1", "true", "yes"}:
        result = runner.start()
        print(f"AUTO_START: {result.get('message')}")


def main() -> None:
    import logging

    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    # Railway sets PORT; local default 8787
    port = int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT", "8787"))
    print(f"Dashboard API (no auth): http://127.0.0.1:{port}")
    print(f"Trading mode: dry_run={os.getenv('DRY_RUN')} paper={os.getenv('ALPACA_PAPER_TRADE')}")
    print("For Railway/Vercel: set env vars in the host dashboard; never commit .env")
    uvicorn.run(
        "trading_bot.web.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
