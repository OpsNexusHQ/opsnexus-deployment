# CI-3 Design Review

## 1. Executive Summary

The CI-3 design is correctly scoped to Docker Compose deployment validation and accurately captures the current topology, health endpoint, migration behavior, multi-repository build context, and major gaps.

It is **NOT READY FOR CI-3 IMPLEMENTATION** yet. The design still leaves several implementation-critical decisions ambiguous:

- exact application repository revisions and workspace assembly are not selected;
- exact Docker/Compose/action/tool versions and immutable action references are not specified;
- migration verification does not identify the exact expected schema evidence;
- dashboard-to-backend smoke behavior is described as an assumption rather than an executable check;
- cleanup and diagnostic steps are proposed, but their exact execution structure is not defined.

These are design precision issues, not requests for deployment redesign.

## 2. Current Deployment Topology

The current `main` repository contains:

- `docker-compose.yml`
- `backend/Dockerfile`
- `dashboard/Dockerfile`
- `dashboard/nginx.conf`
- `.env.example`
- README and security/contribution documentation
- no deployment workflow, scripts, or deployment tests

Compose defines:

- `postgres:16-alpine` with a named `postgres_data` volume and `pg_isready` healthcheck;
- a backend built from the parent `/OpsNexus` context using `backend/Dockerfile`;
- a dashboard built from the same parent context using `dashboard/Dockerfile`;
- one bridge network;
- host ports 8080 and 5173;
- backend dependency on PostgreSQL health;
- dashboard dependency only on backend container start.

The backend connects to PostgreSQL and runs embedded migrations before starting its HTTP server. `GET /health` performs a database ping and returns HTTP 200 with `status: ok` and `database: ok`, or HTTP 503 when degraded.

The dashboard is static nginx content. It compiles `VITE_API_BASE_URL`; absent an injected build value, application code defaults to `http://localhost:8080`. nginx does not proxy `/api`.

The deployment repository contains an ignored local `.env` in this workspace, while `.env.example` is tracked. No `.env` file is tracked by Git.

## 3. Audit Findings Verification

The design accurately records:

- absent backend and dashboard Compose healthchecks;
- dashboard dependency on backend start rather than readiness;
- floating base image tags;
- parent multi-repository build context;
- automatic embedded migrations;
- database-aware backend health behavior;
- absence of deployment CI;
- agent remaining outside Compose;
- lack of production secrets in the repository.

The design does not incorrectly claim that the agent is part of the Compose stack or that browser testing exists.

## 4. CI-3 Design Review

The proposed check categories are appropriate:

- configuration validation;
- image build validation;
- startup/readiness validation;
- smoke testing;
- diagnostics and cleanup.

The design correctly avoids Kubernetes, cloud infrastructure, production deployment, application changes, and broad security tooling.

However, implementation cannot safely begin until the build-context and revision policy is made concrete. The phrase “exact compatible application revisions” is not itself an executable rule.

## 5. Reproducibility Review

The design correctly identifies that the Dockerfiles require a parent context containing sibling repositories. This avoids incorrectly treating `opsnexus-deployment` as a monorepo.

The design must select one concrete method before implementation:

1. check out deployment plus sibling repositories at explicit commit SHAs; or
2. assemble a temporary workspace from explicit repository/ref inputs.

It must also specify the exact refs for `opsnexus-common`, `opsnexus-backend`, and `opsnexus-dashboard`. “Declared refs” or “compatible revisions” is insufficient.

The current image tags are floating:

- `postgres:16-alpine`
- `golang:1.25`
- `debian:bookworm-slim`
- `node:22-alpine`
- `nginx:alpine`

Leaving image pinning for a later production-hardening change is reasonable, but CI-3 must explicitly state that it validates current floating tags and does not claim byte-for-byte reproducibility.

## 6. Health/Readiness Review

The design correctly distinguishes container start from readiness and requires:

- PostgreSQL healthcheck;
- backend HTTP/database health;
- dashboard HTTP reachability;
- bounded polling and hard timeouts.

The backend readiness requirement is precise enough: HTTP 200 plus JSON `status` and `database` values.

The dashboard check is not yet precise enough. It should specify the exact request, expected status, and minimum response evidence, for example:

- `curl --fail --silent --show-error http://127.0.0.1:5173/`;
- non-empty response;
- expected application entrypoint marker;
- optional static asset request.

It should separately state whether the smoke test calls the backend from the host or from a container. This matters because the dashboard’s compiled default uses `localhost:8080` from a browser, while `localhost` inside the dashboard container is not the backend.

## 7. PostgreSQL/Migration Review

The design correctly requires an empty disposable volume, PostgreSQL readiness, backend startup, migration execution, restart, and repeatability.

The migration evidence remains ambiguous. It must name the exact verification, such as:

- a specific table created by the embedded migrations;
- a disposable `psql` command run inside the PostgreSQL container; or
- a safe backend endpoint whose successful response proves the required schema exists.

