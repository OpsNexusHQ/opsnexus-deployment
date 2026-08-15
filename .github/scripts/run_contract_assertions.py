#!/usr/bin/env python3
"""Execute the fixed CI-4 contract profile against a running backend."""

import json
import sys
import urllib.error
import urllib.request

TIMEOUT = 10
AGENT_ID = "ci-compatibility-agent"


def fail(message: str) -> None:
    raise SystemExit(f"ci/compatibility-contract: {message}")


def substitute(value):
    if isinstance(value, str):
        return value.replace("__agent_id__", AGENT_ID)
    if isinstance(value, list):
        return [substitute(item) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item) for key, item in value.items()}
    return value


def request(base_url: str, assertion: dict) -> tuple[int, str, bytes]:
    path = assertion["path"].replace("{id}", AGENT_ID).replace("{agent_id}", AGENT_ID)
    request_data = assertion.get("request")
    headers = {}
    payload = None
    if request_data:
        headers["Content-Type"] = request_data["content_type"]
        payload = json.dumps(substitute(request_data["body"])).encode("utf-8")
    request_obj = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=payload,
        headers=headers,
        method=assertion["method"],
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=TIMEOUT) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(512 if assertion["name"] == "events" else 1024 * 1024)
            return response.status, content_type, body
    except urllib.error.HTTPError as exc:
        body = exc.read(1024)
        fail(f"{assertion['name']} {assertion['method']} {path}: expected {assertion['response']['status']}, got HTTP {exc.code}; body={body[:256]!r}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        fail(f"{assertion['name']} {assertion['method']} {path}: request failed: {exc}")


def field_value(document, path: str):
    value = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            fail(f"response is missing required field {path}")
        value = value[part]
    return value


def validate(assertion: dict, status: int, content_type: str, body: bytes) -> None:
    response_spec = assertion["response"]
    if status != response_spec["status"]:
        fail(f"{assertion['name']} expected HTTP {response_spec['status']}, got {status}")
    expected_content_type = response_spec.get("content_type")
    if expected_content_type and not content_type.lower().startswith(expected_content_type.lower()):
        fail(f"{assertion['name']} expected Content-Type {expected_content_type}, got {content_type}")
    if response_spec.get("body_contains"):
        if response_spec["body_contains"].encode() not in body:
            fail(f"{assertion['name']} response did not contain {response_spec['body_contains']!r}")
        return
    try:
        document = json.loads(body)
    except json.JSONDecodeError as exc:
        fail(f"{assertion['name']} returned invalid JSON: {exc}")
    for field in response_spec.get("fields", []):
        value = field_value(document, field["path"])
        expected_type = field["type"]
        actual_type = "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "string" if isinstance(value, str) else "null"
        if actual_type != expected_type:
            fail(f"{assertion['name']} field {field['path']} expected type {expected_type}, got {actual_type}")
        if "equals" in field and value != substitute(field["equals"]):
            fail(f"{assertion['name']} field {field['path']} expected {field['equals']!r}, got {value!r}")


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: run_contract_assertions.py SPEC BASE_URL")
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    if spec.get("profile") != "contract-basic":
        fail("unexpected assertion profile")
    for assertion in spec["assertions"]:
        status, content_type, body = request(sys.argv[2], assertion)
        validate(assertion, status, content_type, body)
        print(f"ci/compatibility-contract: {assertion['name']} passed")
    print("ci/compatibility-contract: contract-basic assertions passed")


if __name__ == "__main__":
    main()
