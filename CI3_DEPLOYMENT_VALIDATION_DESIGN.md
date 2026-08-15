# Phase 0E CI-3 Deployment Validation Design

Status: corrected design, ready for implementation
Branch: `phase0/ci-deployment-design`
Deployment baseline: `262c78fa28d6a1ebc63363012802b348375712f4`

## Objective and scope

CI-3 validates the existing Docker Compose deployment topology without redesigning it:

PostgreSQL -> backend -> dashboard, with the agent remaining an independently installed host service.

CI-3 does not introduce Kubernetes, cloud infrastructure, production deployment, agent Compose integration, browser automation, application changes, Dockerfile redesign, Compose topology redesign, image tag pinning, broad security tooling, or deployment architecture changes.

## Immutable CI workspace

The Dockerfiles require a parent workspace containing sibling repositories. CI will create this exact temporary layout:

```text
$RUNNER_TEMP/OpsNexus/
├── opsnexus-deployment/
├── opsnexus-common/
├── opsnexus-backend/
└── opsnexus-dashboard/
```

The implementation checks out each repository at these immutable commits:

| Repository | CI-3 baseline SHA | Why selected |
|---|---|---|
| opsnexus-deployment | `262c78fa28d6a1ebc63363012802b348375712f4` | current deployment `main` |
| opsnexus-common | `b571c0a7ae028906d08cf108e357350dda9384d7` | current common `main` |
| opsnexus-backend | `8b1e3340fee81f52a88bde293dd0a05fbc132668` | current backend `main` |
| opsnexus-dashboard | `fe5f4d309b09ed39fceac73ccdfbddfb1c562d97` | current dashboard `main` |

The workflow must use detached checkouts of these exact SHAs, never floating branches or moving tags. Compose runs with its working directory set to `$RUNNER_TEMP/OpsNexus/opsnexus-deployment`; its build context remains `..`, which resolves to the temporary parent workspace required by the Dockerfiles.

This is not a monorepo conversion. The repositories remain separate Git histories and are assembled only into a disposable CI filesystem so the existing deployment Dockerfiles can consume their declared sibling paths. Any future revision change requires an intentional design/workflow diff updating the SHA table and a corresponding CI review.

## Current topology and known limitations

- `docker-compose.yml` defines `postgres`, `backend`, and `dashboard` on one bridge network.
- PostgreSQL uses `postgres:16-alpine`, a named `postgres_data` volume, and `pg_isready` healthchecking.
- Backend uses `backend/Dockerfile`, exposes host port 8080, and depends on PostgreSQL health.
- Dashboard uses `dashboard/Dockerfile`, serves static nginx content on host port 5173, and depends only on backend container start.
- Backend startup pings PostgreSQL, executes embedded SQL migrations in lexical filename order, and only then starts HTTP serving.
- Backend `GET /health` returns HTTP 200 with `{"status":"ok","database":"ok"}` only when the database ping succeeds; degraded state returns HTTP 503.
- Dashboard compiles `VITE_API_BASE_URL`, defaulting in application code to `http://localhost:8080`; nginx does not proxy `/api`.
- The agent is not in Compose.
- No deployment workflow, deployment scripts, or deployment tests currently exist.

The declared image tags remain floating: `postgres:16-alpine`, `golang:1.25`, `debian:bookworm-slim`, `node:22-alpine`, and `nginx:alpine`. CI-3 validates the currently declared configuration but does not claim byte-for-byte reproducible images. Image digest/version hardening is deferred to a later production-hardening phase.

## Stable CI checks and toolchain policy

The workflow will expose these stable checks:

- `ci/deployment-config`
- `ci/deployment-build`
- `ci/deployment-startup`
- `ci/deployment-smoke`

The workflow targets pull requests to `main` and `workflow_dispatch`, with:

```yaml
permissions:
  contents: read
```

