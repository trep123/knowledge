#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
./deploy/stop.sh
./deploy/start.sh
