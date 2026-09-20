# Pilot Validation Findings

> **Status:** Validation data only. Do not cite these values as final paper results.

Pilot workflow run: `35504754995`  
Branch commit: `a282be6bd008698d42ba204d7beaad65bb6e6115`  
Scenario: `configs/scenario-baseline.json`  
Arrival rate: 5 logical bookings/second  
Duration: 30 seconds per strategy  
Client booking timeout: 300 ms  
Supplier processing delay: 500 ms + up to 250 ms deterministic jitter

## Results

| Variant | Strategy | Logical bookings | Duplicate bookings | Duplicate rate | UNKNOWN | Avg resolution | P95 resolution | Avg supplier calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| S1 | ImmediateBlindRetry | 151 | 140 | 92.72% | 151 | 605.0 ms | 606.0 ms | 2.00 |
| S2 | DelayedBlindRetry | 150 | 140 | 93.33% | 150 | 854.1 ms | 856.6 ms | 2.00 |
| S3-A | RetrieveBeforeRetry ×1 | 151 | 138 | 91.39% | 151 | 659.5 ms | 663.5 ms | 3.00 |
| S3-B | RetrieveBeforeRetry ×3 | 150 | 0 | 0.00% | 7 | 800.9 ms | 971.7 ms | 3.46 |

## Sanity interpretation

The baseline scenario deliberately makes the client timeout (300 ms) shorter than the supplier processing time (500–750 ms). This creates ambiguous outcomes by design.

- S1 and S2 usually issue a second OrderCreate before the first supplier operation has completed, producing a very high duplicate rate.
- S3-A retrieves only once, too early in this scenario. The first order is commonly not yet visible/existing when the single retrieve occurs, so a controlled retry still creates duplicates.
- S3-B provides a longer bounded reconciliation window. Three retrieve attempts at 250 ms intervals are sufficient in this pilot to observe the first booking before issuing another OrderCreate, resulting in zero measured duplicates.
- The reliability improvement has a visible cost: S3-B used more supplier calls and higher resolution latency than S1.

The pilot also exposed an important semantic point: S1/S2/S3-A finish as UNKNOWN for nearly all requests because both create calls can exceed the 300 ms client timeout even though supplier-side orders are created. This is expected for this intentionally harsh scenario and confirms that local timeout state cannot be used as supplier ground truth.

## What this pilot proves

The pilot validates that:

1. deterministic failure injection is functioning;
2. ground-truth duplicate classification is functioning;
3. blind retry can reproduce duplicate airline orders under ambiguous timeouts;
4. a single retrieve can be insufficient when reconciliation occurs before supplier completion/visibility;
5. a bounded multi-retrieve window can prevent duplicates in the tested condition;
6. latency and supplier-call overhead are being captured.

## What this pilot does **not** prove

It does not establish that S3-B is generally superior.

Before paper-grade data collection we still need:

- repeated independent runs;
- multiple supplier latency levels;
- multiple timeout probabilities;
- multiple visibility delays;
- retrieve endpoint failures;
- different concurrency/load levels;
- confidence intervals and effect sizes;
- power analysis;
- randomized strategy order;
- frozen experiment protocol and parameter matrix.

No inferential conclusion should be drawn from this single pilot run.
