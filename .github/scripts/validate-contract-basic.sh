#!/usr/bin/env bash
set -euo pipefail

spec="${1:-.github/compatibility/contract-basic.json}"
openapi="${2:-$RUNNER_TEMP/opsnexus-api/api/openapi.yaml}"
[[ -f "$spec" ]] || { echo "ci/compatibility-contract: missing assertion specification $spec" >&2; exit 1; }
[[ -f "$openapi" ]] || { echo "ci/compatibility-contract: missing authoritative OpenAPI $openapi" >&2; exit 1; }
jq -e '.profile == "contract-basic" and (.assertions | length == 7)' "$spec" >/dev/null || { echo 'ci/compatibility-contract: malformed assertion specification' >&2; exit 1; }

while IFS=$'\t' read -r name method path status content_type; do
  method="${method,,}"
  grep -Fq "  $path:" "$openapi" || { echo "ci/compatibility-contract: $name path $path is not in OpenAPI" >&2; exit 1; }
  awk -v start="  $path:" 'found {print; if ($0 ~ /^  \/api\// && $0 !~ start) exit} $0 == start {found=1}' "$openapi" | grep -Eiq "^[[:space:]]+$method:" || { echo "ci/compatibility-contract: $name method $method $path is not in OpenAPI" >&2; exit 1; }
  if [[ "$name" == events ]]; then
    grep -A20 -F "  $path:" "$openapi" | grep -Fq 'text/event-stream' || { echo 'ci/compatibility-contract: SSE media type missing from OpenAPI' >&2; exit 1; }
  fi
  echo "ci/compatibility-contract: verified $name $method $path -> $status${content_type:+ ($content_type)}"
done < <(jq -r '.assertions[] | [.name,.method,.path,(.status|tostring),(.content_type // "")] | @tsv' "$spec")

echo 'ci/compatibility-contract: static assertion specification passed'
