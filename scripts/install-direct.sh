#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENV_PATH=${VENV_PATH:-$PROJECT_DIR/.venv}

mkdir -p "$PROJECT_DIR/data"

if [ ! -x "$VENV_PATH/bin/python" ]; then
  python3 -m venv "$VENV_PATH"
fi

"$VENV_PATH/bin/python" -m pip install -r "$PROJECT_DIR/backend/requirements.txt"
npm --prefix "$PROJECT_DIR/frontend" ci
npm --prefix "$PROJECT_DIR/frontend" run build

if [ ! -f "$PROJECT_DIR/.env.direct" ]; then
  cp "$PROJECT_DIR/.env.direct.example" "$PROJECT_DIR/.env.direct"
fi

echo "Direct deployment installed. Start with: ./scripts/run-direct.sh"