It runs on `ubuntu-24.04`. `actions/checkout` must use immutable reviewed commit `11bd71901bbe5b1630ceea73d27597364c9af683` (`v4.2.2`). No other third-party action is required. The workflow uses the GitHub-hosted runner's preinstalled Docker Engine and Compose plugin; it must print `docker version` and `docker compose version` and fail if either command is unavailable. CI-3 does not install Docker or Compose dynamically. Tool/runtime changes must be reviewed deliberately rather than silently following floating action or installer versions.

## Controlled environment

CI must never consume a developer `.env`. It creates a temporary file such as `$RUNNER_TEMP/opsnexus-ci.env` and passes it explicitly to every Compose command with `--env-file "$RUNNER_TEMP/opsnexus-ci.env"`.

The file contains only disposable test values: a non-production PostgreSQL username, password, database name, host/port, retention value, disabled API authentication, and a localhost CORS origin. No GitHub secrets or production credentials are needed. The file is never printed, uploaded, or included in diagnostics, and is removed during unconditional cleanup.

## Exact validation flow and job ownership

Each lifecycle job uses a unique Compose project name, for example `opsnexus-ci-${{ github.run_id }}-${{ github.job }}`, and the same explicit environment-file policy. Because Docker state is not shared between GitHub jobs, `ci/deployment-startup` owns one complete disposable lifecycle and `ci/deployment-smoke` owns a second complete disposable lifecycle. This avoids relying on containers surviving between jobs.

### `ci/deployment-config`

1. Assemble the four-repository workspace at the SHAs above.
2. Generate the controlled temporary environment file.
3. Print Docker/Compose versions.
4. Run `docker compose --env-file "$RUNNER_TEMP/opsnexus-ci.env" config --quiet` from the deployment directory.
5. Fail on any interpolation or Compose syntax error.

### `ci/deployment-build`

1. Assemble the same four-repository workspace at the same explicit SHAs.
2. Generate the controlled environment file.
3. Run `docker compose --env-file "$RUNNER_TEMP/opsnexus-ci.env" build postgres backend dashboard` from the deployment directory.
4. Fail on any image, dependency, compiler, or asset-build error.

The current PostgreSQL service uses a pulled image rather than a Dockerfile; the build job must still validate the declared image can be resolved while building the application images.

### `ci/deployment-startup`

1. Assemble the exact workspace and controlled environment.
2. Start the stack with `docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" up -d`.
3. Poll PostgreSQL health with `docker inspect --format '{{.State.Health.Status}}' opsnexus-postgres` until `healthy`.
4. Poll backend with `curl --fail --silent --show-error http://127.0.0.1:8080/health`, requiring HTTP 200 and JSON fields `status: ok` and `database: ok`.
5. Prove embedded migrations ran with this exact assertion from the deployment host:

   ```bash
   docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" exec -T postgres \
     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT to_regclass('\''public.telemetry_hourly'\'');"'
   ```

   The expected trimmed result is `telemetry_hourly`. This table is created by the existing `004_phase5.sql` embedded migration. A missing result or SQL error means migration/startup validation failed; backend readiness must not be treated as successful.

6. Restart only the backend with `docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" restart backend`.
7. Poll the same backend health assertion again. The second success proves migrations and startup are repeatable against the existing database volume without destructive reinitialization.
8. Use an unconditional final cleanup step in this job.

### `ci/deployment-smoke`

1. Assemble the exact workspace and controlled environment.
2. Start a fresh isolated stack and wait for PostgreSQL and backend readiness using the same bounded conditions.
3. Run the backend host-level smoke request:

   ```bash
   curl --fail --silent --show-error http://127.0.0.1:8080/health
   ```

   Require HTTP 200 and JSON containing `status: ok` and `database: ok`.

4. Run the dashboard host-level smoke request:

   ```bash
   curl --fail --silent --show-error http://127.0.0.1:5173/
   ```

   Require HTTP success, a non-empty response, and both exact entrypoint markers from the current dashboard `index.html`: `<title>opsnexus-dashboard</title>` and `<div id="root"></div>`.

