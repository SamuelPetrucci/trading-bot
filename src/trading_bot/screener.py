from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from alpaca.common.exceptions import APIError
from alpaca.data.enums import MarketType, MostActivesBy
from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import MarketMoversRequest, MostActivesRequest, StockSnapshotRequest
from alpaca.trading.client import TradingClient

from trading_bot.config import Settings

log = logging.getLogger(__name__)

_SKIP_SYMBOL = re.compile(r"(\.WS$|W$|R$|/)", re.IGNORECASE)


@dataclass(frozen=True)
class Mover:
    symbol: str
    price: float
    percent_change: float
    change: float
    side: str  # "long" or "short"
    source: str = "active"  # active | gainer | loser


def _is_clean_symbol(symbol: str) -> bool:
    if not symbol or len(symbol) > 5:
        return False
    if _SKIP_SYMBOL.search(symbol):
        return False
    return symbol.isalpha()


def _lookup_asset(trading: TradingClient, symbol: str):
    try:
        return trading.get_asset(symbol)
    except APIError as exc:
        log.debug("Asset lookup failed for %s: %s", symbol, exc)
        return None
    except Exception as exc:
        log.debug("Asset lookup error for %s: %s", symbol, exc)
        return None


def _day_change_pct(snapshot) -> tuple[float, float] | None:
    try:
        prev = float(snapshot.previous_daily_bar.close)
        last = float(snapshot.daily_bar.close)
        if snapshot.latest_trade is not None:
            last = float(snapshot.latest_trade.price)
        if prev <= 0:
            return None
        pct = ((last - prev) / prev) * 100.0
        return last, pct
    except Exception:
        return None


def _filter_mover(
    trading: TradingClient,
    settings: Settings,
    symbol: str,
    price: float,
    pct: float,
    source: str,
) -> Mover | None:
    if not _is_clean_symbol(symbol):
        return None
    if price < settings.min_price:
        return None
    if abs(pct) < settings.min_pct_move:
        return None
    if abs(pct) > settings.max_pct_move:
        return None

    asset = _lookup_asset(trading, symbol)
    if asset is None or not asset.tradable:
        return None

    side = "long" if pct > 0 else "short"
    if side == "short":
        if not getattr(asset, "shortable", False):
            return None
        if not getattr(asset, "easy_to_borrow", False):
            return None

    return Mover(
        symbol=symbol,
        price=price,
        percent_change=pct,
        change=price * pct / 100.0,
        side=side,
        source=source,
    )


def fetch_trend_universe(
    screener: ScreenerClient,
    trading: TradingClient,
    data: StockHistoricalDataClient,
    settings: Settings,
) -> list[Mover]:
    """Merge most-actives + top gainers/losers into a trend universe for the LLM."""
    symbols: dict[str, str] = {}

    actives = screener.get_most_actives(
        MostActivesRequest(top=settings.movers_top, by=MostActivesBy.VOLUME)
    )
    for a in actives.most_actives:
        sym = str(a.symbol)
        if _is_clean_symbol(sym):
            symbols[sym] = "active"

    movers = screener.get_market_movers(
        MarketMoversRequest(top=min(settings.movers_top, 20), market_type=MarketType.STOCKS)
    )
    for g in movers.gainers:
        sym = str(g.symbol)
        if _is_clean_symbol(sym):
            symbols.setdefault(sym, "gainer")
    for loser in movers.losers:
        sym = str(loser.symbol)
        if _is_clean_symbol(sym):
            symbols.setdefault(sym, "loser")

    if not symbols:
        return []

    snapshots = data.get_stock_snapshot(
        StockSnapshotRequest(symbol_or_symbols=list(symbols.keys()))
    )

    scored: list[Mover] = []
    for symbol, source in symbols.items():
        snap = snapshots.get(symbol)
        if snap is None:
            continue
        ch = _day_change_pct(snap)
        if ch is None:
            continue
        price, pct = ch
        m = _filter_mover(trading, settings, symbol, price, pct, source)
        if m:
            scored.append(m)

    # Rank: strongest upside first, then weakest downside
    scored.sort(key=lambda m: m.percent_change, reverse=True)
    return scored


def fetch_candidates(
    screener: ScreenerClient,
    trading: TradingClient,
    data: StockHistoricalDataClient,
    settings: Settings,
) -> tuple[list[Mover], list[Mover]]:
    universe = fetch_trend_universe(screener, trading, data, settings)
    longs = [m for m in universe if m.side == "long"][: settings.long_slots]
    shorts = sorted(
        [m for m in universe if m.side == "short"],
        key=lambda m: m.percent_change,
    )[: settings.short_slots]
    return longs, shorts
