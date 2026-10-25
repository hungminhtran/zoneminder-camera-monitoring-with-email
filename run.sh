#!/bin/sh
set -eu

cd "$(dirname "$0")"

set -a
. ./.env
set +a

exec python3 monitor.py "$@"
