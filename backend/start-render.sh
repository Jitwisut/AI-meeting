#!/bin/sh
# Single-container entrypoint (e.g. Render).
# QUEUE_MODE=thread (default here): jobs run in background threads inside the API process — no Redis needed.
# QUEUE_MODE=rq: also start an RQ worker; if either process exits, the container exits so the host restarts it.
set -eu
mkdir -p "${STORAGE_DIR:-/tmp/mom-storage}"
if [ "${QUEUE_MODE:-thread}" != "rq" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
fi
rq worker meetings --url "$REDIS_URL" &
WORKER=$!
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' &
API=$!
trap 'kill $WORKER $API 2>/dev/null' TERM INT
while kill -0 $WORKER 2>/dev/null && kill -0 $API 2>/dev/null; do sleep 5; done
echo "a process exited; stopping container" >&2
kill $WORKER $API 2>/dev/null || true
exit 1
