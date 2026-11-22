#!/usr/bin/env bash
# Copy the tool to the tools VM and restart it. Run from the laptop:
#   deploy/deploy.sh [host]        (default host: tools.test)
# The first-time setup in README.md must have been done once.
set -euo pipefail
HOST="${1:-tools.test}"
cd "$(dirname "$0")/.."

rsync -a --delete --exclude .venv --exclude .git --exclude instance --exclude __pycache__ \
  --exclude .pytest_cache ./ "$HOST:quiz-tool-src/"

ssh -t "$HOST" 'set -e
  sudo rsync -a --delete --exclude .venv ~/quiz-tool-src/ /opt/quiz-tool/
  sudo /opt/quiz-tool/.venv/bin/pip install -q -r /opt/quiz-tool/requirements.txt
  sudo systemctl restart quiz-tool
  sleep 1
  systemctl is-active quiz-tool'
