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

python -m pip install --upgrade pip >/dev/null 2>&1
if [ -f "$REQUIREMENTS_FILE" ]; then
  # Hide noisy 'Requirement already satisfied' messages while keeping errors visible
  pip install -q -r "$REQUIREMENTS_FILE" >/dev/null
fi

# Load .env if present (exports variables like DEFAULT_COUNTRY, ASO_CHAR_LIMIT, etc.)
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

if [ $# -eq 0 ]; then
  echo "Usage: $(basename "$0") [fetch_keywords.py options and arguments]" >&2
  echo "Examples:" >&2
  echo "  $(basename "$0") id123456789 -l en-US" >&2
  echo "  $(basename "$0") com.example.myapp -l en-US de-DE" >&2
  echo "  $(basename "$0") -h  # show Python CLI help" >&2
fi

exec "$PYTHON_BIN" "$PY_SCRIPT" "$@"
