# Phase 0E CI-3 Deployment Validation Design

Status: design-only audit
Branch: phase0/ci-deployment-design
Repository baseline: `main`

## Objective

Validate the existing Docker Compose deployment topology without changing application architecture:

PostgreSQL -> backend -> dashboard, with the agent remaining an independently installed host service.

The first implementation should prove configuration validity, image builds, service readiness, migrations, and a minimal HTTP smoke path. It must not introduce Kubernetes, cloud infrastructure, release automation, or production secrets.

## Current inventory

- `docker-compose.yml` defines `postgres`, `backend`, and `dashboard` on one bridge network.
- PostgreSQL uses `postgres:16-alpine`, a named `postgres_data` volume, and a `pg_isready` healthcheck.
- Backend builds from the parent workspace using `backend/Dockerfile`, exposes port 8080, and waits for PostgreSQL health before starting.
- Dashboard builds from `dashboard/Dockerfile`, serves static files through nginx, and exposes host port 5173.
- Backend startup connects to PostgreSQL and executes embedded migrations before serving HTTP.
- Backend `/health` reports both service and database state and returns HTTP 503 when the database is unavailable.
- Dashboard uses `VITE_API_BASE_URL`, defaulting to `http://localhost:8080`; nginx currently serves static files and does not proxy `/api`.
- The agent is not part of Compose and is documented as installed on the target host.
- There is no deployment workflow, deployment test, compose test script, or deployment-specific CI today.
- `.env.example` is the only environment template; no `.env` or credentials are tracked.

## Confirmed gaps

1. Backend has no Compose healthcheck, so Compose cannot express backend readiness.
2. Dashboard has no healthcheck and only depends on backend container start, not backend readiness.
3. `postgres:16-alpine`, `golang:1.25`, `debian:bookworm-slim`, `node:22-alpine`, and `nginx:alpine` are floating image tags.
4. Dockerfiles depend on a multi-repository parent build context containing sibling `opsnexus-common`, `opsnexus-backend`, and `opsnexus-dashboard` directories. A deployment-repository checkout alone cannot build the stack.
5. The dashboard image build does not receive `VITE_API_BASE_URL`; the application therefore uses its compiled default. This is workable for the documented localhost smoke path but should be made an explicit test assumption.
6. Compose interpolates required variables but does not itself provide a safe CI environment file or validate missing variables before startup.
7. Migrations are automatic inside backend startup. CI must verify that startup applies them and that a second startup is repeatable.
8. No separate readiness endpoint exists; `/health` is a database-aware health endpoint and is suitable for the initial validation gate.
9. External image and Go/npm dependency downloads remain network-dependent and need visible failures, bounded retries only where appropriate, and no success suppression.

## Proposed CI checks

Use stable job names after implementation:

- `ci/deployment-config` — render and validate Compose configuration using a generated, non-secret CI environment file.
- `ci/deployment-build` — build the PostgreSQL-independent application images from the required workspace context.
- `ci/deployment-startup` — start the stack, wait for PostgreSQL and backend readiness, and collect logs on failure.
- `ci/deployment-smoke` — verify backend health, migration-created behavior, dashboard HTTP reachability, and the dashboard-to-backend browser-visible URL assumption.
- `ci/deployment-cleanup` — always collect diagnostics and remove containers/volumes created by the run.

The exact workflow should use `permissions: contents: read`, pull requests targeting `main`, and `workflow_dispatch`. No repository secrets are needed for the first local-only smoke environment.

## Validation sequence

1. Check out the deployment repository and the exact compatible application revisions required by the current Dockerfiles.
2. Generate a temporary CI environment file from non-secret test values; never commit it or upload it.
3. Run `docker compose config` with that environment and fail on interpolation or syntax errors.
4. Build the backend and dashboard images using the parent workspace context; fail on any dependency, compile, or image error.
5. Start PostgreSQL, backend, and dashboard with an isolated Compose project name.
6. Wait for PostgreSQL health and query backend `/health` until it returns HTTP 200 with database `ok`.
7. Verify the backend has completed embedded migrations by exercising a safe read endpoint or inspecting the database schema through a disposable validation command.
8. Verify dashboard port 5173 returns the expected HTML and static assets.
9. Verify the dashboard’s configured API base URL is reachable from the smoke-test environment; do not claim full browser/API behavior without browser testing.
10. Run a second backend restart and confirm migrations remain idempotent.
11. On every failure, print sanitized service status and logs, then remove the isolated stack and temporary environment.

## Health and readiness requirements

- PostgreSQL readiness is the existing `pg_isready` healthcheck.
- Backend readiness is HTTP `GET /health`, requiring HTTP 200 and JSON status `ok`, database `ok`.
- Dashboard readiness is an HTTP response from nginx on port 5173 with non-empty application HTML.
- A container being running is not sufficient evidence of readiness.
- CI must use bounded polling with a hard timeout and fail visibly on timeout.

## Migration strategy

The current backend embeds migrations and runs them during database connection. CI-3 should validate this existing behavior rather than add a migration tool:

- start against an empty disposable named volume;
- wait for backend readiness;
- verify startup succeeds and the expected schema exists through a safe read path or disposable SQL inspection;
- restart the backend against the same volume;
- verify readiness remains successful and no migration failure occurs.

No production database, persistent external volume, or real credential may be used.

## Secrets and environment strategy

- Use generated test-only values in the workflow workspace.
- Keep `OPSNEXUS_API_AUTH_ENABLED=false` for the initial smoke path unless an authenticated smoke case is separately designed.
- Do not expose `.env` contents in logs or artifacts.
- Do not use repository secrets for ordinary pull-request validation.
- Remove the temporary environment file during unconditional cleanup.
- Treat the example password as test-only and never as a production default.

## Reproducibility considerations

CI-3 should initially validate the current stack without broad image redesign. The floating image tags are a reproducibility gap and should be resolved by a separately reviewed image-pinning change before CI-3 is considered a production-grade supply-chain control. The first CI can record resolved image digests without silently changing Dockerfiles, but must not claim byte-for-byte reproducibility.

The multi-repository build context must be made explicit. The implementation should use checked-out sibling repositories at declared refs or another reviewed workspace assembly method; it must not silently build arbitrary local files.

## Failure behavior and cleanup

- Configuration, build, readiness, smoke, and migration failures must produce non-zero jobs.
- No `|| true`, unconditional success, or `continue-on-error` may hide product failures.
- Diagnostic log collection may use `if: failure()` or `if: always()` but must not alter the original result.
- Cleanup must run with `always()` and use an isolated project name.
- The disposable database volume must be removed after the run.

## Out of scope

- Kubernetes or other orchestration platforms.
- Cloud infrastructure and production deployment.
- Application/runtime/API schema changes.
- Agent packaging or agent deployment.
- Browser automation; dashboard reachability remains an HTTP smoke check.
- Security scanning, SBOM generation, release workflows, and registry publishing.
- Changing image tags or Dockerfile architecture before a dedicated review.

## Implementation gate

Implementation may begin only after this design is reviewed and the compatible application revisions/build-context policy are explicitly selected. The first implementation should add only the deployment workflow and narrowly scoped validation scripts/configuration required to execute the sequence above.
