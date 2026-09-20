# Frozen Experiment Protocol Candidate v1.0

> Status: **candidate freeze**. Final freeze occurs only after the fixed-count paired validation workflow passes.

## Primary research question

How do immediate blind retry, delayed blind retry, and retrieve-before-retry reconciliation affect duplicate airline bookings after ambiguous OrderCreate outcomes, and what latency/API-overhead trade-offs arise under supplier delay, retrieval visibility delay, load, and retrieve-endpoint failure?

## Primary outcome

**Duplicate Booking Rate**

A logical booking is duplicate-positive when ground truth contains more than one supplier order for the same `logical_booking_id`.

## Secondary outcomes

- premature retry rate
- UNKNOWN/unresolved rate
- recovery success rate
- resolution latency: median, P95, P99
- supplier API calls per logical booking
- create calls per logical booking
- retrieve calls per logical booking

## Strategies

| Label | Recovery policy |
|---|---|
| S1 | Immediate blind retry after ambiguous create outcome |
| S2 | Delayed blind retry after fixed backoff |
| S3-A | One retrieve before controlled retry |
| S3-B3 | Up to three retrieves before controlled retry |
| S3-B5 | Up to five retrieves before controlled retry; used only in visibility-delay study |

## Pairing and reproducibility

For correctness experiments, every strategy in one repetition receives:

- the same deterministic random seed;
- the same `faultCohort`;
- the same logical booking sequence numbers;
- the same simulator configuration.

Supplier/database state remains isolated by `experimentRunId`. Only the deterministic fault schedule is paired.

Correctness workloads use fixed-count k6 `shared-iterations`, not duration-based request counts.

## Sample-size planning

A conservative two-independent-proportion approximation at alpha 0.05 and 80% power requires approximately:

| Duplicate-rate contrast | Approx. N / strategy |
|---|---:|
| 10% vs 5% | 424 |
| 15% vs 8% | 319 |
| 20% vs 10% | 195 |
| 15% vs 5% | 133 |

Therefore each correctness cell uses **500 logical bookings per strategy per repetition**.

This calculation is intentionally conservative because the experiment pairs deterministic fault cohorts across strategies. The final analysis will not treat this simple power calculation as the inferential model.

## Repetitions

Correctness stages use **10 independent deterministic seeds per condition**.

Each repetition randomizes strategy execution order using its seed.

This yields 5,000 logical booking observations per strategy per condition while preserving run-level replication for sensitivity analysis.

## Timing model

The simulator uses time-compressed parameters to keep experiments tractable. Conclusions are framed in terms of ratios rather than claiming that millisecond values equal real airline processing times.

Base client timeout:

`T = 300 ms`

### Stage A — Core ambiguous completion

Purpose: answer RQ1/RQ2 and establish the reliability-overhead trade-off.

Strategies:

- S1
- S2
- S3-A
- S3-B3

Factors:

**Supplier processing / client-timeout ratio**

- 0.67T
- 1.00T
- 1.67T

**Response-loss probability**

- 5%
- 20%

Fixed:

- hidden success on response loss: 100%
- retrieval visibility delay: 0
- retrieve failure probability: 0
- S2 backoff: 0.83T
- S3 retrieve spacing: 0.83T

Design size:

6 condition cells × 4 strategies × 10 repetitions × 500 bookings.

### Stage B — Retrieval visibility delay

Purpose: answer RQ4 and characterize early NOT_FOUND risk.

Strategies:

- S3-A
- S3-B3
- S3-B5

Fixed:

- processing delay: 0.67T
- response-loss probability: 20%
- hidden success: 100%
- retrieve failure probability: 0

Visibility delay:

- 0T
- 1T
- 2T
- 4T

Retrieve spacing:

- 0.5T

Outcomes emphasize duplicate rate, premature retry, resolution latency, and supplier-call overhead.

### Stage C — Load/concurrency

Purpose: answer the load component of RQ5.

This is the only stage that uses open-model constant-arrival-rate workloads.

Strategies:

- S1
- S2
- S3-B3

Fixed scenario:

- processing delay: 1.67T
- response-loss probability: 10%
- hidden success: 100%
- visibility delay: 0

Arrival rates:

- 5 RPS
- 20 RPS
- 50 RPS

Each load condition runs for 60 seconds with 5 independent seeds after a short warm-up.

Primary outputs:

- duplicate rate
- UNKNOWN rate
- P50/P95/P99 resolution latency
- supplier calls per booking
- achieved vs requested arrival rate

### Stage D — Retrieve endpoint failure

Purpose: verify that an uncertain retrieve result never becomes evidence that a booking is absent.

Strategies:

- S3-B3
- S3-B5

Fixed:

- processing delay: 0.67T
- response-loss probability: 20%
- hidden success: 100%
- visibility delay: 1T

Retrieve transient-failure probability:

- 0%
- 5%
- 10%
- 20%

Primary outputs:

- UNKNOWN rate
- duplicate rate
- number of controlled retries issued after any inconclusive retrieve
- supplier API overhead

Safety invariant:

> A retrieve timeout/503/transport failure cannot authorize a new OrderCreate.

## Statistical analysis

### Duplicate outcome

Report:

- rate by strategy/condition
- absolute risk difference
- relative risk where defined
- 95% confidence intervals

Primary multivariable model:

`duplicate ~ strategy + condition factors + strategy×factor interactions`

Use run/seed-aware robust inference or an equivalent hierarchical sensitivity analysis so logical requests from one run are not treated as fully independent environmental replicates.

Because correctness strategies use paired deterministic fault cohorts, pairwise comparisons will additionally report matched/discordant outcomes where alignment is exact.

### Latency

Report:

- median
- IQR
- P95
- P99

Do not use means alone for tail-latency conclusions.

### API overhead

Report calls per logical booking with 95% confidence intervals and absolute differences.

### Multiple pairwise tests

Use Holm correction within each family of strategy comparisons.

## Exclusions from primary study

The following are intentionally outside the causal comparison:

- Kubernetes autoscaling
- service mesh
- production airline credentials/APIs
- real passenger data
- payment/ticketing workflow
- native supplier idempotency-key support

Native idempotency is a valuable follow-up strategy but would broaden the primary paper beyond the current research question.

## Data integrity

Every final run records:

- git commit SHA
- protocol version
- scenario/condition ID
- seed
- strategy
- strategy execution order
- fault cohort
- simulator configuration
- workload parameters
- experiment run IDs

Final evidence must be generated only from a tagged protocol-freeze commit or its exact descendants that do not alter experimental semantics.

## Freeze gate

Before tagging `protocol-v1.0`:

1. fixed-count correctness validation must pass;
2. exact paired request counts must be confirmed;
3. deterministic fault pairing must be confirmed;
4. no strategy may access simulator ground truth;
5. summary metrics must reconcile with raw SQL ground truth;
6. Stage D safety invariant must have an automated test.

Any semantic change after the tag requires a new protocol version and re-collection of affected final data.
