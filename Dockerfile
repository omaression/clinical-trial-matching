FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY data ./data
COPY scripts/container-start-backend.sh ./scripts/container-start-backend.sh

RUN pip install --upgrade pip setuptools wheel && pip install . && chmod +x ./scripts/container-start-backend.sh

EXPOSE 8000

CMD ["./scripts/container-start-backend.sh"]
