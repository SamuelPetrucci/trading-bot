"use client";

import { useCallback, useEffect, useState } from "react";

type Links = {
  yahoo?: string;
  finviz?: string;
  tradingview?: string;
  news_search?: string;
  sec?: string;
};

type NewsItem = {
  headline: string;
  summary: string;
  url: string;
  source: string;
  created_at: string;
  symbols: string[];
};

type Target = {
  symbol: string;
  side: string;
  price: number;
  percent_change: number;
  links?: Links;
};

type Position = {
  symbol: string;
  side: string;
  qty: number;
  current_price: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  links?: Links;
  news?: NewsItem[];
};

type Status = {
  running: boolean;
  dry_run: boolean;
  paper: boolean;
  poll_seconds: number;
  last_cycle?: {
    message?: string;
    longs?: Target[];
    shorts?: Target[];
  } | null;
  account?: {
    equity: number;
    cash: number;
    buying_power: number;
    daily_pnl_pct: number;
    market_open: boolean;
  } | null;
  positions?: Position[];
  news?: NewsItem[];
  logs?: string[];
  llm?: {
    configured?: boolean;
    used?: boolean;
    rationale?: string;
    universe_size?: number;
  };
};

function LinkRow({ links }: { links?: Links }) {
  if (!links) return null;
  return (
    <div className="links">
      <a href={links.yahoo} target="_blank" rel="noreferrer">
        Yahoo
      </a>
      <a href={links.finviz} target="_blank" rel="noreferrer">
        Finviz
      </a>
      <a href={links.tradingview} target="_blank" rel="noreferrer">
        TradingView
      </a>
      <a href={links.news_search} target="_blank" rel="noreferrer">
        Google News
      </a>
      <a href={links.sec} target="_blank" rel="noreferrer">
        SEC
      </a>
    </div>
  );
}

function money(n?: number) {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(n);
}

function pct(n?: number) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

