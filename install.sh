#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

if command -v python3.11 >/dev/null 2>&1; then
  PYTHON=python3.11
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "[LOI] Khong tim thay Python. Hay cai Python 3.11+ roi chay lai." >&2
  exit 1
fi

exec "$PYTHON" "$ROOT/install.py" "$@"
