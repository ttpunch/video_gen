#!/usr/bin/env bash
#
# Single command to run the whole project: FastAPI backend + Next.js frontend.
#
#   ./run.sh
#
# Backend  -> http://localhost:8000
# Frontend -> http://localhost:3000
#
set -euo pipefail

cd "$(dirname "$0")"

PYTHON=".venv/bin/python"

# --- Sanity checks -----------------------------------------------------------
if [[ ! -x "$PYTHON" ]]; then
  echo "Python venv not found at $PYTHON" >&2
  echo "Create it with:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm install)
fi

# --- Clean up both processes on exit ----------------------------------------
pids=()
cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# --- Start backend -----------------------------------------------------------
echo "Starting backend  -> http://localhost:8000"
"$PYTHON" backend.py &
pids+=($!)

# --- Start frontend ----------------------------------------------------------
echo "Starting frontend -> http://localhost:3000"
(cd frontend && npm run dev) &
pids+=($!)

echo ""
echo "Both services running. Press Ctrl+C to stop."

# Poll until any service exits, then the trap cleans up the rest.
# (Portable: macOS ships bash 3.2, which lacks `wait -n`.)
while true; do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "A service (pid $pid) exited."
      exit 1
    fi
  done
  sleep 1
done
