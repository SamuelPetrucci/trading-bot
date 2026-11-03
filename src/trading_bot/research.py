from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from trading_bot.config import Settings

log = logging.getLogger(__name__)


@dataclass
class NewsItem:
    headline: str
    summary: str
    url: str
    source: str
    created_at: str
    symbols: list[str]


def research_links(symbol: str) -> dict[str, str]:
    s = symbol.upper()
    return {
        "yahoo": f"https://finance.yahoo.com/quote/{s}",
        "finviz": f"https://finviz.com/quote.ashx?t={s}",
        "tradingview": f"https://www.tradingview.com/symbols/{s}/",
        "sec": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={s}&type=&dateb=&owner=include&count=10",
        "news_search": f"https://news.google.com/search?q={s}%20stock",
    }


def make_news_client(settings: Settings) -> NewsClient:
    return NewsClient(api_key=settings.api_key, secret_key=settings.secret_key)


def fetch_news(
    settings: Settings,
    symbols: list[str],
    limit: int = 12,
) -> list[dict[str, Any]]:
    clean = sorted({s.upper() for s in symbols if s})
    if not clean:
        return []
    try:
        client = make_news_client(settings)
        result = client.get_news(
            NewsRequest(symbols=",".join(clean[:20]), limit=limit)
        )
        raw = result.data.get("news", []) if hasattr(result, "data") else []
        items: list[NewsItem] = []
        for n in raw:
            created = n.created_at
            if isinstance(created, datetime):
                created_s = created.isoformat()
            else:
                created_s = str(created or "")
            items.append(
                NewsItem(
                    headline=str(n.headline or ""),
                    summary=str(n.summary or ""),
                    url=str(n.url or ""),
                    source=str(n.source or ""),
                    created_at=created_s,
                    symbols=[str(x) for x in (n.symbols or [])],
                )
            )
        return [asdict(i) for i in items]
    except Exception:
        log.exception("News fetch failed")
        return []


def enrich_positions(
    settings: Settings,
    positions: list[dict[str, Any]],
    extra_symbols: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols = [p["symbol"] for p in positions]
    if extra_symbols:
        symbols.extend(extra_symbols)
    news = fetch_news(settings, symbols)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for item in news:
        for sym in item.get("symbols") or []:
            by_symbol.setdefault(sym, []).append(item)

    enriched = []
    for p in positions:
        sym = p["symbol"]
        enriched.append(
            {
                **p,
                "links": research_links(sym),
                "news": by_symbol.get(sym, [])[:4],
            }
        )
    return enriched, news
