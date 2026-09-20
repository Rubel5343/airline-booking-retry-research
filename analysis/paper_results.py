#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import math
import pathlib
import statistics
from collections import Counter, defaultdict


def read_jsonl(path: pathlib.Path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def percentile(values, p):
    if not values:
        return math.nan
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * p
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(xs[lo])
    w = pos - lo
    return xs[lo] * (1 - w) + xs[hi] * w


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, center - half), min(1.0, center + half))


def two_sided_binomial_equal_p(k, n):
    if n == 0:
        return 1.0
    m = min(k, n - k)
    tail = sum(math.comb(n, i) for i in range(m + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def load_evidence_dir(evidence_dir: pathlib.Path):
    manifest_path = evidence_dir / "evidence-manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing evidence manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for item in manifest["files"]:
        path = evidence_dir / item["name"]
        if not path.exists():
            raise SystemExit(f"Missing evidence file: {path}")
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        if h != item["sha256"]:
            raise SystemExit(f"SHA mismatch: {path}")
        rows = read_jsonl(path)
        if len(rows) != int(item["rows"]):
            raise SystemExit(f"Row-count mismatch: {path}")

    attempts = read_jsonl(evidence_dir / "booking_attempts.jsonl")
    events = read_jsonl(evidence_dir / "booking_events.jsonl")
    orders = read_jsonl(evidence_dir / "supplier_orders.jsonl")

    orders_by_logical = defaultdict(list)
    for row in orders:
        orders_by_logical[row["logical_booking_id"]].append(row)

    events_by_logical = defaultdict(list)
    for row in events:
        events_by_logical[row["logical_booking_id"]].append(row)

    logical = {}
    for attempt in attempts:
        logical_id = attempt["logical_booking_id"]
        ev = events_by_logical[logical_id]
        ords = orders_by_logical[logical_id]
        supplier_count = len({o["supplier_order_id"] for o in ords})
        first_created = any(int(o["create_attempt_no"]) == 1 for o in ords)
        initial_ambiguous = any(
            e["event_type"] == "ORDER_CREATE_AMBIGUOUS"
            and int((e.get("metadata") or {}).get("createCall", 0)) == 1
            for e in ev
        )
        had_retrieve_unknown = any(e["event_type"] == "RETRIEVE_UNKNOWN" for e in ev)
        second_create = int(attempt.get("create_call_count") or 0) >= 2
        recovered = (
            initial_ambiguous
            and attempt["state"] == "SUCCESS"
            and supplier_count == 1
        )
        logical[logical_id] = {
            "logical_booking_id": logical_id,
            "state": attempt["state"],
            "resolution_ms": float(attempt["resolution_ms"]) if attempt.get("resolution_ms") is not None else math.nan,
            "create_calls": int(attempt.get("create_call_count") or 0),
            "retrieve_calls": int(attempt.get("retrieve_call_count") or 0),
            "supplier_calls": int(attempt.get("create_call_count") or 0) + int(attempt.get("retrieve_call_count") or 0),
            "duplicate": supplier_count > 1,
            "second_create": second_create,
            "premature_unsafe_retry": second_create and first_created,
            "initial_ambiguous": initial_ambiguous,
            "recovered_without_duplicate": recovered,
            "retrieve_unknown": had_retrieve_unknown,
        }

    return manifest, logical


def discover(root: pathlib.Path):
    for manifest in sorted(root.rglob("evidence-manifest.json")):
        yield manifest.parent


def summarize_run(manifest, logical):
    rows = list(logical.values())
    n = len(rows)
    duplicates = sum(r["duplicate"] for r in rows)
    unknown = sum(r["state"] == "UNKNOWN" for r in rows)
    retries = sum(r["second_create"] for r in rows)
    premature = sum(r["premature_unsafe_retry"] for r in rows)
    ambiguous = sum(r["initial_ambiguous"] for r in rows)
    recovered = sum(r["recovered_without_duplicate"] for r in rows)
    latencies = [r["resolution_ms"] for r in rows if not math.isnan(r["resolution_ms"])]
    calls = [r["supplier_calls"] for r in rows]

    dlo, dhi = wilson(duplicates, n)
    ulo, uhi = wilson(unknown, n)
    return {
        "condition": manifest["conditionId"],
        "strategy": manifest["strategyLabel"],
        "repetition": int(manifest["repetition"]),
        "run_id": manifest["runId"],
        "n": n,
        "duplicates": duplicates,
        "duplicate_rate": duplicates / n if n else math.nan,
        "duplicate_ci_low": dlo,
        "duplicate_ci_high": dhi,
        "unknown": unknown,
        "unknown_rate": unknown / n if n else math.nan,
        "unknown_ci_low": ulo,
        "unknown_ci_high": uhi,
        "retries": retries,
        "premature_unsafe_retries": premature,
        "premature_unsafe_retry_rate": premature / retries if retries else 0.0,
        "initial_ambiguous": ambiguous,
        "recovered_without_duplicate": recovered,
        "recovery_success_rate": recovered / ambiguous if ambiguous else 0.0,
        "latency_median_ms": statistics.median(latencies) if latencies else math.nan,
        "latency_iqr_ms": percentile(latencies, 0.75) - percentile(latencies, 0.25) if latencies else math.nan,
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_p99_ms": percentile(latencies, 0.99),
        "avg_supplier_calls": statistics.fmean(calls) if calls else math.nan,
        "avg_create_calls": statistics.fmean(r["create_calls"] for r in rows) if rows else math.nan,
        "avg_retrieve_calls": statistics.fmean(r["retrieve_calls"] for r in rows) if rows else math.nan,
    }


def aggregate_runs(run_rows):
    grouped = defaultdict(list)
    for row in run_rows:
        grouped[(row["condition"], row["strategy"])].append(row)

    out = []
    for (condition, strategy), rows in sorted(grouped.items()):
        total_n = sum(r["n"] for r in rows)
        total_dup = sum(r["duplicates"] for r in rows)
        total_unknown = sum(r["unknown"] for r in rows)
        dlo, dhi = wilson(total_dup, total_n)
        ulo, uhi = wilson(total_unknown, total_n)
        out.append({
            "condition": condition,
            "strategy": strategy,
            "repetitions": len(rows),
            "n": total_n,
            "duplicates": total_dup,
            "duplicate_rate": total_dup / total_n if total_n else math.nan,
            "duplicate_ci_low": dlo,
            "duplicate_ci_high": dhi,
            "unknown_rate": total_unknown / total_n if total_n else math.nan,
            "unknown_ci_low": ulo,
            "unknown_ci_high": uhi,
            "mean_run_duplicate_rate": statistics.fmean(r["duplicate_rate"] for r in rows),
            "sd_run_duplicate_rate": statistics.stdev(r["duplicate_rate"] for r in rows) if len(rows) > 1 else 0.0,
            "mean_latency_median_ms": statistics.fmean(r["latency_median_ms"] for r in rows),
            "mean_latency_p95_ms": statistics.fmean(r["latency_p95_ms"] for r in rows),
            "mean_supplier_calls": statistics.fmean(r["avg_supplier_calls"] for r in rows),
            "mean_premature_unsafe_retry_rate": statistics.fmean(r["premature_unsafe_retry_rate"] for r in rows),
            "mean_recovery_success_rate": statistics.fmean(r["recovery_success_rate"] for r in rows),
        })
    return out


def paired_duplicate_comparisons(run_logical):
    by_cell = defaultdict(dict)
    for key, logical in run_logical.items():
        condition, strategy, repetition = key
        by_cell[(condition, repetition)][strategy] = logical

    rows = []
    for (condition, repetition), strategies in sorted(by_cell.items()):
        labels = sorted(strategies)
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                a, b = labels[i], labels[j]
                ids = sorted(set(strategies[a]) & set(strategies[b]))
                a_only = b_only = both = neither = 0
                for logical_id in ids:
                    ad = bool(strategies[a][logical_id]["duplicate"])
                    bd = bool(strategies[b][logical_id]["duplicate"])
                    if ad and bd:
                        both += 1
                    elif ad and not bd:
                        a_only += 1
                    elif not ad and bd:
                        b_only += 1
                    else:
                        neither += 1
                discordant = a_only + b_only
                p = two_sided_binomial_equal_p(a_only, discordant)
                rows.append({
                    "condition": condition,
                    "repetition": repetition,
                    "strategy_a": a,
                    "strategy_b": b,
                    "paired_n": len(ids),
                    "a_duplicate_b_not": a_only,
                    "b_duplicate_a_not": b_only,
                    "both_duplicate": both,
                    "neither_duplicate": neither,
                    "discordant": discordant,
                    "mcnemar_exact_p": p,
                })
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=pathlib.Path, help="Directory containing extracted paper-grade artifacts")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("analysis-output"))
    args = ap.parse_args()

    run_rows = []
    run_logical = {}
    manifests = 0
    for evidence_dir in discover(args.root):
        manifest, logical = load_evidence_dir(evidence_dir)
        manifests += 1
        row = summarize_run(manifest, logical)
        run_rows.append(row)
        run_logical[(row["condition"], row["strategy"], row["repetition"])] = logical

    if manifests == 0:
        raise SystemExit(f"No evidence-manifest.json files found under {args.root}")

    agg = aggregate_runs(run_rows)
    paired = paired_duplicate_comparisons(run_logical)

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "run_summary.csv", run_rows)
    write_csv(args.out / "condition_strategy_summary.csv", agg)
    write_csv(args.out / "paired_duplicate_comparisons.csv", paired)

    summary = {
        "evidenceManifests": manifests,
        "runs": len(run_rows),
        "conditionStrategyCells": len(agg),
        "pairedComparisons": len(paired),
    }
    (args.out / "analysis_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
