from __future__ import annotations

from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from trading_bot.config import Settings


def make_trading_client(settings: Settings) -> TradingClient:
    return TradingClient(
        api_key=settings.api_key,
        secret_key=settings.secret_key,
        paper=settings.paper,
    )


def make_screener_client(settings: Settings) -> ScreenerClient:
    return ScreenerClient(
        api_key=settings.api_key,
        secret_key=settings.secret_key,
    )


def make_data_client(settings: Settings) -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=settings.api_key,
        secret_key=settings.secret_key,
    )
