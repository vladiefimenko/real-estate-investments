#!/usr/bin/env bash
# Entrypoint for Dockerfile.render: migrate, then run the API and the web app together.
# If either process exits, the container exits so the host restarts it.
set -euo pipefail

cd /srv/apps/api
alembic upgrade head

uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*' &
cd /srv/web
HOSTNAME=0.0.0.0 node server.js &

wait -n
exit $?
