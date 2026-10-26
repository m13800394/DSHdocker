#!/usr/bin/env sh
set -eu
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3.10+ is required. Install python3, then rerun deploy.sh.' >&2
  exit 1
fi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/scripts/deploy.py" "$@"
