# Crypto Ledger Sandbox

Production-style backend sandbox for simulated crypto trading.

## Goals
- Double-entry ledger and auditable balance changes
- Available and locked balances
- Idempotent order submission
- Asynchronous events with RabbitMQ
- PostgreSQL transactions and concurrency-safe workflows
- Redis cache and rate-limit foundations
- Docker Compose development environment
- No real funds, exchange API keys, or live trading

## Current services
- FastAPI
- PostgreSQL
- Redis
- RabbitMQ Management UI

## Run
```bash
docker compose up --build
```

- API docs: http://localhost:8000/docs
- RabbitMQ management: http://localhost:15672
