#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v "${ZSIGN_PATH:-zsign}" >/dev/null 2>&1; then
  echo '找不到 zsign。請先依 README 安裝 zsign。' >&2
  exit 1
fi
python3 -m pip install -r requirements.txt
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
