p0-user-models-migration-pydantic-repo-tests
# User Service Domain

This repository defines a minimal user domain consisting of SQLAlchemy models, Alembic migrations, Pydantic schemas, repository helpers, and a lightweight service layer. The accompanying pytest suite exercises the main workflows and database constraints.

## Components

- **Models**: Located in `src/user_service/models.py`, covering `users`, `user_profiles`, `user_sessions`, and the supporting `subscriptions` table.
- **Schemas**: Pydantic DTOs in `src/user_service/schemas.py` provide strict validation for create/update/read operations.
- **Repositories & Services**: Encapsulate database access patterns and high-level orchestration under `src/user_service/repository.py` and `src/user_service/services.py`.
- **Migrations**: Alembic migration scripts live under `migrations/`. Apply them with `alembic upgrade head`.
- **Tests**: Async pytest coverage in `tests/` ensures constraints, cascades, and service logic behave as expected.
- **Documentation**: An ERD-style overview is documented in `docs/user_domain.md`.

## Running the tests

Install the project dependencies and execute the tests:

```bash
pip install -e .
pytest
```

The tests automatically run the Alembic migrations against an isolated SQLite database for each scenario.

feat/compose-dev-stack-p0
# Compose developer stack

This repository ships a batteries-included Docker Compose stack for local development. It bundles the
FastAPI backend, Celery worker, Python-powered frontend, and the required infrastructure services:
PostgreSQL 15, Redis 7, RabbitMQ 3.12, MinIO (S3 compatible storage), Nginx reverse proxy, Prometheus,
Grafana, and a Sentry relay.

All application containers are built from multi-stage Dockerfiles using Python 3.11 slim images with
production-friendly defaults (non-root users, health checks, dependency wheels, minimal base packages).

## Prerequisites

- Docker Engine 24+
- Docker Compose plugin (bundled with Docker Desktop / Engine)
- GNU Make (optional, but all helper commands assume it is available)

## Getting started

1. **Clone & configure environment variables**

   ```bash
   cp .env.example .env.docker
   # Adjust passwords/keys if desired
   ```

   The `.env.docker` file is committed with sane defaults for local usage. Update values if you require
   custom credentials.

2. **Start the stack**

   ```bash
   make up
   ```

   This builds the Python backend/worker/frontend images (caching dependency wheels in a builder stage)
   and launches every service with sensible restart policies, resource limits, named volumes, and shared
   networks.

