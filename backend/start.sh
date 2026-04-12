#!/bin/sh
set -e

mkdir -p /app/data

echo "Running Alembic migrations..."
alembic upgrade head || echo "WARNING: Alembic migration failed — continuing with existing schema"

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
