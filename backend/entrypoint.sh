#!/bin/sh

set -eu

normalize_database_url() {
  if [ -z "${DATABASE_URL:-}" ] && [ -n "${APP_DATABASE_URL:-}" ]; then
    DATABASE_URL="${APP_DATABASE_URL}"
    export DATABASE_URL
  fi

  if [ -z "${DATABASE_URL:-}" ] && [ -n "${PGHOST:-}" ] && [ -n "${PGUSER:-}" ] && [ -n "${PGPASSWORD:-}" ] && [ -n "${PGDATABASE:-}" ]; then
    DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT:-5432}/${PGDATABASE}"
    export DATABASE_URL
  fi

  case "${DATABASE_URL:-}" in
    postgresql+asyncpg://*)
      ;;
    postgresql://*)
      DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgresql://}"
      export DATABASE_URL
      ;;
    postgres://*)
      DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgres://}"
      export DATABASE_URL
      ;;
  esac
}

print_runtime_summary() {
  python - <<'PY'
import os
from urllib.parse import urlsplit


def summarize(name: str) -> str:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return f"{name}=missing"
    try:
        parts = urlsplit(raw_value)
        host = parts.hostname or "unknown-host"
        port = parts.port or "default"
        path = parts.path or ""
        return f"{name}={parts.scheme}://{host}:{port}{path}"
    except Exception:
        return f"{name}=invalid"


print(summarize("DATABASE_URL"))
print(summarize("REDIS_URL"))
PY
}

normalize_database_url
print_runtime_summary

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is not set. Refusing to start api service."
  exit 1
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
