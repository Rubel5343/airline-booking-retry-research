# Experiment Protocol v1.1

> Status: **DRAFT AMENDMENT** to v1.0. No paper-grade data may be collected under v1.1 until the implementation-validation gates pass and the `protocol-v1.1` freeze reference is created.

## Why v1.1 exists

Protocol v1.0 froze the causal factors and statistical design, but a pre-run implementation review identified several execution parameters that could materially affect reproducibility: processing jitter, retrieve endpoint latency, fixed-workload concurrency, response-loss hold time, cooldown behavior, and the exact near-timeout condition.

v1.1 makes those parameters explicit before final data collection. No v1.0 pilot/validation data is promoted to paper evidence.

## Primary research question

How do immediate blind retry, delayed blind retry, and retrieve-before-retry reconciliation affect duplicate airline bookings after ambiguous OrderCreate outcomes, and what latency/API-overhead trade-offs arise under supplier delay, retrieval visibility delay, load, and retrieve-endpoint failure?

## Primary outcome

**Duplicate Booking Rate**

A logical booking is duplicate-positive when ground truth contains more than one supplier order for the same `logical_booking_id`.

## Secondary outcomes

- premature retry rate
- UNKNOWN/unresolved rate
- recovery success rate
- resolution latency: median, IQR, P95, P99
- supplier API calls per logical booking
- create calls per logical booking
- retrieve calls per logical booking
- achieved versus requested arrival rate in the load stage

## Strategies

| Label | Recovery policy |
|---|---|
| S1 | Immediate blind retry after ambiguous create outcome |
| S2 | Delayed blind retry after fixed backoff |
| S3-A | One retrieve before controlled retry |
| S3-B3 | Up to three retrieves before controlled retry |
| S3-B5 | Up to five retrieves before controlled retry; used in visibility/failure studies |

## Pairing and reproducibility

For correctness experiments, every strategy in one repetition receives:

- the same deterministic random seed;
- the same `faultCohort`;
- the same logical booking sequence numbers;
- the same simulator configuration.

Supplier/database state remains isolated by `experimentRunId`. Only the deterministic fault schedule is paired.

Correctness workloads use fixed-count k6 `shared-iterations`, not duration-based request counts.

Strategy execution order is deterministically randomized independently for every seed/repetition.

## Sample-size planning

A conservative two-independent-proportion approximation at alpha 0.05 and 80% power requires approximately:

| Duplicate-rate contrast | Approx. N / strategy |
|---|---:|
| 10% vs 5% | 424 |
| 15% vs 8% | 319 |
| 20% vs 10% | 195 |
| 15% vs 5% | 133 |

Each correctness cell therefore uses **500 logical bookings per strategy per repetition**.

Correctness stages use **10 independent deterministic seeds per condition**, yielding 5,000 logical booking observations per strategy/condition while preserving run-level replication.

The simple power calculation is a planning lower bound, not the final inferential model.

## Global execution controls

Base client timeout:

`T = 300 ms`

The values are intentionally time-compressed. Interpretation is based on timing ratios, not a claim that millisecond values directly represent production airline durations.

Unless a stage overrides them:

| Parameter | Frozen value |
|---|---:|
| Processing jitter | 0 ms |
| Retrieve endpoint processing delay | 50 ms (~0.17T) |
| Explicit supplier failure probability | 0% |
| Transient create failure probability | 0% |
| Hidden success on configured response loss | 100% |
| Response-loss hold time | 1500 ms (5T) |
| Fixed-count correctness VUs | 20 |
| Logical bookings / strategy / repetition | 500 |
| k6 fixed-workload max duration | 10 min |
| Post-workload metric cooldown | 600 ms (2T) |

The cooldown is only for metric/ground-truth settling. Response-loss ground truth is persisted before the artificial response hold, so the experiment does not need to wait for the full response-loss hold before querying ground truth.

## Stage A — Core ambiguous completion

Purpose: answer RQ1/RQ2 and establish the reliability-overhead trade-off without crossing redundant ambiguity mechanisms.

Strategies:

- S1
- S2
- S3-A
- S3-B3

Conditions:

| Condition | Processing / timeout | Frozen processing | Response loss | Interpretation |
|---|---:|---:|---:|---|
| A1 | 0.67T | 200 ms | 5% | low-rate lost-response ambiguity |
| A2 | 0.67T | 200 ms | 20% | higher-rate lost-response ambiguity |
| A3 | 1.10T | 330 ms | 0% | near-timeout slow-completion ambiguity |
| A4 | 1.67T | 500 ms | 0% | clear slow-completion ambiguity |

A3 uses 1.10T rather than exactly 1.00T so operating-system/network scheduling noise does not decide whether the request crosses the client deadline.

Fixed Stage-A recovery timing:

- S2 backoff: 250 ms (~0.83T)
- S3 client backoff between completed retrieve attempts: 250 ms (~0.83T)
- retrieve endpoint processing delay: 50 ms
- retrieval visibility delay: 0
- retrieve failure probability: 0

Response-loss probability is intentionally not crossed with processing ratios above the client timeout. When processing itself exceeds the deadline, ambiguity already exists without intentional response loss.

Design size:

4 conditions × 4 strategies × 10 repetitions × 500 bookings.

## Stage B — Retrieval visibility delay

Purpose: answer RQ4 and characterize early NOT_FOUND risk.

Strategies:

- S3-A
- S3-B3
- S3-B5

Fixed:

