# Betting Platform

Live football betting bot with Poisson/Dixon-Coles models, entry-only strategy, and SvelteKit dashboard.

## Quick Start

```bash
# Backend
cd backend
pip install uv
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (dev)
cd frontend
npm install
npm run dev
```

## Features

- **Poisson/Dixon-Coles models** trained on 5,256 historical matches
- **Live momentum scoring** with xG, shots, possession tracking
- **Entry-only strategy** — no exits, ride to final whistle
- **Kelly criterion staking** with risk management
- **Multi-exchange support** — Betfair (delayed free) + Matchbook (free tier)
- **SvelteKit dashboard** — dark theme, real-time polling, charts

## API Documentation

Visit `http://localhost:8000/docs` for Swagger UI.

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp backend/.env.example backend/.env
```

## License

MIT
