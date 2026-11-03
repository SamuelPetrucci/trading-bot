from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TargetView:
    symbol: str
    side: str
    price: float
    percent_change: float
    source: str = ""
    reason: str = ""


@dataclass
class PositionView:
    symbol: str
    side: str
    qty: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float
    current_price: float
    avg_entry_price: float


@dataclass
class AccountView:
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    daily_pnl_pct: float
    paper: bool
    market_open: bool


@dataclass
class CycleResult:
    ok: bool
    message: str
    longs: list[TargetView] = field(default_factory=list)
    shorts: list[TargetView] = field(default_factory=list)
    halted: bool = False
    llm_used: bool = False
    llm_rationale: str = ""
    universe_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
