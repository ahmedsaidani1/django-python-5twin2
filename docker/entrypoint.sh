#!/bin/sh
# Web container: apply migrations (and optionally load demo data) before starting the command.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo
fi

exec "$@"
