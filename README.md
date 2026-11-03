# Momentum long/short bot (Alpaca paper)

Buys strong gainers and shorts weak losers using Alpaca market movers, with filters and risk limits.

## Setup

```powershell
copy .env.example .env
# put your Alpaca PAPER keys in .env
```

## Run bot (CLI)

```powershell
# one cycle (safe first test)
$env:ONCE="true"; uv run python -m trading_bot

# continuous loop every 5 minutes
uv run python -m trading_bot
```

## Dashboard API (must keep running on this PC)

```powershell
uv run trading-dashboard
```

Local UI also works at `http://127.0.0.1:8787` (user `trader` + `DASHBOARD_PASSWORD`).

## Vercel control app

Vercel hosts the UI. Your PC still runs the trader API.

1. Start the bot API: `uv run trading-dashboard`
2. Expose it with a tunnel (Cloudflare Tunnel / ngrok), e.g. `https://abc.ngrok.app`
3. In `dashboard/`:

```powershell
cd dashboard
copy .env.example .env.local
# set BOT_API_URL=https://your-tunnel
# set BOT_API_TOKEN to match DASHBOARD_TOKEN in the root .env
npm run dev
```

4. Deploy UI:

```powershell
cd dashboard
npx vercel
# set env on Vercel: BOT_API_URL, BOT_API_TOKEN
```

Dry run (no orders): set `DRY_RUN=true` in `.env` or toggle in the dashboard.

## Multi-page desk

Open http://127.0.0.1:8787

- `#/portfolio` — balance, chart, positions, news
- `#/llm` — live LLM activity feed + cycle thesis
- `#/trades` — trade summary, journal, broker orders
- `#/control` — start/stop/run cycle
- `#/uptime` — 24/7 instructions

## Run around the clock

The bot only trades while the Python process is running.

```powershell
# auto-restart loop (keep PC awake)
powershell -ExecutionPolicy Bypass -File .\scripts\run-24-7.ps1

# or install a login Scheduled Task (Admin once)
powershell -ExecutionPolicy Bypass -File .\scripts\install-task.ps1
Start-ScheduledTask -TaskName TradingBotDesk
```

For true always-on without your laptop: host the bot API on a small VPS and point the Vercel UI `BOT_API_URL` at it. Set `AUTO_START=true` in `.env`.

## Deploy on Render

1. Go to [render.com](https://render.com) → **New** → **Blueprint** (or **Web Service**).
2. Connect GitHub repo `SamuelPetrucci/trading-bot`.
3. If using Blueprint, Render reads `render.yaml`.  
   If using Web Service manually:
   - **Runtime:** Docker
   - **Dockerfile path:** `./Dockerfile`
   - **Instance type:** Free
4. Set environment variables:

```text
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_PAPER_TRADE=true
GROQ_API_KEY=...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=qwen/qwen3.8-27b
AUTO_START=true
DRY_RUN=false
DASHBOARD_HOST=0.0.0.0
```

5. Deploy → open the `.onrender.com` URL → check `/api/health`.

**Important (Free plan):** the service **sleeps after ~15 minutes idle**, which stops the trading loop. To keep it awake, ping `/api/health` every 10 minutes (e.g. [cron-job.org](https://cron-job.org)), or upgrade to a paid always-on instance.

## Deploy on Railway

1. Push this repo to GitHub.
2. In [Railway](https://railway.app) → **New Project** → **Deploy from GitHub** → select this repo.
3. Add the same env vars as above (Railway sets `PORT` automatically).
4. Open the public URL → `/api/health`.

## Strategy

- Rank most-active liquid stocks by today's move
- Long up to 3 moderate winners; short up to 3 easy-to-borrow losers
- Filters: price ≥ $15, move between 2–25% (skips penny pumps)
- ~2% equity per position, 4% stop / 8% take-profit
- Halt + flatten if daily loss ≥ 3%

This is momentum following, not future prediction. Paper first.
