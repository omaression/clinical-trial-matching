# Local Development

Use the repo launcher at `./scripts/dev.sh` to boot the full local stack with one command.

## Prerequisites

- Activate a Python environment with the backend dependencies installed.
- Ensure PostgreSQL is running and `CTM_DATABASE_URL` points at the target database if you are not using the default local DSN.
- Install frontend dependencies once with `cd frontend && npm install`.

## Start Everything

From the repository root:

```bash
./scripts/dev.sh
```

The launcher does three things:

1. Runs `alembic upgrade head`
2. Starts FastAPI on `http://127.0.0.1:8000`
3. Starts Next.js on `http://127.0.0.1:3000`

The backend health endpoint is:

```bash
http://127.0.0.1:8000/api/v1/health
```

The frontend entrypoint is:

```bash
http://127.0.0.1:3000
```

## Defaults

The launcher sets these defaults if they are not already exported:

```bash
CTM_API_KEY=local-dev-api-key
CTM_FRONTEND_API_KEY=$CTM_API_KEY
CTM_FRONTEND_API_BASE_URL=http://127.0.0.1:8000/api/v1
CTM_BACKEND_HOST=127.0.0.1
CTM_BACKEND_PORT=8000
CTM_FRONTEND_HOST=127.0.0.1
CTM_FRONTEND_PORT=3000
```

Override any of them in your shell before launching if you need different ports or keys.

## Useful Variants

Skip Alembic if the database is already current:

```bash
CTM_SKIP_MIGRATIONS=1 ./scripts/dev.sh
```

Run on different ports:

```bash
CTM_BACKEND_PORT=8010 CTM_FRONTEND_PORT=3010 ./scripts/dev.sh
```

## Failure Modes

- If `frontend/node_modules` is missing, the launcher exits immediately. Run `cd frontend && npm install` once.
- If `alembic`, `uvicorn`, or `npm` are missing from `PATH`, the launcher exits immediately and prints the missing command.
- If either the backend or frontend process exits, the launcher stops the other process and exits with the same status.
