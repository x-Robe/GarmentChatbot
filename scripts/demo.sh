#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK_PYTHON="${GARMENT_PYTHON:-$TASK_ROOT/.venv/bin/python}"
if [[ ! -x "$TASK_PYTHON" ]]; then
  echo 'Missing .venv. Create Python 3.12 venv and install backend requirements first.' >&2
  exit 1
fi
exec "$TASK_PYTHON" "$TASK_ROOT/scripts/local_demo.py" "$@"
