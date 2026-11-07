#!/bin/bash
# Local CLI only. Does not deploy unless explicitly called with a deploy command.
set -euo pipefail
umask 077
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK_NODE="${GARMENT_NODE:-$(command -v node || true)}"
if [[ -z "$TASK_NODE" ]]; then
  TASK_NODE="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
fi
TASK_CLI="$TASK_ROOT/.tools/firebase/node_modules/firebase-tools/lib/bin/firebase.js"
if [[ ! -x "$TASK_NODE" || ! -f "$TASK_CLI" ]]; then
  echo 'Local Firebase CLI or Node is missing. Install firebase-tools first.' >&2
  exit 1
fi
mkdir -p "$TASK_ROOT/.runtime/firebase-cli-config"
exec /usr/bin/env XDG_CONFIG_HOME="$TASK_ROOT/.runtime/firebase-cli-config" NO_UPDATE_NOTIFIER=1 "$TASK_NODE" "$TASK_CLI" "$@"
