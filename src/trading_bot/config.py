from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str
    secret_key: str
    paper: bool

    # Universe / filters
    movers_top: int = 30
    long_slots: int = 3
    short_slots: int = 3
    min_price: float = 15.0
    min_pct_move: float = 2.0  # |% change| required to qualify
    max_pct_move: float = 25.0  # skip already-parabolic pumps

    # Risk
    risk_per_position_pct: float = 2.0  # % of equity per name
    max_daily_loss_pct: float = 3.0
    stop_loss_pct: float = 4.0
    take_profit_pct: float = 8.0

    # Loop
    poll_seconds: int = 300
    dry_run: bool = False


def load_settings() -> Settings:
    load_dotenv()
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        raise SystemExit(
            "Missing ALPACA_API_KEY / ALPACA_SECRET_KEY. Copy .env.example to .env and fill them in."
        )

    paper = os.getenv("ALPACA_PAPER_TRADE", "true").lower() in {"1", "true", "yes"}
    dry_run = os.getenv("DRY_RUN", "false").lower() in {"1", "true", "yes"}

    return Settings(
        api_key=api_key,
        secret_key=secret_key,
        paper=paper,
        movers_top=int(os.getenv("MOVERS_TOP", "30")),
        long_slots=int(os.getenv("LONG_SLOTS", "3")),
        short_slots=int(os.getenv("SHORT_SLOTS", "3")),
        min_price=float(os.getenv("MIN_PRICE", "15")),
        min_pct_move=float(os.getenv("MIN_PCT_MOVE", "2")),
        max_pct_move=float(os.getenv("MAX_PCT_MOVE", "25")),
        risk_per_position_pct=float(os.getenv("RISK_PER_POSITION_PCT", "2")),
        max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "3")),
        stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "4")),
        take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "8")),
        poll_seconds=int(os.getenv("POLL_SECONDS", "300")),
        dry_run=dry_run,
    )
