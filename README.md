# ShortsGen AI

A local studio for drafting, editing, rendering, and publishing vertical videos.
Next.js provides the editor; FastAPI orchestrates the generation providers and
FFmpeg. SQLite stores projects, progress, jobs, and cost reservations.

## Setup

Use Python 3.11, Node.js 20.9 or newer, and FFmpeg with `ffprobe` and the libass
subtitle filter available on your PATH. On macOS, FFmpeg can be installed with
`brew install ffmpeg`.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
cp .env.example .env
cd frontend
npm ci
cd ..
./run.sh
```

`requirements-lock.txt` snapshots the verified Python 3.11 macOS environment.
`requirements.txt` lists direct dependencies for resolving a different platform;
run the checks below after resolving and review version changes before updating
the lock. The frontend uses its committed `package-lock.json`.

Open http://localhost:3000. The backend defaults to `127.0.0.1:8000`.
The launcher starts the backend and frontend; generation engines need their own
setup:

- **Text:** run Ollama with a downloaded model, or configure `OPENROUTER_API_KEY`.
- **Speech:** place `kokoro-v1.0.onnx` and `voices-v1.0.bin` in `models/`.
- **Images:** select Pollinations, configure Leonardo, or start the local image
  server with `.venv/bin/python sd_server.py`. Local model downloads need network
  access and sufficient disk space and RAM.
- **Stock footage:** set `PEXELS_API_KEY` to enable stock search.
- **Animation:** configure `MINIMAX_API_KEY` for Hailuo or Leonardo credentials
  for Leonardo motion.
- **YouTube:** supply `client_secret.json` and authorize from the studio before
  publishing. The default upload privacy is private.

The production frontend build currently downloads its two Google Fonts, so
`npm run build` requires access to Google Fonts.

## Reliability and recovery

Drafts, renders, and uploads are persisted in SQLite before the API acknowledges
submission. A single worker drains the queue to limit local GPU/FFmpeg pressure.
**Run one backend process**, without multiple Uvicorn workers or reload mode.
This is a local application, not an authenticated multi-user deployment.

- Queued jobs continue after a backend restart.
- Interrupted jobs become failed with a recovery message. They are not replayed
  automatically against paid providers or publishing APIs.
- Failed renders retain completed scene assets. Open the saved storyboard from
  the library and render again to resume.
- Scene assets are reused only when their input fingerprints match. Older assets
  without fingerprints are regenerated on their first render after this update.
- Refreshing the frontend reconnects to the last monitored generation/upload.
- Concurrent operations on the same generation are rejected.
- An upload reservation is recorded **before** contacting YouTube. If the remote
  result is uncertain, publishing that generation remains blocked. Check your
  channel before any manual reconciliation of the reservation; do not blindly
  retry or delete the reservation.

Scene assets referenced by saved projects remain on disk, including failed and
completed projects. Deletion removes only explicitly referenced, unshared files
inside `temp/` and `outputs/`, plus the final thumbnail. Unreferenced temporary
files expire after 48 hours. Back up `video_studio.db`, `outputs/`, and `temp/`
together while the backend is stopped if you want editable project backups.

## Cost limits

`LEONARDO_DAILY_BUDGET` and `HAILUO_DAILY_BUDGET` are optional UTC daily limits in
configured **cost units**, not currency. Each paid attempt (including retries)
atomically reserves its configured cost before making the request. Reservations
remain after ambiguous failures because the provider may have charged them.
Use provider billing dashboards to reconcile actual charges.

Local and Pollinations images do not consume Leonardo image units. Hailuo motion
uses its own service ledger and `HAILUO_MOTION_COST`.

## Configuration

Backend settings live in `.env`; see `.env.example` for generation providers.
`BACKEND_HOST`, `PUBLIC_BASE_URL`, and `CORS_ORIGINS` configure the bind address,
media URL origin, and allowed frontend origins. Keep the loopback default for
personal use. Network access requires a separate authentication/access-control
layer.

For a different backend URL, put `NEXT_PUBLIC_API_BASE_URL` in
`frontend/.env.local` (see `frontend/.env.example`) and rebuild the frontend.
The same backend origin should be used for `PUBLIC_BASE_URL`.

## Checks

```sh
.venv/bin/python -m pytest
.venv/bin/python -m pip check
cd frontend
npm run lint
npx tsc --noEmit --incremental false
npm run build
```

Tests isolate SQLite in a temporary directory and include actual FFmpeg rendering
checks plus mocked provider/upload tests. They do not validate live provider
availability or publish videos.

## Main modules

- `backend.py`: API routes and video orchestration
- `asset_state.py`: scene input fingerprints and asset invalidation
- `job_queue.py`: persisted job submission, serialization, and restart recovery
- `db_manager.py`: project storage, upload reservations, and owned-file deletion
- `cost_tracker.py`: atomic paid-attempt reservations
- `video_quality.py`, `captions.py`: rendering and subtitle processing
- `frontend/src/lib/`: API configuration, shared types, and cancellable polling
