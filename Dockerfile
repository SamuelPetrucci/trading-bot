FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1
ENV AUTO_START=true
ENV ALPACA_PAPER_TRADE=true
ENV DRY_RUN=false

EXPOSE 8080

CMD ["uv", "run", "trading-dashboard"]
