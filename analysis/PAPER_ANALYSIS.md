# Paper Analysis Pipeline

This analysis layer is intentionally separate from the frozen collection protocol. It does not modify booking strategy behavior, supplier simulation, seeds, workloads, timing, or evidence capture.

## Inputs

Extract the GitHub paper-grade artifacts into one directory. The analysis script recursively discovers every `evidence-manifest.json` and validates:

- evidence file presence;
- SHA-256 digests;
- declared row counts;
- JSON parsing.

## Run

```bash
python3 analysis/paper_results.py /path/to/extracted-artifacts --out analysis-output
```

## Outputs

- `run_summary.csv`
  - one row per measured strategy run;
  - duplicate/UNKNOWN rates;
  - premature or unsafe retry rate;
  - recovery success;
  - median/IQR/P95/P99 resolution latency;
  - supplier API-call overhead.

- `condition_strategy_summary.csv`
  - pooled descriptive statistics by condition and strategy;
  - Wilson 95% intervals for duplicate and UNKNOWN proportions;
  - run-level mean/SD duplicate rate;
  - latency and API-call summaries.

- `paired_duplicate_comparisons.csv`
  - strategy pairs within the same condition/repetition;
  - matched logical bookings;
  - discordant duplicate outcomes;
  - exact two-sided McNemar/binomial p-value.

- `analysis_manifest.json`
  - count of evidence manifests, runs, condition/strategy cells, and paired comparisons processed.

## Statistical interpretation

The script deliberately separates descriptive and matched binary analysis from the final multivariable model.

The manuscript should use:

1. absolute rates and 95% confidence intervals;
2. absolute risk differences and relative risks where meaningful;
3. paired discordance/McNemar results for exact matched comparisons;
4. run/seed-aware clustered or hierarchical regression for the final multivariable duplicate model;
5. median, IQR, P95, and P99 for latency;
6. supplier calls per logical booking for overhead;
7. Holm adjustment within families of pairwise tests.

A later analysis script may implement the clustered/hierarchical model after all final conditions have been collected and inspected for convergence. This avoids silently choosing a model that is incompatible with the realized final dataset.