3. **Verify connectivity**

   Once `docker compose ps` shows all containers as `running`/`healthy`, execute:

   ```bash
   make connectivity
   ```

   The helper script hits the nginx reverse proxy on `http://localhost:8080` and checks:

   - `/api/health` → FastAPI backend health (database, Redis, RabbitMQ, MinIO probes)
   - `/grafana/api/health` → Grafana API availability
   - `/prometheus/-/healthy` → Prometheus target
   - `/minio/metrics` → MinIO console endpoint

   You can also explore:

   - API docs: [http://localhost:8080/api/docs](http://localhost:8080/api/docs)
   - Frontend dashboard: [http://localhost:8080/](http://localhost:8080/)
   - Grafana: [http://localhost:8080/grafana/](http://localhost:8080/grafana/)
   - Prometheus: [http://localhost:8080/prometheus/](http://localhost:8080/prometheus/)
   - MinIO console: [http://localhost:8080/minio/](http://localhost:8080/minio/)

## Helpful commands

All commands automatically use `.env.docker`. Override with `ENV_FILE=<path>` if required.

| Command | Description |
| --- | --- |
| `make up` | Build and start the entire stack in the background |
| `make down` | Stop containers but keep volumes |
| `make destroy` | Stop everything and remove named volumes |
| `make logs` | Tail logs for every service |
| `make tail TAIL_SERVICE=backend` | Tail logs for a specific service |
| `make ps` | Show container status |
| `make connectivity` | Run HTTP connectivity checks via nginx |

## Service inventory

| Service | Tech | Notes |
| --- | --- | --- |
| `backend` | FastAPI + Uvicorn | Exposes `/api`, instrumented with Prometheus metrics, publishes Celery tasks |
| `worker` | Celery | Consumes tasks via RabbitMQ broker, persists results in Redis |
| `frontend` | FastAPI (Jinja) | Simple status dashboard consuming backend health |
| `nginx` | nginx:1.25-alpine | The only service exposed to the host (`localhost:8080`) |
| `postgres` | PostgreSQL 15 | Persistent data volume `postgres_data` |
| `redis` | Redis 7 | Volume-backed cache/queue |
| `rabbitmq` | RabbitMQ 3.12 | Management + Prometheus plugins enabled, volume `rabbitmq_data` |
| `minio` | MinIO | S3-compatible storage, console reachable through nginx |
| `prometheus` | Prometheus v2.47 | Scrapes backend, self, and RabbitMQ metrics |
| `grafana` | Grafana 10 | Auto-provisioned Prometheus data source |
| `sentry-relay` | getsentry/relay | Relays SDK traffic to upstream Sentry (defaults to sentry.io) |

Two networks are defined:

- `core`: default bridge network for application and infrastructure containers
- `monitoring`: shared by Prometheus, Grafana, and nginx to isolate observability traffic

Persistent named volumes keep state (`postgres_data`, `redis_data`, `rabbitmq_data`, `minio_data`,
`grafana_data`, `prometheus_data`).

## Default credentials

| Service | Via nginx | Username | Password |
| --- | --- | --- | --- |
| Grafana | http://localhost:8080/grafana/ | `${GRAFANA_ADMIN_USER}` | `${GRAFANA_ADMIN_PASSWORD}` |
| MinIO console | http://localhost:8080/minio/ | `${MINIO_ROOT_USER}` | `${MINIO_ROOT_PASSWORD}` |
| RabbitMQ management | _internal only_ (`http://rabbitmq:15672`) | `${RABBITMQ_DEFAULT_USER}` | `${RABBITMQ_DEFAULT_PASS}` |

Update these values in `.env.docker` before sharing the stack with a wider team. Prometheus reuses the
RabbitMQ credentials for metrics scraping, so adjust `prometheus/prometheus.yml` if you change them.

## Configuration reference

The following environment variables are consumed by the stack (see `.env.example` for details):

- **PostgreSQL**: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`
- **Celery / messaging**: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`
- **Object storage**: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_ENDPOINT`, `MINIO_REGION`
- **Sentry**: `SENTRY_DSN`, `SENTRY_RELAY_UPSTREAM_URL`, `SENTRY_RELAY_PORT`
- **Frontend/backend tuning**: `BACKEND_UVICORN_WORKERS`
- **Grafana**: `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`

The Sentry relay entrypoint renders a configuration file at runtime using the variables above. Replace `SENTRY_DSN` with a valid DSN that routes through the relay (`http://<public>:<secret>@sentry-relay:3000/<project>`), and point `SENTRY_RELAY_UPSTREAM_URL` to your upstream Sentry instance.

## Troubleshooting

- **Containers not healthy**: Run `docker compose ps` to identify failing services, then inspect logs with
  `make tail TAIL_SERVICE=<service>`.
- **Port collisions**: The stack binds nginx to `localhost:8080`. Adjust the port in `docker-compose.yml` if
  the host already uses it.
- **Database migrations**: The backend ships without migrations. Use `docker compose exec backend bash`
  to apply schema changes as needed.
- **Slow startup**: The Celery worker waits for RabbitMQ and Redis to become reachable. Initial health checks
  might report `degraded` until all dependencies pass.
- **Cleaning state**: Run `make destroy` to wipe data volumes and start from a clean slate.
- **Connectivity script fails**: Ensure nginx is running (`make tail TAIL_SERVICE=nginx`) and that your
  firewall allows connections to `localhost:8080`.

## Extending the stack

- Add additional API routers inside `backend/app` and Celery tasks in `backend/app/tasks.py`.
- Attach new services (e.g., Jaeger, Loki) by following the established pattern: create a directory with
  service-specific config, mount it in `docker-compose.yml`, and wire the service through nginx if it needs
  host access.
- Update `prometheus/prometheus.yml` and Grafana provisioning files to capture new metrics endpoints.

## License

This project is distributed under the MIT License. Modify and adapt the stack as needed for your
engineering workflows.

# Backend Service

This repository contains a FastAPI-based backend scaffold with structured logging, async database
support via SQLAlchemy, and Alembic migrations.

## Development

Install dependencies (development extras include linting and testing tools):

```bash
pip install -e .[dev]
```

Run the application locally:

```bash
uvicorn backend.main:app --reload
```

Or via Docker Compose (includes Postgres):

```bash
docker compose up --build
```

Execute the tests:

```bash
pytest
```

Additional tooling is configured via `pre-commit`, `ruff`, `black`, and `mypy` for quality gates.

### Authentication API

The backend exposes a full authentication workflow under `/api/v1/auth` with registration, verification, login, refresh, and logout endpoints. Tokens are returned in the JSON payload and persisted as HTTP-only cookies for browser clients. Authenticated requests can supply the access token via the `Authorization: Bearer <token>` header.

| Endpoint | Description |
| --- | --- |
| `POST /api/v1/auth/register` | Create a new account and receive a verification token |
| `POST /api/v1/auth/verify` | Activate an account using the verification token |
| `POST /api/v1/auth/login` | Exchange credentials for access/refresh tokens (rate limited 5/min) |
| `POST /api/v1/auth/refresh` | Rotate refresh tokens and receive a fresh access token |
| `POST /api/v1/auth/logout` | Revoke the current session and clear cookies |
| `GET /api/v1/auth/me` | Retrieve the authenticated user's profile |

Example HTTPie commands:

```bash
http POST :8000/api/v1/auth/register email=demo@example.com password='StrongPass123!'
# copy the verification token from the response
http POST :8000/api/v1/auth/verify token=="<verification-token>"
http --session=auth POST :8000/api/v1/auth/login email=demo@example.com password='StrongPass123!'
http --session=auth POST :8000/api/v1/auth/refresh
http --session=auth GET :8000/api/v1/auth/me
http --session=auth POST :8000/api/v1/auth/logout
```

### Task status streaming

The backend exposes a WebSocket endpoint at `ws://<host>/ws/tasks/{task_id}` that delivers real-time
updates for generation tasks:

- Authenticate by providing the `X-User-Id` header during the WebSocket handshake. Only the owner of the task can
  subscribe to its updates.
- The server immediately sends a `snapshot` message containing the latest persisted task state so reconnecting
  clients do not miss updates.
- Subsequent updates are published with `type="update"` in the order they are written to the database. Each payload
  includes a monotonically increasing `sequence`, `status`, optional `error`, and a `terminal` flag indicating
  whether the task is finished.
- Heartbeat frames (`type="heartbeat"`) are sent every ~15 seconds when no state changes occur. Connections are
  closed with code `1000` once a terminal status (`completed` or `failed`) has been delivered.

Example payload:

```json
{
  "type": "update",
  "task_id": "0a89f0bd-7ec9-43cf-a2e4-1d5f5df45a7a",
  "sequence": 3,
  "status": "processing",
  "terminal": false,
  "prompt": "Generate via websocket",
  "parameters": {"width": 512},
  "created_at": "2023-10-30T10:15:31.762Z",
  "updated_at": "2023-10-30T10:16:05.114Z",
  "sent_at": "2023-10-30T10:16:05.200Z"
}
```

#### Publishing from backend components

Use the `TaskStatusBroadcaster` helper whenever a worker or API endpoint mutates a task record. The broadcaster
persists the latest payload in Redis (with a TTL for cleanup) and delivers it over the `tasks:{task_id}` pub/sub
channel:

```python
from backend.generation.broadcaster import TaskStatusBroadcaster

broadcaster = TaskStatusBroadcaster(redis_client)
await broadcaster.publish(task)
```

#### Frontend example

```javascript
const ws = new WebSocket(`ws://${location.host}/ws/tasks/${taskId}`);
ws.onopen = () => console.log('task stream connected');
ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  if (payload.type === 'heartbeat') {
    return;
  }
  renderTaskStatus(payload);
};
ws.onclose = (event) => {
  console.log('Task stream closed', event.code);
};
```

main
main
