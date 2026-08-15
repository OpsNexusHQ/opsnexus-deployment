#!/usr/bin/env python3
"""Validate the fixed CI-4 assertion definition against OpenAPI 3.1."""

import json
import sys
from pathlib import Path

import yaml


def fail(message: str) -> None:
    raise SystemExit(f"ci/compatibility-contract: {message}")


def resolve_ref(ref: str, document: dict, source: Path):
    if ref.startswith("#/"):
        value = document
        for part in ref[2:].split("/"):
            value = value[part.replace("~1", "/").replace("~0", "~")]
        return value, document, source
    if "#" in ref:
        filename, pointer = ref.split("#", 1)
    else:
        filename, pointer = ref, ""
    external_source = (source.parent / filename).resolve()
    if not external_source.is_file():
        fail(f"referenced schema does not exist: {ref}")
    external = yaml.safe_load(external_source.read_text(encoding="utf-8"))
    if pointer:
        value = external
        for part in pointer.lstrip("/").split("/"):
            value = value[part.replace("~1", "/").replace("~0", "~")]
        return value, external, external_source
    return external, external, external_source


def dereference(schema: dict, document: dict, source: Path) -> dict:
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        target, target_doc, target_source = resolve_ref(schema["$ref"], document, source)
        return dereference(target, target_doc, target_source)
    if "allOf" in schema:
        merged = {"type": schema.get("type", "object"), "properties": {}, "required": []}
        for part in schema["allOf"]:
            item = dereference(part, document, source)
            merged["properties"].update(item.get("properties", {}))
            merged["required"].extend(item.get("required", []))
        merged["required"] = sorted(set(merged["required"]))
        return merged
    return schema


def response_schema(response: dict, content_type: str, document: dict, source: Path) -> dict:
    content = response.get("content", {})
    if content_type not in content:
        fail(f"response does not define content type {content_type}")
    return dereference(content[content_type].get("schema", {}), document, source)


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: validate_contract_basic.py SPEC OPENAPI")
    spec_path = Path(sys.argv[1])
    openapi_path = Path(sys.argv[2])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    api = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    if spec.get("profile") != "contract-basic":
        fail("unexpected assertion profile")
    for assertion in spec.get("assertions", []):
        name = assertion["name"]
        path = assertion["path"]
        method = assertion["method"].lower()
        operation = api.get("paths", {}).get(path, {}).get(method)
        if not operation:
            fail(f"{name}: {method.upper()} {path} is not in the authoritative OpenAPI contract")
        response_spec = assertion.get("response", {})
        status = str(response_spec["status"])
        response = operation.get("responses", {}).get(status)
        if not response:
            fail(f"{name}: OpenAPI operation has no response {status}")
        expected_type = response_spec.get("content_type")
        if expected_type:
            schema = response_schema(response, expected_type, api, openapi_path)
        else:
            schema = {}
        for field in response_spec.get("fields", []):
            field_path = field["path"].split(".")[0]
            if field_path not in schema.get("properties", {}):
                fail(f"{name}: response field {field['path']} is not defined by OpenAPI response {status}")
            field_schema = dereference(schema["properties"][field_path], api, openapi_path)
            actual_type = field_schema.get("type")
            expected_type_name = field["type"]
            compatible_types = {"number", "integer"} if expected_type_name == "number" else {expected_type_name}
            if actual_type and actual_type not in compatible_types:
                fail(f"{name}: response field {field['path']} type differs from OpenAPI")
        request_spec = assertion.get("request")
        if request_spec:
            request_body = operation.get("requestBody", {})
            request_content = request_body.get("content", {})
            request_type = request_spec["content_type"]
            if request_type not in request_content:
                fail(f"{name}: request does not define content type {request_type}")
            request_schema = dereference(request_content[request_type].get("schema", {}), api, openapi_path)
            for field in request_spec.get("required_fields", []):
                if field not in request_schema.get("required", []):
                    fail(f"{name}: request field {field} is not required by OpenAPI")
        if expected_type == "text/event-stream":
            if expected_type not in response.get("content", {}):
                fail(f"{name}: SSE media type is not defined by OpenAPI")
        print(f"ci/compatibility-contract: verified {name} {method.upper()} {path} -> {status}")
    print("ci/compatibility-contract: static assertion specification passed")


if __name__ == "__main__":
    main()