5. This validates static dashboard reachability and backend health independently. It does not validate browser-side API integration. The design intentionally does not add browser automation. The compiled `VITE_API_BASE_URL` behavior and lack of nginx `/api` proxy remain documented architecture facts, not claims of end-to-end browser validation.
6. Use an unconditional final cleanup step in this job.

## Timeouts and polling

All readiness loops have hard deadlines:

- PostgreSQL readiness: 120 seconds;
- backend readiness: 120 seconds after PostgreSQL is healthy;
- dashboard HTTP readiness: 60 seconds;
- polling interval: 5 seconds;
- overall startup/smoke job timeout: 20 minutes.

Each loop records the start time and exits non-zero when its deadline expires. No loop waits indefinitely. A failed `curl`, failed health-state inspection, SQL assertion failure, or timeout preserves the original non-zero job result.

## Failure diagnostics

On any startup, health, migration, restart, or smoke failure, diagnostic commands run before cleanup without changing the original result:

```bash
docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" ps --all
docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" images
docker inspect opsnexus-postgres opsnexus-backend opsnexus-dashboard
docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" logs --no-color postgres backend dashboard
```

The workflow may also emit a sanitized `docker compose config` view with secret values removed. It must never print database URLs, passwords, generated environment-file contents, GitHub secrets, or other credentials. Diagnostics must not use `|| true`, `continue-on-error`, or unconditional success. Configuration/build failures before containers exist emit the failed command and available build output; container diagnostics are conditional on resource existence and do not hide the original failure.

## Cleanup structure

Cleanup is an unconditional final step in each lifecycle job (`ci/deployment-startup` and `ci/deployment-smoke`) using `if: ${{ always() }}`. It runs after successful validation, failed build/startup, failed health, failed migration, failed restart, and failed smoke checks.

The cleanup command is:

```bash
docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" down --volumes --remove-orphans
rm -f "$ENV_FILE"
```

The isolated project name prevents collisions. `down --volumes` removes containers, the Compose network, and the disposable PostgreSQL volume. If failure occurs before Compose creates resources, the command is allowed to find no resources and the environment file is still removed; that cleanup path must not replace the earlier failure result.

## Exact CI sequence

The implemented workflow will therefore perform:

1. checkout/assemble deployment and three sibling repositories at the four explicit SHAs;
2. generate the controlled test environment;
3. validate Compose configuration in `ci/deployment-config`;
4. validate image resolution/builds in `ci/deployment-build`;
5. start the stack in `ci/deployment-startup`;
6. wait for PostgreSQL readiness;
7. wait for backend `/health` readiness;
8. assert `public.telemetry_hourly` exists;
9. restart backend and reassert health;
10. start a fresh lifecycle in `ci/deployment-smoke`;
11. verify backend `/health` and dashboard `/` reachability;
12. collect sanitized diagnostics on lifecycle failure;
13. always remove containers, network, volume, and temporary environment files.

## Definition of Done

CI-3 is complete only when all of the following are satisfied:

- sibling repository revisions are immutable and documented;
- the temporary parent workspace is assembled deterministically;
- Compose/config validation passes;
- declared images and application builds pass;
- PostgreSQL readiness passes;
- backend health passes;
- the explicit migration schema assertion passes;
- backend restart validation passes;
- dashboard HTTP reachability passes;
- backend/dashboard smoke checks pass within scope;
- diagnostics are available without exposing secrets;
- test-only secret hygiene is validated;
- cleanup is guaranteed after every lifecycle outcome;
- CI actions are pinned;
- the floating-image limitation is documented;
- CI documentation is updated;
- remote GitHub Actions validation is green;
- the PR is reviewed and merged.

## Deferred hardening

The current floating Docker image tags reduce reproducibility. CI-3 will validate the declared tags but does not pin them or claim byte-for-byte reproducibility. Digest pinning and image/version hardening require a later production-hardening change.

The agent remains outside Compose. Browser automation, production deployment, cloud infrastructure, Kubernetes, application changes, Dockerfile redesign, Compose topology redesign, and broad security tooling remain out of scope.
