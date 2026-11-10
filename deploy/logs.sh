#!/usr/bin/env bash
cd "$(dirname "$0")/.."
if [ $# -ge 1 ]; then
    docker compose logs -f --tail=200 "$1"
else
    docker compose logs -f --tail=100
fi
