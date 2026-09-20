# Experiment Protocol v1.1.1 — Evidence Capture Patch

> Status: **DRAFT PATCH**. This patch inherits all experimental semantics, causal factors, strategy definitions, timing parameters, seed schedules, sample sizes, and statistical plans from frozen protocol v1.1. It changes evidence capture only. No paper-grade data has been collected before this patch.

## Parent protocol

- Parent frozen ref: `protocol-v1.1`
- Parent frozen commit: `6c6070eea82f5e1559977e5ce3909cab3ac9501c`
- Parent protocol document: `EXPERIMENT_PROTOCOL_V1_1.md`

## Reason for the patch

The v1.1 final runners persisted run-level summaries, but the frozen data-integrity requirements also call for raw ground-truth evidence sufficient to independently reconstruct final metrics and paired outcomes.

Before the first paper-grade condition was executed, this gap was identified. v1.1.1 therefore adds immutable per-run evidence export without changing supplier behavior, client strategy behavior, workloads, timing, seeds, sample sizes, or statistical hypotheses.

## Added evidence for every measured experiment run

Each measured strategy run exports:

1. `experiment_run.jsonl`
   - experiment metadata
   - seed/configuration
   - source git commit

2. `booking_attempts.jsonl`
   - one client-side logical booking record per attempt
   - terminal state
   - create/retrieve call counts
   - resolution latency

3. `booking_events.jsonl`
   - ordered client-side event timeline
   - create ambiguity
   - retrieve outcomes
   - controlled retries

4. `supplier_orders.jsonl`
   - simulator ground-truth orders
   - logical booking ID
   - create attempt number
   - creation and visibility timestamps
   - response-loss flag

5. `supplier_calls.jsonl`
   - supplier operation timeline
   - operation attempt number
   - outcome
   - configured delay

6. `evidence-manifest.json`
   - protocol version
   - source git commit
   - condition/strategy/repetition/run ID
   - row count for every raw dataset
   - SHA-256 digest for every JSONL evidence file

Warm-up runs in Stage C remain excluded from analysis and are not required to have raw paper evidence exports. Measurement runs are exported.

## Integrity guarantees

For every evidence manifest:

- every declared JSONL file must exist;
- every line must parse as valid JSON;
- line count must equal the declared row count;
- SHA-256 must match the manifest;
- exactly one experiment-run metadata row must exist;
- exported run IDs are scoped to one experiment run only.

The GitHub Actions artifact digest provides an additional archive-level integrity record.

## Analysis implications

The raw evidence enables independent reconstruction of:

- duplicate booking rate;
- matched/discordant outcomes across paired fault cohorts;
- premature/unsafe retry;
- recovery success after ambiguous first create;
- UNKNOWN rate;
- create/retrieve/API-call overhead;
- resolution latency;
- Stage-C achieved workload and dropped-iteration context.

Run-level summary JSON remains a convenience layer and is not the only source of truth.

## Experimental semantics

**No experimental semantics change in v1.1.1.**

The following remain exactly as frozen in v1.1:

- strategies S1, S2, S3-A, S3-B3, S3-B5;
- A/B/C/D condition definitions;
- timeout and timing ratios;
- visibility/failure probabilities;
- seed schedule;
- deterministic fault pairing;
- correctness sample size and repetitions;
- load rates, warm-up, duration, VU limits;
- outcome definitions and inferential plan.

## Freeze gate

Before creating `protocol-v1.1.1`:

1. .NET restore/build passes;
2. existing ambiguity/pairing/retrieve-safety gates pass;
3. reduced A/B/D matrix passes;
4. reduced C-R5/C-R20/C-R50 load validation passes;
5. exactly 45 measured validation runs produce evidence manifests:
   - 36 A/B/D strategy runs;
   - 9 Stage-C measurement strategy runs;
6. every evidence manifest passes row-count, JSON parsing, and SHA-256 verification;
7. paper-grade workflow remains manual-dispatch only;
8. paper-grade workflow checks out the frozen `protocol-v1.1.1` ref;
9. final artifact upload includes raw JSONL evidence as well as summary JSON.

Pilot and validation observations remain excluded from paper evidence.
