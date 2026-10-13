#!/bin/sh
# Single-container entrypoint for hosts where the API and worker cannot share a disk (e.g. Render):
# runs the RQ worker and the API side by side; if either exits, the container exits so the host restarts it.
set -eu
mkdir -p "${STORAGE_DIR:-/tmp/mom-storage}"
rq worker meetings --url "$REDIS_URL" &
WORKER=$!
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' &
API=$!
trap 'kill $WORKER $API 2>/dev/null' TERM INT
while kill -0 $WORKER 2>/dev/null && kill -0 $API 2>/dev/null; do sleep 5; done
echo "a process exited; stopping container" >&2
kill $WORKER $API 2>/dev/null || true
exit 1
