const $ = (id) => document.getElementById(id);

let chartApi = null;
let areaSeries = null;

function money(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(n);
}

function pct(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || res.statusText);
  return data;
}

function avatar(symbol) {
  return (symbol || "??").slice(0, 3).toUpperCase();
}

function linkRow(links) {
  if (!links) return "";
  return `<div class="links">
    <a href="${links.yahoo}" target="_blank" rel="noopener">Yahoo</a>
    <a href="${links.finviz}" target="_blank" rel="noopener">Finviz</a>
    <a href="${links.tradingview}" target="_blank" rel="noopener">TV</a>
    <a href="${links.news_search}" target="_blank" rel="noopener">News</a>
  </div>`;
}

function currentRoute() {
  const hash = (location.hash || "#/portfolio").replace(/^#\/?/, "");
  return hash.split("?")[0] || "portfolio";
}

function showRoute(route) {
  const name = route || "portfolio";
  document.querySelectorAll(".page").forEach((p) => {
    p.classList.toggle("active", p.id === `page-${name}`);
  });
  document.querySelectorAll(".side-nav a, .dock button").forEach((el) => {
    el.classList.toggle("active", el.dataset.route === name);
  });
  if (name === "llm") refreshLlm().catch(() => {});
  if (name === "trades") refreshTrades().catch(() => {});
}

function renderBadges(s) {
  const llm = s.llm || {};
  $("badges").innerHTML = [
    `<span class="badge ${s.running ? "on" : "off"}">${s.running ? "RUNNING" : "STOPPED"}</span>`,
    `<span class="badge ${s.paper ? "warn" : "off"}">${s.paper ? "PAPER" : "LIVE"}</span>`,
    `<span class="badge ${s.dry_run ? "warn" : "on"}">${s.dry_run ? "DRY RUN" : "ORDERS ON"}</span>`,
    `<span class="badge ${s.account?.market_open ? "on" : "off"}">${s.account?.market_open ? "OPEN" : "CLOSED"}</span>`,
    `<span class="badge ${llm.configured ? (llm.used ? "on" : "warn") : "off"}">${llm.configured ? (llm.used ? "LLM ON" : "LLM READY") : "LLM OFF"}</span>`,
  ].join("");
}

function renderHero(s) {
  const a = s.account || {};
  $("equity").textContent = money(a.equity);
  const pill = $("daily-pill");
  const chg = a.daily_pnl_pct || 0;
  pill.textContent = `${pct(chg)} today`;
  pill.className = `pill ${chg >= 0 ? "" : "neg"}`.trim();
}

function renderLlmBox(s) {
  const llm = s.llm || {};
  if (!llm.configured) {
    $("llm-box").innerHTML = `<div class="hint">Add <code>LLM_API_KEY</code> to .env (OpenAI or xAI). Until then, momentum fallback still trades.</div>`;
    return;
  }
  $("llm-box").innerHTML = `
    <div class="llm-title">Current thesis · universe ${llm.universe_size || "—"}</div>
    <div class="llm-text">${llm.rationale || "No thesis yet — run a cycle."}</div>
  `;
}

function renderPositions(positions) {
  $("asset-count").textContent = String(positions?.length || 0);
  if (!positions?.length) {
    $("positions").innerHTML = `<div class="empty">No open positions</div>`;
    return;
  }
  $("positions").innerHTML = positions
    .map(
      (p) => `<div class="asset" data-symbol="${p.symbol}">
        <div class="avatar">${avatar(p.symbol)}</div>
        <div>
          <div class="name">${p.symbol} <span class="${p.side === "long" ? "side-long" : "side-short"}">${p.side}</span></div>
          <div class="meta">${p.qty} @ ${money(p.current_price)}</div>
          ${linkRow(p.links)}
        </div>
        <div class="right">
          <div class="usd">${money(p.market_value)}</div>
          <div class="chg ${p.unrealized_plpc >= 0 ? "pos" : "neg"}">${pct(p.unrealized_plpc)}</div>
        </div>
      </div>`
    )
    .join("");
}

function renderTargets(cycle) {
  const all = [...(cycle?.longs || []), ...(cycle?.shorts || [])];
  $("target-count").textContent = String(all.length);
  if (!all.length) {
    $("targets").innerHTML = `<div class="empty">No targets yet</div>`;
    return;
  }
  $("targets").innerHTML = all
    .map(
      (t) => `<div class="asset" data-symbol="${t.symbol}">
        <div class="avatar">${avatar(t.symbol)}</div>
        <div>
          <div class="name">${t.symbol} <span class="${t.side === "long" ? "side-long" : "side-short"}">${t.side}</span></div>
          <div class="meta">${t.source || "trend"} · ${money(t.price)}</div>
          ${linkRow(t.links)}
        </div>
        <div class="right">
          <div class="usd">${money(t.price)}</div>
          <div class="chg ${t.percent_change >= 0 ? "pos" : "neg"}">${pct(t.percent_change)}</div>
        </div>
      </div>`
    )
    .join("");
}

function renderNews(items) {
  if (!items?.length) {
    $("news").innerHTML = `<div class="empty">No news yet</div>`;
    return;
  }
  $("news").innerHTML = items
    .slice(0, 8)
    .map(
      (n) => `<article class="news-item">
        <a href="${n.url}" target="_blank" rel="noopener">${n.headline}</a>
        <div class="news-meta">${n.source || "news"} · ${(n.symbols || []).join(", ")}</div>
        <div class="news-summary">${n.summary || ""}</div>
      </article>`
    )
    .join("");
}

function renderTradeMeta(s) {
  const cycle = s.last_cycle || {};
  $("trade-details").innerHTML = `
    <div>Cash ${money(s.account?.cash)}</div>
    <div>Buying power ${money(s.account?.buying_power)}</div>
    <div>Longs ${(cycle.longs || []).map((t) => t.symbol).join(", ") || "—"}</div>
    <div>Shorts ${(cycle.shorts || []).map((t) => t.symbol).join(", ") || "—"}</div>
  `;
  $("uptime-status").innerHTML = `
    <div>Loop: <strong>${s.running ? "RUNNING" : "STOPPED"}</strong></div>
    <div>Mode: ${s.paper ? "paper" : "live"} · dry_run=${s.dry_run}</div>
    <div>Poll: ${s.poll_seconds}s</div>
    <div>Last run: ${s.last_run_at || "—"}</div>
  `;
}

function renderLogs(lines) {
  $("logs").textContent = (lines || []).join("\n") || "No logs yet";
  $("logs").scrollTop = $("logs").scrollHeight;
}

function collectSymbols(s) {
  const set = new Set();
  (s.positions || []).forEach((p) => set.add(p.symbol));
  const cycle = s.last_cycle || {};
  [...(cycle.longs || []), ...(cycle.shorts || [])].forEach((t) => set.add(t.symbol));
  if (!set.size) set.add("SPY");
  return [...set];
}

function syncSelects(symbols, preferred) {
  for (const id of ["chart-symbol", "trade-symbol"]) {
    const sel = $(id);
    const current = preferred || sel.value;
    sel.innerHTML = symbols.map((s) => `<option value="${s}">${s}</option>`).join("");
    if (symbols.includes(current)) sel.value = current;
  }
}

function ensureChart() {
  if (chartApi) return;
  const el = $("chart");
  chartApi = LightweightCharts.createChart(el, {
    layout: { background: { color: "transparent" }, textColor: "#8d9b92" },
    grid: { vertLines: { visible: false }, horzLines: { color: "rgba(36,48,42,0.55)" } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false },
    width: el.clientWidth,
    height: 180,
  });
  areaSeries = chartApi.addAreaSeries({
    lineColor: "#b6f36a",
    topColor: "rgba(182, 243, 106, 0.35)",
    bottomColor: "rgba(182, 243, 106, 0.02)",
    lineWidth: 2,
  });
  window.addEventListener("resize", () => {
    if (chartApi) chartApi.applyOptions({ width: el.clientWidth });
  });
}

async function loadChart(symbol) {
  ensureChart();
  const tf = $("chart-tf").value;
  const data = await api(`/api/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}&limit=150`);
  areaSeries.setData((data.bars || []).map((b) => ({ time: b.time, value: b.close })));
  chartApi.timeScale().fitContent();
  $("chart-symbol").value = symbol;
  $("trade-symbol").value = symbol;
  $("trade-side-chip").textContent = symbol;
}

function wireAssetClicks() {
  document.querySelectorAll(".asset[data-symbol]").forEach((el) => {
    el.onclick = () => loadChart(el.dataset.symbol).catch((e) => toast(e.message));
  });
}

async function refreshLlm() {
  const data = await api("/api/llm/activity?limit=60");
  $("llm-feed").innerHTML = (data.events || [])
    .map(
      (e) => `<div class="feed-item">
        <div class="stage">${e.stage}</div>
        <div class="when">${e.ts || ""}</div>
        <div class="detail">${e.detail || ""}</div>
      </div>`
    )
    .join("") || `<div class="empty">No LLM activity yet — run a cycle</div>`;

  $("llm-cycles").innerHTML = (data.cycles || [])
    .map((c) => {
      const longs = (c.longs || []).map((t) => t.symbol || t).join(", ") || "—";
      const shorts = (c.shorts || []).map((t) => t.symbol || t).join(", ") || "—";
      return `<div class="feed-item">
        <div class="stage">${c.llm_used ? "LLM cycle" : "Momentum cycle"}</div>
        <div class="when">${c.ts || ""}</div>
        <div class="detail">${c.llm_rationale || c.message || ""}</div>
        <div class="news-meta">Long ${longs} · Short ${shorts}</div>
      </div>`;
    })
    .join("") || `<div class="empty">No cycles logged yet</div>`;
}

async function refreshTrades() {
  const data = await api("/api/trades/summary");
  const s = data.summary || {};
  $("trade-metrics").innerHTML = `
    <div class="metric"><div class="label">Trades</div><div class="value">${s.total_trades || 0}</div></div>
    <div class="metric"><div class="label">Buys</div><div class="value">${s.buys || 0}</div></div>
    <div class="metric"><div class="label">Sells/shorts</div><div class="value">${s.sells || 0}</div></div>
    <div class="metric"><div class="label">LLM cycles</div><div class="value">${s.llm_cycles || 0}/${s.cycles || 0}</div></div>
  `;
  const top = (s.top_symbols || []).map((x) => `${x.symbol} (${x.count})`).join(", ") || "—";
  $("trade-summary").innerHTML = `
    <div class="llm-title">Desk summary</div>
    <div class="llm-text">${s.latest_rationale || s.latest_cycle_message || "No summarized thesis yet."}</div>
    <div class="news-meta" style="margin-top:8px">Most traded: ${top}</div>
  `;
  $("trade-journal").innerHTML = (s.recent_trades || [])
    .map(
      (t) => `<div class="feed-item">
        <div class="stage">${t.side} ${t.symbol}</div>
        <div class="when">${t.ts || ""} · ${t.source || ""}</div>
        <div class="detail">qty ${t.qty || "—"} ${t.price ? "@ " + money(t.price) : ""}</div>
        <div class="news-meta">${t.reason || ""}</div>
      </div>`
    )
    .join("") || `<div class="empty">No journal trades yet</div>`;

  $("broker-orders").innerHTML = (s.broker_orders || [])
    .map(
      (o) => `<div class="feed-item">
        <div class="stage">${o.side} ${o.symbol}</div>
        <div class="when">${o.submitted_at || ""} · ${o.status}</div>
        <div class="detail">qty ${o.qty} filled ${o.filled_qty}${o.filled_avg_price ? " @ " + money(o.filled_avg_price) : ""}</div>
      </div>`
    )
    .join("") || `<div class="empty">${s.broker_orders_error || "No broker orders"}</div>`;
}

async function refresh() {
  const s = await api("/api/status");
  renderHero(s);
  renderBadges(s);
  renderLlmBox(s);
  renderPositions(s.positions);
  renderTargets(s.last_cycle);
  renderNews(s.news);
  renderTradeMeta(s);
  renderLogs(s.logs);
  $("dry-run").checked = !!s.dry_run;
  if (document.activeElement !== $("poll")) $("poll").value = s.poll_seconds;
  $("btn-start").disabled = !!s.running;
  $("btn-stop").disabled = !s.running;
  $("btn-start-2").disabled = !!s.running;
  $("btn-stop-2").disabled = !s.running;

  const symbols = collectSymbols(s);
  const prev = $("chart-symbol").value;
  syncSelects(symbols, prev);
  if (!chartApi || !symbols.includes(prev)) {
    await loadChart(symbols[0]).catch(() => {});
  }
  wireAssetClicks();

  if (currentRoute() === "llm") await refreshLlm().catch(() => {});
  if (currentRoute() === "trades") await refreshTrades().catch(() => {});
  return s;
}

async function bind() {
  window.addEventListener("hashchange", () => showRoute(currentRoute()));
  document.querySelectorAll("[data-route]").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (el.tagName === "BUTTON") {
        e.preventDefault();
        location.hash = `#/${el.dataset.route}`;
      }
    });
  });

  $("btn-refresh").onclick = () => refresh().then(() => toast("Updated"));
  const start = async () => {
    toast((await api("/api/start", { method: "POST" })).message || "Started");
    await refresh();
  };
  const stop = async () => {
    toast((await api("/api/stop", { method: "POST" })).message || "Stopped");
    await refresh();
  };
  $("btn-start").onclick = start;
  $("btn-stop").onclick = stop;
  $("btn-start-2").onclick = start;
  $("btn-stop-2").onclick = stop;
  $("btn-once").onclick = async () => {
    toast("Running LLM cycle…");
    const r = await api("/api/once", { method: "POST" });
    toast(r.ok ? r.cycle?.message || "Done" : r.message || "Failed");
    await refresh();
    if (currentRoute() === "llm") await refreshLlm();
    if (currentRoute() === "trades") await refreshTrades();
  };
  $("btn-preview").onclick = async () => {
    const r = await api("/api/preview", { method: "POST" });
    toast(r.ok ? "Preview ready" : r.message || "Failed");
    await refresh();
  };
  $("btn-flatten").onclick = async () => {
    if (!confirm("Close all positions?")) return;
    toast((await api("/api/flatten", { method: "POST" })).message || "Flattened");
    await refresh();
  };
  $("dry-run").onchange = async (e) => {
    const r = await api("/api/dry-run", {
      method: "POST",
      body: JSON.stringify({ enabled: e.target.checked }),
    });
    toast(r.dry_run ? "Dry run ON" : "Orders ON");
    await refresh();
  };
  $("poll").onchange = async (e) => {
    const r = await api("/api/poll", {
      method: "POST",
      body: JSON.stringify({ seconds: Number(e.target.value) }),
    });
    toast(`Poll = ${r.poll_seconds}s`);
  };
  $("chart-symbol").onchange = () => loadChart($("chart-symbol").value).catch((e) => toast(e.message));
  $("chart-tf").onchange = () => loadChart($("chart-symbol").value).catch((e) => toast(e.message));
  $("trade-symbol").onchange = () => loadChart($("trade-symbol").value).catch((e) => toast(e.message));

  if (!location.hash) location.hash = "#/portfolio";
  showRoute(currentRoute());
  await refresh();
  setInterval(() => refresh().catch(() => {}), 8000);
}

bind().catch((err) => toast(err.message || "Failed to load"));
