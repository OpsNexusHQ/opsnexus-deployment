#!/usr/bin/env bash
set -euo pipefail

exec python3 "$(dirname "$0")/run_contract_assertions.py" \
  "${1:-.github/compatibility/contract-basic.json}" \
  "${OPSNEXUS_CONTRACT_BASE_URL:-http://127.0.0.1:8080}"
