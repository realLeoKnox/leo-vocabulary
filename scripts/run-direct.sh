#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ -f "$PROJECT_DIR/.env.direct" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env.direct"
  set +a
fi

VENV_PATH=${VENV_PATH:-$PROJECT_DIR/.venv}
APP_HOST=${APP_HOST:-0.0.0.0}
APP_PORT=${APP_PORT:-8080}
DATABASE_URL=${DATABASE_URL:-sqlite:///$PROJECT_DIR/data/vocab.db}
FRONTEND_DIST=${FRONTEND_DIST:-$PROJECT_DIR/frontend/dist}

if [ ! -x "$VENV_PATH/bin/uvicorn" ]; then
  echo "Python environment not found. Run ./scripts/install-direct.sh first." >&2
  exit 1
fi
if [ ! -f "$FRONTEND_DIST/index.html" ]; then
  echo "Frontend build not found. Run ./scripts/install-direct.sh first." >&2
  exit 1
fi

mkdir -p "$PROJECT_DIR/data"
export DATABASE_URL FRONTEND_DIST

cd "$PROJECT_DIR/backend"
"$VENV_PATH/bin/alembic" upgrade head
exec "$VENV_PATH/bin/uvicorn" app.main:app --host "$APP_HOST" --port "$APP_PORT"