async function api(path: string, options: RequestInit = {}) {
  const res = await fetch(`/api/bot/${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.message || data.detail || res.statusText);
  }
  return data;
}

export default function Home() {
  const [status, setStatus] = useState<Status | null>(null);
  const [targets, setTargets] = useState<Status["last_cycle"]>(null);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const flash = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(""), 2600);
  };

  const refresh = useCallback(async () => {
    try {
      const s = (await api("status")) as Status;
      setStatus(s);
      setTargets(s.last_cycle || null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reach bot API");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const run = async (fn: () => Promise<void>, okMsg?: string) => {
    setBusy(true);
    try {
      await fn();
      if (okMsg) flash(okMsg);
      await refresh();
    } catch (err) {
      flash(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const longs = targets?.longs || [];
  const shorts = targets?.shorts || [];
  const positions = status?.positions || [];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <h1>Desk</h1>
          <p>Vercel control panel → your bot API</p>
        </div>
        <div className="badges">
          <span className={`badge ${status?.running ? "on" : "off"}`}>
            {status?.running ? "RUNNING" : "STOPPED"}
          </span>
          <span className={`badge ${status?.paper ? "warn" : "off"}`}>
            {status?.paper ? "PAPER" : "LIVE"}
          </span>
          <span className={`badge ${status?.dry_run ? "warn" : "on"}`}>
            {status?.dry_run ? "DRY RUN" : "ORDERS ON"}
          </span>
          <span className={`badge ${status?.account?.market_open ? "on" : "off"}`}>
            {status?.account?.market_open ? "MARKET OPEN" : "MARKET CLOSED"}
          </span>
        </div>
      </header>

      {error ? (
        <div className="error-banner span-12">
          Bot API unreachable: {error}. Keep `uv run trading-dashboard` running and set
          `BOT_API_URL` to a public tunnel URL.
        </div>
      ) : null}

      <section className="grid">
        <article className="card span-8">
          <h2>Account</h2>
          <div className="metrics">
            <div className="metric">
              <div className="label">Equity</div>
              <div className="value">{money(status?.account?.equity)}</div>
            </div>
            <div className="metric">
              <div className="label">Buying power</div>
              <div className="value">{money(status?.account?.buying_power)}</div>
            </div>
            <div className="metric">
              <div className="label">Cash</div>
              <div className="value">{money(status?.account?.cash)}</div>
            </div>
            <div className="metric">
              <div className="label">Daily P/L</div>
              <div
                className={`value ${(status?.account?.daily_pnl_pct || 0) >= 0 ? "pos" : "neg"}`}
              >
                {pct(status?.account?.daily_pnl_pct)}
              </div>
            </div>
          </div>
          <div className="llm-box" style={{ marginTop: 14 }}>
            <div className="llm-title">
              {status?.llm?.configured
                ? status?.llm?.used
                  ? "LLM thesis"
                  : "LLM ready"
                : "LLM offline"}{" "}
              · universe {status?.llm?.universe_size || "—"}
            </div>
            <div className="llm-text">
              {status?.llm?.rationale ||
                (status?.llm?.configured
                  ? "Run once / start loop for a trend thesis."
                  : "Set LLM_API_KEY on the bot host to let the model dictate trades.")}
            </div>
          </div>
        </article>

        <article className="card span-4">
          <h2>Controls</h2>
          <div className="controls">
            <div className="row">
              <button
                className="primary"
                disabled={busy || !!status?.running}
                onClick={() =>
                  run(async () => {
                    const r = await api("start", { method: "POST" });
                    flash(r.message || "Started");
                  })
                }
              >
                Start loop
              </button>
              <button
                disabled={busy || !status?.running}
                onClick={() =>
                  run(async () => {
                    const r = await api("stop", { method: "POST" });
                    flash(r.message || "Stopped");
                  })
                }
              >
                Stop
              </button>
            </div>
            <div className="row">
              <button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    flash("Running cycle…");
                    const r = await api("once", { method: "POST" });
                    flash(r.cycle?.message || r.message || "Done");
                  })
                }
              >
                Run once
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const r = await api("preview", { method: "POST" });
                    setTargets(r.cycle);
                    flash("Targets refreshed");
                  })
                }
              >
                Preview targets
              </button>
            </div>
            <div className="row">
              <button
                className="danger"
                disabled={busy}
                onClick={() => {
                  if (!confirm("Close all positions and cancel open orders?")) return;
                  run(async () => {
                    const r = await api("flatten", { method: "POST" });
                    flash(r.message || "Flattened");
                  });
                }}
              >
                Flatten all
              </button>
            </div>
            <label className="switch">
              <span>Dry run (no orders)</span>
              <input
                type="checkbox"
                checked={!!status?.dry_run}
                onChange={(e) =>
                  run(async () => {
                    await api("dry-run", {
                      method: "POST",
                      body: JSON.stringify({ enabled: e.target.checked }),
                    });
                    flash(e.target.checked ? "Dry run ON" : "Orders ON");
                  })
                }
              />
            </label>
            <label className="switch">
              <span>Poll seconds</span>
              <input
                type="number"
                min={30}
                max={3600}
                step={30}
                defaultValue={status?.poll_seconds || 300}
                onBlur={(e) =>
                  run(async () => {
                    const seconds = Number(e.target.value);
                    const r = await api("poll", {
                      method: "POST",
                      body: JSON.stringify({ seconds }),
                    });
                    flash(`Poll = ${r.poll_seconds}s`);
                  })
                }
              />
            </label>
          </div>
        </article>

        <article className="card span-6">
          <h2>Positions</h2>
          {!positions.length ? (
            <div className="empty">No open positions</div>
          ) : (
            positions.map((p) => (
              <div className="pos-block" key={`${p.symbol}-${p.side}`}>
                <div>
                  <strong>{p.symbol}</strong>{" "}
                  <span className={p.side === "long" ? "side-long" : "side-short"}>
                    {p.side}
                  </span>{" "}
                  · {p.qty} @ {money(p.current_price)}
                </div>
                <div className={p.unrealized_pl >= 0 ? "pos" : "neg"}>
                  {money(p.unrealized_pl)} ({pct(p.unrealized_plpc)})
                </div>
                <LinkRow links={p.links} />
                {(p.news || []).slice(0, 2).map((n) => (
                  <div className="news-meta" key={n.url}>
                    <a href={n.url} target="_blank" rel="noreferrer">
                      {n.headline}
                    </a>
                  </div>
                ))}
              </div>
            ))
          )}
        </article>

        <article className="card span-6">
          <h2>Targets</h2>
          {!longs.length && !shorts.length ? (
            <div className="empty">No targets yet — run preview or a cycle</div>
          ) : (
            <>
              {[...longs, ...shorts].map((t) => (
                <div className="pos-block" key={`${t.side}-${t.symbol}`}>
                  <div>
                    <strong>{t.symbol}</strong>{" "}
                    <span className={t.side === "long" ? "side-long" : "side-short"}>
                      {t.side}
                    </span>{" "}
                    · {money(t.price)} ·{" "}
                    <span className={t.percent_change >= 0 ? "pos" : "neg"}>
                      {pct(t.percent_change)}
                    </span>
                  </div>
                  <LinkRow links={t.links} />
                </div>
              ))}
              <p className="hint" style={{ marginTop: 10 }}>
                {targets?.message || ""}
              </p>
            </>
          )}
        </article>

        <article className="card span-12">
          <h2>News & research</h2>
          {!(status?.news || []).length ? (
            <div className="empty">No news yet — open a position or run a cycle</div>
          ) : (
            <div className="news-list">
              {(status?.news || []).slice(0, 10).map((n) => (
                <article className="news-item" key={`${n.url}-${n.headline}`}>
                  <a href={n.url} target="_blank" rel="noreferrer">
                    {n.headline}
                  </a>
                  <div className="news-meta">
                    {n.source || "news"} · {(n.symbols || []).join(", ")} · {n.created_at}
                  </div>
                  <div className="news-summary">{n.summary}</div>
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="card span-12">
          <h2>Logs</h2>
          <pre className="logs">{(status?.logs || []).join("\n") || "No logs yet"}</pre>
        </article>
      </section>

      <div className={`toast ${toast ? "show" : ""}`}>{toast}</div>
    </div>
  );
}
