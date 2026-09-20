# Project Status

## Phase 1 — Scaffold

Completed:

- .NET 10 Booking Strategy Service
- deterministic Supplier Simulator
- PostgreSQL research + simulator schemas
- S1 immediate blind retry
- S2 delayed blind retry
- S3 retrieve-before-retry
- k6 starter workload
- Docker Compose environment
- duplicate/premature-retry SQL

## Phase 2 — Pilot hardening

Completed:

- experiment-run-scoped supplier state
- atomic CREATE/RETRIEVE operation counters
- definite rejection separated from transient ambiguous failure
- simulator configuration validation
- retrieve failure cannot authorize OrderCreate
- run summary endpoint
- fixed Docker resource limits
- pinned k6 Docker image
- pilot runner across S1/S2/S3-A/S3-B
- visibility-delay and retrieve-failure scenarios

## Current gate

Run the first compile/container pilot on a Docker-enabled machine:

```bash
docker compose down -v
docker compose up --build -d
./scripts/smoke-test.sh
./scripts/pilot-run.sh
```

Do not collect paper results until compile/runtime validation and pilot sanity checks pass.

## Phase 3 — after pilot validation

- fix any compile/runtime defects
- verify ground-truth duplicate classification
- verify S3-A vs S3-B behavior under visibility delay
- export run-level CSV/JSON results
- add automated statistical analysis notebook/script
- run pilot effect-size estimates
- perform power analysis
- freeze final experiment matrix
