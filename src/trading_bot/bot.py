from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from alpaca.trading.enums import PositionSide

from trading_bot.clients import make_data_client, make_screener_client, make_trading_client
from trading_bot.config import Settings
from trading_bot.executor import Executor
from trading_bot.journal import journal
from trading_bot.llm import decide_trades
from trading_bot.models import AccountView, CycleResult, PositionView, TargetView
from trading_bot.research import fetch_news
from trading_bot.risk import RiskGate, get_open_positions
from trading_bot.screener import fetch_trend_universe

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def market_is_open(trading) -> bool:
    clock = trading.get_clock()
    return bool(clock.is_open)


def get_account_view(settings: Settings) -> AccountView:
    trading = make_trading_client(settings)
    risk = RiskGate(settings)
    account = trading.get_account()
    snap = risk.snapshot(account)
    return AccountView(
        equity=snap.equity,
        cash=float(account.cash),
        buying_power=float(account.buying_power),
        portfolio_value=float(account.portfolio_value),
        daily_pnl_pct=snap.daily_pnl_pct,
        paper=settings.paper,
        market_open=market_is_open(trading),
    )


def get_position_views(settings: Settings) -> list[PositionView]:
    trading = make_trading_client(settings)
    positions = get_open_positions(trading)
    views: list[PositionView] = []
    for pos in positions.values():
        side = pos.side.value if hasattr(pos.side, "value") else str(pos.side)
        views.append(
            PositionView(
                symbol=pos.symbol,
                side=side,
                qty=float(pos.qty),
                market_value=float(pos.market_value),
                unrealized_pl=float(pos.unrealized_pl),
                unrealized_plpc=float(pos.unrealized_plpc) * 100.0,
                current_price=float(pos.current_price),
                avg_entry_price=float(pos.avg_entry_price),
            )
        )
    return sorted(views, key=lambda p: abs(p.market_value), reverse=True)


def preview_targets(settings: Settings) -> CycleResult:
    trading = make_trading_client(settings)
    screener = make_screener_client(settings)
    data = make_data_client(settings)
    universe = fetch_trend_universe(screener, trading, data, settings)
    pos_views = [p.__dict__ for p in get_position_views(settings)]
    news = fetch_news(settings, [m.symbol for m in universe[:12]] + [p["symbol"] for p in pos_views])
    decision = decide_trades(settings, universe, pos_views, news)
    by_sym = {m.symbol: m for m in universe}
    longs = [
        TargetView(
            symbol=s,
            side="long",
            price=by_sym[s].price,
            percent_change=by_sym[s].percent_change,
            source=by_sym[s].source,
            reason=decision.rationale,
        )
        for s in decision.longs
        if s in by_sym
    ]
    shorts = [
        TargetView(
            symbol=s,
            side="short",
            price=by_sym[s].price,
            percent_change=by_sym[s].percent_change,
            source=by_sym[s].source,
            reason=decision.rationale,
        )
        for s in decision.shorts
        if s in by_sym
    ]
    return CycleResult(
        ok=True,
        message="LLM preview" if decision.used_llm else "Momentum preview",
        longs=longs,
        shorts=shorts,
        llm_used=decision.used_llm,
        llm_rationale=decision.rationale,
        universe_size=len(universe),
    )


