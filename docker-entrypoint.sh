#!/bin/sh
set -eu

case "${DEV:-0}" in
  1|true|TRUE|yes) dev=1 ;;
  *) dev=0 ;;
esac

db=$(python -c "import config; print(config.DB_PATH)")
echo "boot: DEV=$dev DB_PATH=$db"

if [ "$dev" = "1" ]; then
  echo "DEV=1: seeding $db"
  python tools/seed.py --cameras "${SEED_CAMERAS:-32}"
else
  echo "DEV=0: leaving $db to the collector"
fi

exec "$@"
