#!/usr/bin/env python3
# frozen_string_literal: true
"""
OpsNexus CI-4 Compatibility Set Resolver

Resolves authoritative commit SHAs for all OpsNexus platform components:
  - opsnexus-common
  - opsnexus-agent
  - opsnexus-api
  - opsnexus-backend
  - opsnexus-dashboard
  - opsnexus-cli
  - opsnexus-deployment
  - opsnexus-docs

Selection Model:
  base branch platform manifest (platform-compatibility.yaml)
  + PR context / changed component PR HEAD SHA(s)
  => selected compatibility set (immutable 40-character hex commit SHAs)
"""

import argparse
import json
import os
import re
import sys
import yaml

KNOWN_COMPONENTS = [
    "opsnexus-common",
    "opsnexus-agent",
    "opsnexus-api",
    "opsnexus-backend",
    "opsnexus-dashboard",
    "opsnexus-cli",
    "opsnexus-deployment",
    "opsnexus-docs",
]

HEX_SHA_REGEX = re.compile(r"^[0-9a-fA-F]{40}$")


def fail(msg: str) -> None:
    sys.stderr.write(f"ci/compatibility-set-resolver: ERROR: {msg}\n")
    sys.exit(1)


def validate_sha(component: str, sha: str) -> str:
    if not isinstance(sha, str) or not HEX_SHA_REGEX.match(sha):
        fail(f"{component} SHA '{sha}' is invalid (must be 40-character hex string)")
    return sha.lower()


def parse_manifest(filepath: str) -> dict:
    if not os.path.exists(filepath):
        fail(f"Manifest file not found at '{filepath}'")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        fail(f"Failed to parse YAML manifest '{filepath}': {e}")

    if not isinstance(data, dict) or "components" not in data or not isinstance(data["components"], dict):
        fail(f"Manifest '{filepath}' missing 'components' mapping")

    components = data["components"]
    result = {}
    for comp in KNOWN_COMPONENTS:
        if comp not in components:
            fail(f"Manifest '{filepath}' missing component '{comp}'")
        comp_data = components[comp]
        if not isinstance(comp_data, dict) or "commit" not in comp_data:
            fail(f"Manifest component '{comp}' missing 'commit' SHA")
        result[comp] = validate_sha(comp, str(comp_data["commit"]))

    return result


def main():
    parser = argparse.ArgumentParser(description="Resolve OpsNexus CI-4 Compatibility Set")
    parser.add_argument("--manifest", required=True, help="Path to base platform-compatibility.yaml")
    parser.add_argument("--pr-repo", default="", help="Component repository name of the current PR")
    parser.add_argument("--pr-sha", default="", help="PR HEAD commit SHA (40-char hex)")
    parser.add_argument("--pr-manifest", default="", help="Path to modified platform-compatibility.yaml in PR (if docs PR)")
    parser.add_argument("--github-output", default="", help="Path to GITHUB_OUTPUT environment file")
    parser.add_argument("--json-output", default="", help="Path to write JSON result")

    args = parser.parse_args()

    # 1. Read Base Manifest
    selected_set = parse_manifest(args.manifest)
    sources = {comp: "base manifest" for comp in KNOWN_COMPONENTS}

    # 2. Apply PR HEAD SHA substitution if specified
    if args.pr_repo:
        norm_repo = args.pr_repo.strip()
        # Handle short names like "backend", "agent" -> "opsnexus-backend", "opsnexus-agent"
        if not norm_repo.startswith("opsnexus-"):
            norm_repo = f"opsnexus-{norm_repo}"

        if norm_repo in KNOWN_COMPONENTS:
            if args.pr_sha:
                pr_sha = validate_sha(norm_repo, args.pr_sha.strip())
                selected_set[norm_repo] = pr_sha
                sources[norm_repo] = "PR HEAD"
        else:
            sys.stderr.write(f"ci/compatibility-set-resolver: WARNING: Unknown PR repo '{args.pr_repo}'\n")

    # 3. Handle Docs PR with modified manifest if provided
    if args.pr_manifest and os.path.exists(args.pr_manifest):
        pr_manifest_set = parse_manifest(args.pr_manifest)
        for comp, sha in pr_manifest_set.items():
            if sha != selected_set[comp]:
                selected_set[comp] = sha
                sources[comp] = "PR Manifest"

    # 4. Print Sanitized Summary Table (Task 13 requirement)
    sys.stderr.write("\n====================================================\n")
    sys.stderr.write("OpsNexus CI-4 Selected Compatibility Set\n")
    sys.stderr.write("====================================================\n")
    sys.stderr.write(f"{'component':<20} {'selected commit SHA':<42} {'source':<15}\n")
    sys.stderr.write("-" * 79 + "\n")
    for comp in KNOWN_COMPONENTS:
        sys.stderr.write(f"{comp:<20} {selected_set[comp]:<42} {sources[comp]:<15}\n")
    sys.stderr.write("====================================================\n\n")

    # 5. Output to GITHUB_OUTPUT if provided
    if args.github_output:
        try:
            with open(args.github_output, "a", encoding="utf-8") as f:
                for comp, sha in selected_set.items():
                    short_key = comp.replace("opsnexus-", "")
                    f.write(f"{short_key}_sha={sha}\n")
                    f.write(f"{comp.replace('-', '_')}_sha={sha}\n")
        except Exception as e:
            fail(f"Failed to write to GITHUB_OUTPUT '{args.github_output}': {e}")

    # 6. Output JSON if requested
    if args.json_output:
        try:
            with open(args.json_output, "w", encoding="utf-8") as f:
                json.dump(selected_set, f, indent=2)
        except Exception as e:
            fail(f"Failed to write JSON output '{args.json_output}': {e}")

    # Print JSON to stdout for callers
    print(json.dumps(selected_set))


if __name__ == "__main__":
    main()
