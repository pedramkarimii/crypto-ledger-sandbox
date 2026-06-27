# Crypto Ledger Sandbox

Production-style backend sandbox for simulated crypto trading. It is designed to demonstrate financial-state integrity, idempotent APIs, asynchronous event delivery, and repeatable local development.

> This project does not connect to real exchanges, accept API keys, or handle real funds.

## Highlights

- JWT authentication with protected wallet and order endpoints
- PostgreSQL-backed wallets with separate available and locked balances
- Double-entry ledger records for sandbox funding, order reservation, and cancellation release
- Idempotent sandbox funding and order submission
- Order lifecycle: create/reserve funds, cancel/release funds, and safe replay handling
- Transactional outbox for `order.created` and `order.canceled`
- Durable RabbitMQ topic exchange with persistent messages and publisher confirms
- Separate outbox relay worker with retry metadata in PostgreSQL
- Docker Compose environment with FastAPI, PostgreSQL, Redis, RabbitMQ, and the optional worker
- GitHub Actions quality gate for migrations, linting, tests, and API readiness

## Architecture

```text
Client
  |
  v
FastAPI API
  |
  +--> PostgreSQL
  |      +--> users, wallets, ledger, orders
  |      +--> outbox_events
  |
  +--> Redis (foundation for cache and rate limits)

outbox-relay worker
  |
  +--> RabbitMQ topic exchange: crypto.ledger.events
```

Order mutations and outbox writes are committed in one PostgreSQL transaction. The relay then publishes pending events to RabbitMQ and records the delivery result.

This provides at-least-once delivery. Event consumers should use `event_key` or `event_id` for idempotency.

## Services and local ports

| Service | Local address |
| --- | --- |
| FastAPI docs | http://localhost:8001/docs |
| FastAPI health | http://localhost:8001/health |
| RabbitMQ Management UI | http://localhost:15673 |
| PostgreSQL | localhost:5433 |
| Redis | localhost:6381 |
| RabbitMQ AMQP | localhost:5673 |

## Run locally

1. Create local environment values:

```bash
cp .env.example .env
```

2. Start the API and infrastructure:

```bash
docker compose up --build -d
```

3. Apply migrations:

```bash
docker compose exec -T api alembic upgrade head
```

4. Start the asynchronous relay worker:

```bash
docker compose --profile worker up -d outbox-relay
```

Useful worker commands:

```bash
docker compose --profile worker ps
docker compose --profile worker logs -f outbox-relay
```

## Core API routes

| Method | Route | Notes |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Create a user |
| POST | `/api/v1/auth/login` | Obtain a JWT |
| GET | `/api/v1/auth/me` | Current authenticated user |
| POST | `/api/v1/wallets/fund` | Development-only sandbox funding; requires `Idempotency-Key` |
| GET | `/api/v1/wallets` | Available, locked, and total balances |
| POST | `/api/v1/orders` | Reserve funds for a buy or sell order; requires `Idempotency-Key` |
| POST | `/api/v1/orders/{order_id}/cancel` | Release reserved funds; safe to replay |

## Event delivery

Order creation and cancellation store events in `outbox_events` as part of the same database transaction.

The relay worker:

1. Claims one unpublished event with a database row lock.
2. Publishes a persistent message to the `crypto.ledger.events` topic exchange.
3. Uses the event type as the routing key, such as `order.created` or `order.canceled`.
4. Marks `published_at` after RabbitMQ confirms delivery.
5. Increments `publish_attempts` and saves `last_error` when publishing fails.

## Validate locally

```bash
docker compose exec -T api ruff check app tests
docker compose exec -T api alembic check
docker compose exec -T api python -m pytest -q
```

## Project layout

```text
app/
  api/          HTTP routes and dependencies
  core/         settings and security
  db/           SQLAlchemy base and session management
  events/       RabbitMQ publisher
  models/       PostgreSQL models
  services/     ledger, order, and outbox workflows
  workers/      asynchronous outbox relay
alembic/         database migrations
tests/           integration tests
```

## CI

Every push to `main` and every pull request runs:

- Docker Compose build and service startup
- Alembic migrations
- Ruff linting
- Integration tests
- API readiness check
