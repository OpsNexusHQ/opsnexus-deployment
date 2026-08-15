#!/usr/bin/env bash
set -euo pipefail

base_url="${OPSNEXUS_CONTRACT_BASE_URL:-http://127.0.0.1:8080}"
agent_id="ci-compatibility-agent"
request_timeout=(--connect-timeout 5 --max-time 10 --fail --silent --show-error)

fail_assertion() { echo "ci/compatibility-contract: $1" >&2; exit 1; }

request_json() {
  local method="$1" path="$2" body="${3:-}" response_file status
  response_file="$(mktemp)"
  if [[ -n "$body" ]]; then
    status="$(curl "${request_timeout[@]}" -X "$method" -H 'Content-Type: application/json' --data "$body" -o "$response_file" -w '%{http_code}' "$base_url$path")" || { rm -f "$response_file"; fail_assertion "$method $path request failed"; }
  else
    status="$(curl "${request_timeout[@]}" -X "$method" -o "$response_file" -w '%{http_code}' "$base_url$path")" || { rm -f "$response_file"; fail_assertion "$method $path request failed"; }
  fi
  printf '%s\n%s' "$status" "$response_file"
}

registration='{"id":"ci-compatibility-agent","name":"CI Compatibility Agent","hostname":"ci","os":"linux","arch":"amd64","version":"ci"}'
result="$(request_json POST /api/v1/agents/register "$registration")"
status="${result%%$'\n'*}"; file="${result#*$'\n'}"
[[ "$status" == 201 ]] || fail_assertion "POST /api/v1/agents/register expected 201, got $status"
jq -e --arg id "$agent_id" '.id == $id' "$file" >/dev/null || fail_assertion "registration response missing id"
rm -f "$file"

telemetry='{"agent_id":"ci-compatibility-agent","timestamp":"2026-08-16T00:00:00Z","metrics":{"system":{"timestamp":"2026-08-16T00:00:00Z"}}}'
result="$(request_json POST "/api/v1/agents/$agent_id/telemetry" "$telemetry")"
status="${result%%$'\n'*}"; file="${result#*$'\n'}"
[[ "$status" == 201 ]] || fail_assertion "POST telemetry expected 201, got $status"
jq -e '.status == "accepted"' "$file" >/dev/null || fail_assertion "telemetry response missing accepted status"
rm -f "$file"

for assertion in health metrics overview alerts; do
  case "$assertion" in
    health) path="/api/v1/agents/$agent_id/health"; fields='.agent_id and .status' ;;
    metrics) path="/api/v1/agents/$agent_id/metrics"; fields='.agent_id and .timestamp and (.metrics | type == "object")' ;;
    overview) path="/api/v1/overview"; fields='has("total") and has("healthy") and has("stale") and has("offline")' ;;
    alerts) path="/api/v1/alerts"; fields='(.alerts | type == "array")' ;;
  esac
  result="$(request_json GET "$path")"
  status="${result%%$'\n'*}"; file="${result#*$'\n'}"
  [[ "$status" == 200 ]] || fail_assertion "GET $path expected 200, got $status"
  jq -e "$fields" "$file" >/dev/null || fail_assertion "GET $path response shape assertion failed"
  rm -f "$file"
done

sse_headers="$(mktemp)"; sse_body="$(mktemp)"
set +e
curl --connect-timeout 5 --max-time 10 --fail --silent --show-error -D "$sse_headers" -o "$sse_body" "$base_url/api/v1/events"
sse_exit=$?
set -e
[[ "$sse_exit" == 0 || "$sse_exit" == 28 ]] || fail_assertion "GET /api/v1/events curl exit $sse_exit"
grep -Eiq '^content-type: text/event-stream($|;)' "$sse_headers" || fail_assertion "SSE content type missing"
grep -q ': connected' "$sse_body" || fail_assertion "SSE initial connection event missing"
rm -f "$sse_headers" "$sse_body"

echo "ci/compatibility-contract: contract-basic assertions passed"
