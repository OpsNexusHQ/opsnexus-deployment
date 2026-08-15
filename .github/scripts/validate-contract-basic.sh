#!/usr/bin/env bash
set -euo pipefail

exec python3 "$(dirname "$0")/validate_contract_basic.py" \
  "${1:-.github/compatibility/contract-basic.json}" \
  "${2:-$RUNNER_TEMP/opsnexus-api/api/openapi.yaml}"
