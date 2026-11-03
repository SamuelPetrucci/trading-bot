from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from trading_bot.config import Settings
from trading_bot.screener import Mover

log = logging.getLogger(__name__)


@dataclass
class LlmDecision:
    longs: list[str]
    shorts: list[str]
    closes: list[str]
    rationale: str
    used_llm: bool
    raw: dict[str, Any] | None = None


def _load_env() -> None:
    # Ensure .env is applied even if this module is imported before config.load_settings()
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except Exception:
        pass


def llm_configured() -> bool:
    _load_env()
    return bool(
        os.getenv("GROQ_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("XAI_API_KEY", "").strip()
    )


def _client_settings() -> tuple[str, str, str]:
    _load_env()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    api_key = (
        groq_key
        or os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("XAI_API_KEY", "").strip()
    )
    explicit_base = (
        os.getenv("LLM_BASE_URL", "").strip()
        or os.getenv("OPENAI_BASE_URL", "").strip()
    )
    # Auto-route: Groq keys (gsk_...) or GROQ_API_KEY → Groq OpenAI-compatible API
    if groq_key or api_key.startswith("gsk_"):
        base_url = explicit_base or "https://api.groq.com/openai/v1"
        # Current Groq free-tier chat models vary by account; qwen is widely available
        default_model = "qwen/qwen3.8-27b"
    elif "x.ai" in (explicit_base or ""):
        base_url = explicit_base
        default_model = "grok-2-latest"
    else:
        base_url = explicit_base or "https://api.openai.com/v1"
        default_model = "gpt-4o-mini"
    model = os.getenv("LLM_MODEL", "").strip() or default_model
    return api_key, base_url, model


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def decide_trades(
    settings: Settings,
    universe: list[Mover],
    positions: list[dict[str, Any]],
    news: list[dict[str, Any]],
) -> LlmDecision:
    """
    Ask an LLM to pick longs/shorts from the trend universe.
    Falls back to top momentum ranks if LLM is unavailable.
    """
    fallback_longs = [m.symbol for m in universe if m.side == "long"][: settings.long_slots]
    fallback_shorts = [m.symbol for m in universe if m.side == "short"][: settings.short_slots]
    fallback = LlmDecision(
        longs=fallback_longs,
        shorts=fallback_shorts,
        closes=[],
        rationale="Fallback momentum ranks (LLM unavailable or failed)",
        used_llm=False,
    )

    if not llm_configured():
        return fallback

    api_key, base_url, model = _client_settings()
    if not api_key:
        return fallback

    universe_payload = [
        {
            "symbol": m.symbol,
            "price": m.price,
            "percent_change": round(m.percent_change, 2),
            "bias": m.side,
        }
        for m in universe
    ]
    news_payload = [
        {
            "headline": n.get("headline"),
            "symbols": n.get("symbols"),
            "summary": (n.get("summary") or "")[:240],
        }
        for n in news[:8]
    ]

    system = (
        "You are a disciplined equity trading strategist for a paper-trading bot. "
        "Pick liquid momentum names that are trending now. Prefer strong volume leaders "
        "and fast growers, avoid already-parabolic pumps, low-quality junk, and overcrowded "
        "illiquid names. Short only easy-to-borrow weak names. "
        "Respond with JSON only."
    )
    user = {
        "task": "Select trades for this cycle",
        "constraints": {
            "max_longs": settings.long_slots,
            "max_shorts": settings.short_slots,
            "min_price": settings.min_price,
            "min_pct_move": settings.min_pct_move,
            "max_pct_move": settings.max_pct_move,
            "only_choose_from_universe": True,
        },
        "universe": universe_payload,
        "open_positions": positions,
        "recent_news": news_payload,
        "output_schema": {
            "longs": ["SYMBOL"],
            "shorts": ["SYMBOL"],
            "closes": ["SYMBOL"],
            "rationale": "one short sentence",
        },
    }

    try:
        from openai import OpenAI

        # Groq free OTPM is often ~1000; omit max_tokens and the API reserves ~2k.
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "400"))
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        data = _extract_json(content)
        allowed = {m.symbol for m in universe}
        longs = [s.upper() for s in data.get("longs", []) if str(s).upper() in allowed][
            : settings.long_slots
        ]
        shorts = [
            s.upper() for s in data.get("shorts", []) if str(s).upper() in allowed
        ][: settings.short_slots]
        # Prevent same symbol both sides
        shorts = [s for s in shorts if s not in longs]
        closes = [str(s).upper() for s in data.get("closes", [])]
        rationale = str(data.get("rationale") or "LLM selected trend names")
        log.info("LLM picks longs=%s shorts=%s closes=%s", longs, shorts, closes)
        return LlmDecision(
            longs=longs or fallback_longs,
            shorts=shorts or fallback_shorts,
            closes=closes,
            rationale=rationale,
            used_llm=True,
            raw=data,
        )
    except Exception:
        log.exception("LLM decision failed; using momentum fallback")
        return fallback
