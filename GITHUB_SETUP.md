# GitHub setup

Recommended repository:

- Name: `airline-booking-retry-research`
- Visibility: Private during pilot development
- Initialize with README: **No** (the scaffold already contains one)
- Description: `Experimental evaluation of blind retry vs retrieve-before-retry reconciliation for ambiguous airline booking timeouts.`

After creating the repository, grant the connected ChatGPT GitHub app access to it. The scaffold can then be pushed without changing the existing `fcboot` repository.

Recommended initial branches after the first push:

- `main` — stable research scaffold
- `experiment/pilot` — pilot fixes and instrumentation

The repository already contains a GitHub Actions workflow at `.github/workflows/ci.yml` that will:

1. install .NET 10,
2. restore/build the solution,
3. validate shell/JSON/project files,
4. build Docker images,
5. start PostgreSQL and both services,
6. run normal smoke tests,
7. run deterministic ambiguous-timeout integration smoke tests.
