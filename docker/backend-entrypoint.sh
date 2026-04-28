#!/bin/sh
set -e

# Fix ownership of bind-mounted volumes so appuser (uid 1000) can write.
# Required because docker daemon creates missing host dirs as root.
chown -R 1000:1000 \
    /app/data \
    /app/logs \
    /home/appuser/.cache 2>/dev/null || true

exec gosu appuser "$@"
