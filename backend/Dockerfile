# syntax=docker/dockerfile:1
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by asyncpg and uvicorn
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Project metadata and code
COPY pyproject.toml ./
COPY app app

# Install Python dependencies from pyproject
RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

# Alembic migrations
COPY alembic alembic
COPY alembic.ini ./

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
