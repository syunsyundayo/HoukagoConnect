#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/.python_packages/lib/site-packages${PYTHONPATH:+:$PYTHONPATH}"
exec python -m gunicorn --no-control-socket --bind 0.0.0.0:8000 --workers 1 --threads 2 'app:create_app()'