def run_once(settings: Settings) -> CycleResult:
    trading = make_trading_client(settings)
    screener = make_screener_client(settings)
    data = make_data_client(settings)
    risk = RiskGate(settings)
    executor = Executor(trading, settings)

    journal.add_llm_event("cycle_start", "Starting trade cycle")
    account = trading.get_account()
    snap = risk.snapshot(account)
    log.info(
        "Equity=$%.2f daily_pnl=%.2f%% paper=%s",
        snap.equity,
        snap.daily_pnl_pct,
        settings.paper,
    )
    journal.add_llm_event(
        "account",
        f"Equity ${snap.equity:,.2f} · daily PnL {snap.daily_pnl_pct:.2f}%",
        data={"equity": snap.equity, "daily_pnl_pct": snap.daily_pnl_pct},
    )

    if snap.halted:
        log.error("RISK HALT: %s — closing all positions", snap.reason)
        journal.add_llm_event("risk_halt", snap.reason or "Daily loss limit hit")
        if not settings.dry_run:
            trading.close_all_positions(cancel_orders=True)
        return CycleResult(ok=False, message=snap.reason or "Risk halt", halted=True)

    market_open = market_is_open(trading)
    if not market_open:
        now = datetime.now(ET).strftime("%Y-%m-%d %H:%M %Z")
        log.info("Market closed (%s). Screening + LLM only.", now)
        journal.add_llm_event("market", f"Market closed ({now}) — decisions only")

    # Hard risk exits first
    positions = get_open_positions(trading)
    for symbol, pos in list(positions.items()):
        stop, why = risk.should_stop_out(pos)
        if stop:
            qty = abs(int(float(pos.qty)))
            is_long = pos.side == PositionSide.LONG
            log.info("Exit %s (%s)", symbol, why)
            journal.add_llm_event("risk_exit", f"{symbol}: {why}")
            executor.close(symbol, qty, is_long=is_long)
            journal.add_trade(
                {
                    "symbol": symbol,
                    "side": "sell" if is_long else "buy",
                    "qty": qty,
                    "reason": why,
                    "source": "risk",
                }
            )

    journal.add_llm_event("screen", "Scanning most-actives + top movers")
    universe = fetch_trend_universe(screener, trading, data, settings)
    journal.add_llm_event(
        "universe",
        f"Built trend universe with {len(universe)} names",
        data={"symbols": [m.symbol for m in universe[:20]]},
    )
    pos_views = [
        {
            "symbol": p.symbol,
            "side": p.side.value if hasattr(p.side, "value") else str(p.side),
            "qty": float(p.qty),
            "unrealized_plpc": float(p.unrealized_plpc) * 100.0,
            "current_price": float(p.current_price),
        }
        for p in get_open_positions(trading).values()
    ]
    journal.add_llm_event("news", "Fetching headlines for movers + positions")
    news = fetch_news(
        settings,
        [m.symbol for m in universe[:15]] + [p["symbol"] for p in pos_views],
    )
    journal.add_llm_event("news_done", f"Loaded {len(news)} headlines")
    journal.add_llm_event("llm_call", "Asking model to pick longs/shorts from universe")
    decision = decide_trades(settings, universe, pos_views, news)
    journal.add_llm_event(
        "llm_decision",
        decision.rationale,
        data={
            "used_llm": decision.used_llm,
            "longs": decision.longs,
            "shorts": decision.shorts,
            "closes": decision.closes,
        },
    )
    by_sym = {m.symbol: m for m in universe}

    long_views = [
        TargetView(
            s,
            "long",
            by_sym[s].price,
            by_sym[s].percent_change,
            by_sym[s].source,
            decision.rationale,
        )
        for s in decision.longs
        if s in by_sym
    ]
    short_views = [
        TargetView(
            s,
            "short",
            by_sym[s].price,
            by_sym[s].percent_change,
            by_sym[s].source,
            decision.rationale,
        )
        for s in decision.shorts
        if s in by_sym
    ]
    log.info(
        "LLM=%s universe=%s LONG=%s SHORT=%s | %s",
        decision.used_llm,
        len(universe),
        decision.longs,
        decision.shorts,
        decision.rationale,
    )

    result = CycleResult(
        ok=True,
        message="Market closed — LLM/trend screening only",
        longs=long_views,
        shorts=short_views,
        llm_used=decision.used_llm,
        llm_rationale=decision.rationale,
        universe_size=len(universe),
    )
    if not market_open:
        journal.add_cycle(result.to_dict())
        return result

    journal.add_llm_event("risk_gate", "Applying size limits and rebalance rules")
    target_long = set(decision.longs)
    target_short = set(decision.shorts)
    positions = get_open_positions(trading)

    for symbol, pos in positions.items():
        is_long = pos.side == PositionSide.LONG
        keep = symbol in target_long if is_long else symbol in target_short
        if symbol in decision.closes or not keep:
            qty = abs(int(float(pos.qty)))
            log.info("Rebalance/LLM close %s", symbol)
            journal.add_llm_event("order", f"Close {symbol} x{qty}")
            executor.close(symbol, qty, is_long=is_long)
            journal.add_trade(
                {
                    "symbol": symbol,
                    "side": "sell" if is_long else "buy",
                    "qty": qty,
                    "reason": "rebalance/llm close",
                    "source": "llm" if decision.used_llm else "momentum",
                }
            )

    positions = get_open_positions(trading)

    for s in decision.longs:
        if s in positions or s not in by_sym:
            continue
        m = by_sym[s]
        qty = risk.position_qty(snap.equity, m.price)
        if qty <= 0:
            continue
        log.info("LLM LONG %s qty=%s (%.1f%%)", s, qty, m.percent_change)
        journal.add_llm_event("order", f"BUY {s} x{qty} ({m.percent_change:+.1f}%)")
        executor.buy(s, qty)
        journal.add_trade(
            {
                "symbol": s,
                "side": "buy",
                "qty": qty,
                "price": m.price,
                "percent_change": m.percent_change,
                "reason": decision.rationale,
                "source": "llm" if decision.used_llm else "momentum",
            }
        )

    for s in decision.shorts:
        if s in positions or s not in by_sym:
            continue
        m = by_sym[s]
        qty = risk.position_qty(snap.equity, m.price)
        if qty <= 0:
            continue
        log.info("LLM SHORT %s qty=%s (%.1f%%)", s, qty, m.percent_change)
        journal.add_llm_event("order", f"SHORT {s} x{qty} ({m.percent_change:+.1f}%)")
        executor.sell_short(s, qty)
        journal.add_trade(
            {
                "symbol": s,
                "side": "sell",
                "qty": qty,
                "price": m.price,
                "percent_change": m.percent_change,
                "reason": decision.rationale,
                "source": "llm" if decision.used_llm else "momentum",
            }
        )

    mode = "dry-run" if settings.dry_run else "live-paper" if settings.paper else "live"
    brain = "llm" if decision.used_llm else "momentum-fallback"
    result = CycleResult(
        ok=True,
        message=f"Cycle complete ({mode}, {brain})",
        longs=long_views,
        shorts=short_views,
        llm_used=decision.used_llm,
        llm_rationale=decision.rationale,
        universe_size=len(universe),
    )
    journal.add_llm_event("cycle_done", result.message)
    journal.add_cycle(result.to_dict())
    return result


def main() -> None:
    import os
    import time

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from trading_bot.config import load_settings

    settings = load_settings()
    if os.getenv("ONCE", "").lower() in {"1", "true", "yes"}:
        run_once(settings)
        return

    mode = "PAPER" if settings.paper else "LIVE"
    log.info(
        "Starting LLM trend bot [%s] poll=%ss dry_run=%s",
        mode,
        settings.poll_seconds,
        settings.dry_run,
    )
    while True:
        try:
            run_once(settings)
        except Exception:
            log.exception("Cycle failed")
        time.sleep(settings.poll_seconds)
