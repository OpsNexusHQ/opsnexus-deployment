# CI-3 Implementation Review

## 1. Executive Summary

The implementation is narrowly scoped to one deployment workflow and uses the approved repository baselines, immutable checkout references, controlled test values, Compose validation, image builds, readiness checks, migration validation, restart validation, diagnostics, and cleanup.

The implementation is **NOT READY TO PUSH** because three HIGH issues remain:

1. Checkout credentials are persisted by default and copied with the checked-out `.git` directories into the Docker build context.
2. Startup/smoke cleanup has a `working-directory` that does not exist if checkout or workspace assembly fails, so cleanup is not guaranteed on all setup failures.
3. Backend polling and dashboard smoke curls have no per-request timeout. A hung curl can exceed the stated 120/60-second readiness limits; only the broader 20-minute job timeout bounds it.

The local Docker daemon limitation is not itself a blocker.

## 2. Scope/Diff Review

Against deployment `main` (`262c78fa28d6a1ebc63363012802b348375712f4`), the branch contains:

- approved design document `CI3_DEPLOYMENT_VALIDATION_DESIGN.md`;
- `.github/workflows/ci-deployment-validation.yml`.

The implementation commit is `d3f6ad83bccfb37b8b26706fa84c91ac77a9def1`, with no unexpected commits after the approved design commit. `git diff --check` passes.

No Dockerfiles, Compose files, source, migrations, image tags, application dependencies, or generated artifacts were changed. The working tree has one pre-existing untracked `CI3_DESIGN_REVIEW.md`; it was not modified or committed by this implementation.

## 3. Design-to-Implementation Review

Implemented correctly:

- temporary `$RUNNER_TEMP/OpsNexus` workspace;
- exact four-repository SHA selection;
- explicit environment file and Compose `--env-file`;
- Compose configuration validation;
- application image builds;
- PostgreSQL health polling;
- backend health polling;
- `public.telemetry_hourly` assertion;
- backend restart and second health validation;
- dashboard HTTP smoke test;
- diagnostics and unconditional cleanup steps;
- stable check names;
- 20-minute job timeouts.

Differences or defects:

- The design specifies a 60-second dashboard readiness limit, but the implementation performs one dashboard curl without a 60-second polling/deadline mechanism.
- The design requires cleanup after failures before resources exist; the workflow cleanup steps depend on a deployment working directory that may not exist after setup failure.
- The design requires bounded readiness behavior; curls lack `--max-time`, so the loop deadline is not a hard deadline if curl itself hangs.
- The design requires safe workspace handling; default checkout credential persistence leaves credentials in copied Git metadata.

## 4. Workspace/Revision Review

The workflow checks out:

- deployment `262c78fa28d6a1ebc63363012802b348375712f4`;
- common `b571c0a7ae028906d08cf108e357350dda9384d7`;
- backend `8b1e3340fee81f52a88bde293dd0a05fbc132668`;
- dashboard `fe5f4d309b09ed39fceac73ccdfbddfb1c562d97`.

Each repository is first checked out under `ci-source/`, then copied to:

```text
$RUNNER_TEMP/OpsNexus/
  opsnexus-deployment/
  opsnexus-common/
  opsnexus-backend/
  opsnexus-dashboard/
```

Compose runs from the deployment directory and uses the existing parent-context Dockerfiles. The path design is correct and does not create a monorepo.

## 5. Workflow/Supply-Chain Review

All action references use:

```text
actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
```

No floating action references or third-party downloads are present. The workflow uses the preinstalled Docker Engine and Compose plugin on `ubuntu-24.04`, as approved.

The workflow does not set `persist-credentials: false` on checkout. This is a supply-chain and secret-handling defect because checkout credentials may remain in `.git/config`, are copied into the temporary workspace, and can enter the Docker build context.

## 6. Permissions/Fork Safety

The workflow sets:

```yaml
permissions:
  contents: read
```

No repository secrets or production credentials are required. Test-only values are generated in the workflow. Fork safety is otherwise appropriate, subject to the checkout credential-persistence issue.

## 7. Environment/Secrets

The workflow creates a temporary test environment file under `$RUNNER_TEMP`, passes it explicitly to Compose, does not print it, and removes it during cleanup. No shell tracing, `env`, or `printenv` is used.

The values are test-only. The database URL is present in the temporary file but is not intentionally printed. The main risk is credential persistence from checkout metadata, not the generated test values themselves.

## 8. Deployment Validation Review

### Configuration

`docker compose --env-file "$RUNNER_TEMP/opsnexus-ci.env" config --quiet` runs from the assembled deployment directory and propagates failures.

### Build

The workflow builds the Compose services with the parent workspace context. Startup and smoke jobs use `up -d --build` or an explicit build before startup because GitHub jobs have isolated runners.

The current floating image tags remain unchanged and the workflow does not claim byte-for-byte image reproducibility.

### PostgreSQL

