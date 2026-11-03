from __future__ import annotations

import logging

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from trading_bot.config import Settings

log = logging.getLogger(__name__)


class Executor:
    def __init__(self, trading: TradingClient, settings: Settings) -> None:
        self.trading = trading
        self.settings = settings

    def buy(self, symbol: str, qty: int) -> None:
        self._submit(symbol, qty, OrderSide.BUY)

    def sell_short(self, symbol: str, qty: int) -> None:
        self._submit(symbol, qty, OrderSide.SELL)

    def close(self, symbol: str, qty: int, is_long: bool) -> None:
        side = OrderSide.SELL if is_long else OrderSide.BUY
        self._submit(symbol, qty, side)

    def _submit(self, symbol: str, qty: int, side: OrderSide) -> None:
        if qty <= 0:
            log.warning("Skip %s %s — qty=%s", side, symbol, qty)
            return
        if self.settings.dry_run:
            log.info("[DRY RUN] %s %s x%s", side.value, symbol, qty)
            return

        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        order = self.trading.submit_order(req)
        log.info(
            "Submitted %s %s x%s order_id=%s status=%s",
            side.value,
            symbol,
            qty,
            order.id,
            order.status,
        )
