from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from alpaca.data.enums import DataFeed
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from trading_bot.config import Settings


_TF = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}


def fetch_bars(
    settings: Settings,
    symbol: str,
    timeframe: str = "5Min",
    limit: int = 120,
) -> list[dict[str, Any]]:
    client = StockHistoricalDataClient(settings.api_key, settings.secret_key)
    tf = _TF.get(timeframe, _TF["5Min"])
    end = datetime.now(timezone.utc)
    # Rough lookback window
    if timeframe.endswith("Day"):
        start = end - timedelta(days=max(limit + 5, 40))
    elif "Hour" in timeframe:
        start = end - timedelta(hours=max(limit + 5, 48))
    else:
        start = end - timedelta(minutes=max(limit * 5, 600))

    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=tf,
        start=start,
        end=end,
        limit=limit,
        feed=DataFeed.IEX,
    )
    barset = client.get_stock_bars(req)
    bars = barset.data.get(symbol.upper(), []) if hasattr(barset, "data") else []
    out: list[dict[str, Any]] = []
    for b in bars[-limit:]:
        ts = b.timestamp
        if isinstance(ts, datetime):
            t = int(ts.timestamp())
        else:
            t = int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())
        out.append(
            {
                "time": t,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
        )
    return out