The workflow polls the actual `opsnexus-postgres` health state for 120 seconds at 5-second intervals. The polling condition is correct, but the broader curl timeout issue remains for backend checks.

### Backend

The workflow checks `http://127.0.0.1:8080/health` and requires both JSON fields `status: ok` and `database: ok`. It repeats the same validation after `docker compose restart backend`.

### Migration

The workflow executes PostgreSQL `psql` inside the running container and checks:

```sql
SELECT to_regclass('public.telemetry_hourly');
```

The trimmed result must be `telemetry_hourly`, matching the existing `004_phase5.sql` migration. This is an appropriate concrete schema assertion.

### Dashboard

The workflow requests `http://127.0.0.1:5173/`, requires non-empty content, and checks the current entrypoint markers:

- `<title>opsnexus-dashboard</title>`;
- `<div id="root"></div>`.

It does not claim browser-level API integration or add browser automation.

## 9. Diagnostics

Startup and smoke failures collect Compose service status, images, container inspection, and non-colored service logs before cleanup. Diagnostics do not use `continue-on-error` and do not alter required validation results.

Diagnostics are conditional on resource existence through shell conditionals, which is appropriate for failures before containers are created. However, diagnostics themselves use a deployment `working-directory`, so setup failures before that directory exists can prevent the diagnostic/cleanup steps from starting.

## 10. Cleanup

The startup and smoke jobs use `if: ${{ always() }}` and run:

```bash
docker compose --project-name "$PROJECT" --env-file "$RUNNER_TEMP/opsnexus-ci.env" down --volumes --remove-orphans
```

They remove temporary workspaces and environment files. Config/build jobs also remove temporary files.

The cleanup command is correct after successful assembly, startup, readiness, migration, restart, and smoke failures. It is not guaranteed when setup fails before `$RUNNER_TEMP/OpsNexus/opsnexus-deployment` exists because the cleanup step declares that path as its working directory.

## 11. Findings

| Severity | Finding |
|---|---|
| HIGH | `actions/checkout` leaves credentials persisted by default; copied `.git` directories can carry the token into the Docker build context. |
| HIGH | Startup/smoke cleanup steps require a deployment working directory that may not exist after checkout or workspace assembly failure. |
| HIGH | Backend polling and dashboard smoke curls lack `--max-time`; stated 120/60-second bounds are not hard if curl hangs. |
| MEDIUM | `ci/deployment-build` requests `docker compose build postgres backend dashboard` although PostgreSQL is image-only in Compose; actual pull/build behavior should be made explicit. |
| INFORMATIONAL | Local Docker Engine exists, but the daemon socket was unavailable, so live image/build/startup/smoke validation was not run locally. |
| INFORMATIONAL | No `needs:` relationships are used; jobs intentionally run independently because Docker state is not shared between GitHub jobs. |

## 12. Required Fixes

Before pushing:

1. Add `persist-credentials: false` to every checkout step, or otherwise ensure checkout credentials are not copied into the temporary workspace/build context.
2. Remove `working-directory` from unconditional cleanup steps and `cd` conditionally only when the deployment directory exists, while always removing the temporary workspace and environment file.
3. Add explicit per-request curl timeouts and implement the dashboard 60-second bounded validation required by the design.
4. Make PostgreSQL image validation explicit in the build job, either by validating the image through the Compose startup path or by using a Compose-supported service selection that does not falsely describe an image-only service as built.

## 13. Final Decision

NOT READY TO PUSH

## 14. Corrective Review

The four findings were corrected without changing deployment architecture:

- Every checkout now sets `persist-credentials: false`, preventing checkout tokens from being retained in copied Git metadata or entering the Docker build context.
- Diagnostics and cleanup no longer declare the deployment directory as their workflow working directory. They conditionally enter it only when it exists, while always attempting temporary workspace and environment-file removal.
- Backend and dashboard HTTP requests now use `--connect-timeout 5 --max-time 10`. Dashboard validation polls for up to 60 seconds; backend polling remains bounded at 120 seconds with 5-second intervals.
- PostgreSQL is explicitly handled as an image-only Compose service with `docker compose pull --quiet postgres`; only locally-built backend and dashboard services are passed to `docker compose build`.

## 15. Corrective Validation

- YAML parsing: passed.
- Embedded shell syntax parsing: passed.
- Compose configuration validation: passed where the local Docker client could run it.
- Baseline SHA verification: passed.
- Immutable action reference review: passed.
- Curl timeout and polling review: passed.
- Cleanup prerequisite review: passed.
- `git diff --check`: passed.
- Live Docker build/startup/smoke execution: unavailable because the local Docker daemon socket is inaccessible.

No Dockerfiles, Compose files, source, migrations, image tags, or application dependencies changed. The remaining untracked `CI3_DESIGN_REVIEW.md` is pre-existing and untouched.

## 16. Final Decision After Correction

READY TO PUSH