The design should also specify the expected behavior if migration startup fails: backend readiness must time out/fail, logs must be collected, and the original failure must remain non-zero.

## 8. Dashboard Review

The design appropriately avoids browser testing. HTTP reachability is sufficient for the current phase, provided the request and expected response are specified.

The design correctly notices that nginx does not proxy API requests and that `VITE_API_BASE_URL` is compiled into the dashboard. The implementation plan must choose whether CI:

- validates only static dashboard reachability; or
- validates the compiled API URL and host-published backend endpoint separately.

It must not imply full dashboard/backend browser integration without browser automation.

## 9. Security/Secrets Review

The design is appropriately secret-safe:

- test-only values;
- no production credentials;
- no required GitHub secrets;
- temporary environment file;
- no environment-file upload;
- cleanup of temporary values.

The implementation should explicitly prevent accidental use of a developer `.env` by passing a generated `--env-file` or equivalent controlled environment to Compose. It should also avoid printing the generated file or database URL in diagnostics.

## 10. CI Workflow Design Review

The proposed permissions and PR/manual triggers are appropriate. Required design details are still missing:

- exact workflow filename;
- immutable SHAs and reviewed versions for checkout and Docker setup actions;
- runner/platform requirement;
- Docker and Compose version policy;
- exact workspace checkout/revision commands;
- exact Compose project name;
- exact environment-file path;
- exact timeout values;
- exact polling commands;
- exact log/status collection commands;
- exact cleanup command and volume-removal behavior.

The five stable job names are sensible, but a separate cleanup job must explicitly depend on the validation jobs and use `always()`, or cleanup should be a final step in the same job. Otherwise cleanup ordering is ambiguous.

## 11. Failure Diagnostics Review

The design correctly requires diagnostics without masking failures and names service status and logs as evidence.

It should specify the exact diagnostic bundle:

- `docker compose ps --all`;
- `docker compose images`;
- `docker inspect` health/status for PostgreSQL, backend, and dashboard;
- `docker compose logs --no-color postgres backend dashboard`;
- sanitized Compose configuration where safe.

It should explicitly state that logs are emitted to the job log or uploaded only after secret review. Database URLs and environment values must not be printed.

## 12. Cleanup Review

The design requires cleanup after success and failure, isolated project naming, and removal of the disposable volume. That is correct.

The exact implementation structure is not yet specified. The design must require cleanup with `always()` and ensure it runs after build, startup, health, and smoke failures. It should also distinguish failures before Compose creates resources from failures after startup.

## 13. Stable Job Name Review

The proposed names are concise and suitable for branch protection:

- `ci/deployment-config`
- `ci/deployment-build`
- `ci/deployment-startup`
- `ci/deployment-smoke`
- `ci/deployment-cleanup`

The cleanup check should not be treated as the product-validation gate if it only performs cleanup. The design should clarify whether cleanup is a job/check or an unconditional final step in the validation job.

## 14. Scope Assessment

Scope is appropriately narrow. The design does not introduce architecture changes, Kubernetes, cloud resources, agent deployment, browser testing, image pinning, or broad security tooling.

The unresolved revision/workspace policy is a CI implementation prerequisite, not scope expansion.

## 15. Findings Table

| Severity | Finding |
|---|---|
| HIGH | Exact sibling repository refs and workspace assembly method are not selected, so the multi-repository build cannot yet be implemented deterministically. |
| HIGH | Exact migration evidence is not defined; “safe read path or SQL inspection” leaves a required validation decision to implementation. |
| HIGH | Dashboard smoke behavior and host/container API URL semantics are not specified precisely enough to prove the intended topology. |
| MEDIUM | Exact action SHAs, Docker/Compose versions, runner requirements, timeouts, and polling commands are unspecified. |
| MEDIUM | Failure diagnostics are described but the exact sanitized command set and artifact/log policy are not defined. |
| MEDIUM | Cleanup ordering and the cleanup job-versus-final-step structure are ambiguous. |
| LOW | Floating image tags remain a reproducibility limitation; deferring pinning is acceptable if explicitly documented as non-production-grade reproducibility. |
| INFORMATIONAL | No deployment CI, scripts, or tests currently exist. |

## 16. Required Design Changes

Before implementation, update the design to specify:

1. exact application repository commit SHAs or approved immutable refs;
2. the exact temporary workspace assembly method;
3. the exact migration/schema assertion;
4. the exact backend and dashboard smoke requests and expected responses;
5. whether API connectivity is tested from the host or a container;
6. immutable action references and Docker/Compose/runner policy;
7. exact timeouts and polling behavior;
8. exact sanitized diagnostics;
9. exact cleanup ordering and resource-removal command;
10. whether cleanup is a final step or a dependent job.

Do not implement these changes in this review.

## 17. Final Decision

NOT READY FOR CI-3 IMPLEMENTATION
