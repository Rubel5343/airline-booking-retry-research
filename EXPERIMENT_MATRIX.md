# Experiment Matrix — Draft v1

> This matrix is **not frozen**. It is the Phase 3 design used to estimate variance and reduce the final design to a defensible staged experiment.

## Design principles

1. Strategies within the same repetition share a **fault cohort** so deterministic supplier outcomes are paired across S1/S2/S3-A/S3-B.
2. k6 uses `scenario.iterationInTest` to generate deterministic logical booking IDs rather than wall-clock timestamps.
3. Strategy execution order is deterministically randomized per repetition.
4. Supplier/database state remains isolated by `experimentRunId`; only the random fault schedule is shared through `faultCohort`.
5. Pilot/variance data is not paper evidence.
6. Final paper data starts only after a protocol-freeze commit/tag.

## Strategy variants

| Label | Strategy | Retrieve attempts |
|---|---|---:|
| S1 | Immediate blind retry | 0 |
| S2 | Delayed blind retry | 0 |
| S3-A | Retrieve-before-retry | 1 |
| S3-B | Bounded retrieve-before-retry | 3 |

## Phase 3 variance pilots

Run each scenario for several independent repetitions with different deterministic seeds.

| Scenario | Purpose |
|---|---|
| baseline | Estimate variance under ambiguous supplier completion |
| visibility-delay | Stress early NOT_FOUND and delayed order visibility |
| retrieve-failure | Validate that uncertain retrieve failures do not authorize duplicate creation |

Initial variance-pilot settings:

- repetitions: 3–5
- arrival rate: 5 RPS
- duration: 15–30 s per strategy
- client booking timeout: 300 ms
- delayed retry: 250 ms
- retrieve interval: 250 ms

These values are intentionally time-compressed for pilot validation. Final paper scenarios will be expressed using timing ratios and include at least one slower realism check.

## Proposed final staged design

### Stage A — Core ambiguous completion

Factors:

- strategy: S1, S2, S3-A, S3-B
- supplier-processing / client-timeout ratio: below, near, and above 1
- hidden-success probability: low, medium, high

Primary outcome: duplicate-booking rate.

### Stage B — Retrieval visibility

Factors:

- retrieve visibility delay: 0, short, medium, long relative to timeout
- retrieve attempts/window: 1, 3, 5

Primary outcomes:

- duplicate-booking rate
- premature-retry rate
- resolution latency
- supplier-call overhead

### Stage C — Load

Factors:

- offered arrival rate: low, medium, high
- selected strategies: S1, S2, S3-B

Primary outcomes:

- duplicate rate
- P50/P95/P99 resolution latency
- UNKNOWN rate
- supplier calls per logical booking

### Stage D — Retrieve endpoint failure

Factors:

- retrieve failure probability: 0%, 5%, 10%, 20%
- selected reconciliation strategies

Primary outcomes:

- UNKNOWN rate
- duplicate-booking rate
- incorrect retry-after-uncertain-retrieve count

## Statistical plan after variance pilot

Use pilot repetitions only to estimate run-level variance and set sample size.

Final analysis should report:

- absolute and relative differences
- 95% confidence intervals
- effect sizes
- run-level distributions
- logistic regression for duplicate outcome when modeling multiple factors
- median/IQR/P95/P99 for latency
- corrected pairwise tests where appropriate

The final number of repetitions will be chosen after power/sample-size analysis rather than fixed from the single validation pilot.
