#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 /app/data /app/logs /home/appuser/.cache 2>/dev/null || true
    exec gosu appuser "$@"
fi

exec "$@"
