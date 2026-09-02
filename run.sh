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

# --- Rotate the backend log before each run ----------------------------------
# Previously unbounded: a long-lived local backend just kept appending to
# backend_stdout.log forever. Rotating at startup (rather than continuously,
# which would mean reopening a live process's stdout mid-write) covers the
# common case for a personal dev app that gets restarted regularly.
BACKEND_LOG="backend_stdout.log"
BACKEND_LOG_MAX_BYTES=$((10 * 1024 * 1024))
if [[ -f "$BACKEND_LOG" ]]; then
  size=$(wc -c < "$BACKEND_LOG" 2>/dev/null || echo 0)
  if (( size > BACKEND_LOG_MAX_BYTES )); then
    [[ -f "${BACKEND_LOG}.1" ]] && mv -f "${BACKEND_LOG}.1" "${BACKEND_LOG}.2"
    mv -f "$BACKEND_LOG" "${BACKEND_LOG}.1"
  fi
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
# Process substitution (not a pipe) so $! below still captures backend.py's
# own PID for the liveness check / cleanup trap, not tee's.
echo "Starting backend  -> http://localhost:8000"
"$PYTHON" backend.py > >(tee -a "$BACKEND_LOG") 2>&1 &
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
