#!/usr/bin/env bash
# Load .env and start the SaC HTTP server
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a; source .env; set +a
fi
exec /Users/mulongxie/.pyenv/versions/3.12.0/bin/python -m sac.server.http "$@"
