from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.client import TradingClient
from alpaca.trading.models import Position, TradeAccount

from trading_bot.config import Settings


@dataclass
class RiskSnapshot:
    equity: float
    start_equity: float
    daily_pnl_pct: float
    halted: bool
    reason: str | None = None


class RiskGate:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._day_start_equity: float | None = None

    def snapshot(self, account: TradeAccount) -> RiskSnapshot:
        equity = float(account.equity)
        if self._day_start_equity is None:
            # Prefer broker last_equity (prior close) as daily baseline
            self._day_start_equity = float(account.last_equity or equity)

        start = self._day_start_equity
        daily_pnl_pct = 0.0 if start <= 0 else ((equity - start) / start) * 100.0
        halted = daily_pnl_pct <= -self.settings.max_daily_loss_pct
        reason = (
            f"Daily loss {daily_pnl_pct:.2f}% hit limit -{self.settings.max_daily_loss_pct}%"
            if halted
            else None
        )
        return RiskSnapshot(
            equity=equity,
            start_equity=start,
            daily_pnl_pct=daily_pnl_pct,
            halted=halted,
            reason=reason,
        )

    def position_qty(self, equity: float, price: float) -> int:
        if price <= 0 or equity <= 0:
            return 0
        dollars = equity * (self.settings.risk_per_position_pct / 100.0)
        qty = int(dollars // price)
        return max(qty, 0)

    def should_stop_out(self, position: Position) -> tuple[bool, str | None]:
        entry = float(position.avg_entry_price)
        current = float(position.current_price)
        if entry <= 0 or current <= 0:
            return False, None

        side = position.side.value if hasattr(position.side, "value") else str(position.side)
        if side == "long":
            pnl_pct = ((current - entry) / entry) * 100.0
        else:
            pnl_pct = ((entry - current) / entry) * 100.0

        if pnl_pct <= -self.settings.stop_loss_pct:
            return True, f"stop-loss {pnl_pct:.2f}%"
        if pnl_pct >= self.settings.take_profit_pct:
            return True, f"take-profit {pnl_pct:.2f}%"
        return False, None


def get_open_positions(trading: TradingClient) -> dict[str, Position]:
    positions = trading.get_all_positions()
    return {p.symbol: p for p in positions}