- processing delay: 200 ms (0.67T)
- response-loss probability: 20%
- hidden success: 100%
- retrieve failure probability: 0
- retrieve endpoint processing delay: 50 ms
- client backoff between completed retrieve attempts: 150 ms (0.5T)

Visibility delay:

- 0 ms (0T)
- 300 ms (1T)
- 600 ms (2T)
- 1200 ms (4T)

Primary outcomes:

- duplicate rate
- premature retry rate
- UNKNOWN rate
- resolution latency
- supplier-call overhead

Design size:

4 visibility conditions × 3 strategies × 10 repetitions × 500 bookings.

## Stage C — Load/concurrency

Purpose: answer the load component of RQ5.

This is the only stage using open-model `constant-arrival-rate` workloads.

Strategies:

- S1
- S2
- S3-B3

Fixed scenario:

- processing delay: 500 ms (1.67T)
- processing jitter: 0
- response-loss probability: 0%
- visibility delay: 0
- retrieve failure probability: 0
- S2 backoff: 250 ms
- S3 client retrieve backoff: 250 ms
- retrieve endpoint delay: 50 ms

Arrival rates:

- 5 RPS
- 20 RPS
- 50 RPS

For every strategy/load/seed:

- discarded warm-up run: 15 seconds
- measurement run: 60 seconds
- independent seeds per load condition: 5
- preallocated VUs: 100
- maximum VUs: 500
- graceful stop: 30 seconds

Warm-up uses a separate experiment run and its records are excluded from all analysis.

Primary outputs:

- duplicate rate
- UNKNOWN rate
- P50/P95/P99 resolution latency
- supplier calls per logical booking
- achieved/requested arrival-rate ratio
- dropped iterations, if any

A load run with dropped iterations is retained as a capacity observation but cannot be interpreted as having delivered the requested workload without qualification.

## Stage D — Retrieve endpoint failure

Purpose: verify that uncertain retrieve results never become evidence that a booking is absent.

Strategies:

- S3-B3
- S3-B5

Fixed:

- processing delay: 200 ms (0.67T)
- response-loss probability: 20%
- hidden success: 100%
- visibility delay: 300 ms (1T)
- retrieve endpoint processing delay: 50 ms
- client backoff between completed retrieve attempts: 150 ms (0.5T)

Retrieve transient-failure probability:

- 0%
- 5%
- 10%
- 20%

Primary outputs:

- UNKNOWN rate
- duplicate rate
- controlled-retry count after any inconclusive retrieve
- supplier API overhead

Safety invariant:

> A retrieve timeout, HTTP 503, or transport failure cannot authorize a new OrderCreate. If any retrieve attempt is inconclusive and no later retrieve finds the booking, the attempt remains UNKNOWN rather than issuing a new create.

Design size:

4 retrieve-failure conditions × 2 strategies × 10 repetitions × 500 bookings.

## Statistical analysis

### Duplicate outcome

Report:

- rate by strategy/condition
- absolute risk difference
- relative risk where defined
- 95% confidence intervals

Primary multivariable model:

`duplicate ~ strategy + condition factors + strategy×factor interactions`

Use run/seed-aware robust inference or an equivalent hierarchical sensitivity analysis so logical requests within one run are not treated as fully independent environmental replicates.

Because correctness strategies use paired deterministic fault cohorts, pairwise comparisons additionally report matched/discordant outcomes when alignment is exact.

### Latency

Report:

- median
- IQR
- P95
- P99

Means may be reported descriptively but are not the basis for tail-latency conclusions.

### API overhead

Report calls per logical booking with 95% confidence intervals and absolute differences.

### Multiple comparisons

Use Holm adjustment within each family of pairwise strategy tests.

## Exclusions from the primary study

- Kubernetes autoscaling
- service mesh
- production airline credentials/APIs
- real passenger data
- payment/ticketing workflow
- native supplier idempotency-key support

Native supplier idempotency is reserved for follow-up work because adding it to the primary experiment changes the research question from reconciliation-policy evaluation to server-side duplicate suppression.

## Data integrity

Every paper-grade run records:

- git commit SHA
- protocol version
- condition ID
- seed
- strategy
- strategy execution order
- fault cohort
- complete simulator configuration
- complete workload configuration
- experiment run IDs
- raw ground-truth export or reproducible SQL snapshot

The BookingStrategyService exposes client-visible attempt/latency/call metrics only. Duplicate-booking ground truth is computed externally from the simulator schema after a run; the recovery strategy code and booking-service summary path have no simulator-schema access.

No final result may be collected from a commit that changes experimental semantics relative to the frozen protocol reference.

## v1.1 freeze validation requirements

Before creating `protocol-v1.1`:

1. .NET restore/build passes;
2. Docker/database/service smoke tests pass;
3. fixed-count correctness produces exactly the requested N for each paired strategy;
4. first-create deterministic fault outcomes match across strategies sharing a fault cohort;
5. no strategy can read simulator ground-truth tables or APIs;
6. external duplicate metrics reconcile across two independent canonical SQL formulations, and BookingStrategyService contains no simulator-schema/ground-truth access;
7. the retrieve-failure safety invariant passes an automated test;
8. Stage-A reduced validation executes all A1–A4 conditions with a small non-paper N;
9. Stage-B reduced validation executes all visibility levels;
10. Stage-D reduced validation executes all retrieve-failure levels;
11. final-data workflows are manual-dispatch only.

Any semantic change after v1.1 freeze requires v1.2 (or later) and re-collection of affected final evidence.
