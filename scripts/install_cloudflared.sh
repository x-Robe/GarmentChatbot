#!/bin/bash
# Installs only an official Cloudflare release under this repository's ignored .tools.
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$(uname -m)" in
  arm64) TASK_ARCH=arm64 ;;
  x86_64) TASK_ARCH=amd64 ;;
  *) echo 'Unsupported Mac architecture' >&2; exit 1 ;;
esac
mkdir -p "$TASK_ROOT/.tools"
TASK_ARCHIVE="$(mktemp "$TASK_ROOT/.tools/cloudflared.XXXXXX")"
trap 'rm -f "$TASK_ARCHIVE"' EXIT
curl --fail --location --retry 2 "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-$TASK_ARCH.tgz" --output "$TASK_ARCHIVE"
tar -xzf "$TASK_ARCHIVE" -C "$TASK_ROOT/.tools" cloudflared
chmod 755 "$TASK_ROOT/.tools/cloudflared"
"$TASK_ROOT/.tools/cloudflared" --version
