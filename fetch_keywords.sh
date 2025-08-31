#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-$SCRIPT_DIR/requirements.txt}"
PY_SCRIPT="$SCRIPT_DIR/fetch_keywords.py"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: $PYTHON_BIN not found. Install Python 3.9+." >&2
  exit 2
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip >/dev/null
if [ -f "$REQUIREMENTS_FILE" ]; then
  pip install -r "$REQUIREMENTS_FILE"
fi

# Load .env if present (exports variables like ASC_KEY_ID, ASC_ISSUER_ID, etc.)
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

if [ $# -eq 0 ]; then
  echo "Usage: $(basename "$0") [fetch_keywords.py options and arguments]" >&2
  echo "Examples:" >&2
  echo "  ASC_KEY_ID=... ASC_ISSUER_ID=... ASC_PRIVATE_KEY_PATH=... $(basename "$0") id123456789 -l en-US" >&2
  echo "  $(basename "$0") -h  # show Python CLI help" >&2
fi

exec "$PYTHON_BIN" "$PY_SCRIPT" "$@"
