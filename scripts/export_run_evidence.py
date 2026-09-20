#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import subprocess


def psql_lines(query: str):
    cmd = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "research", "-d", "airline_research",
        "-At", "-c", query,
    ]
    out = subprocess.check_output(cmd, text=True)
    return [line for line in out.splitlines() if line.strip()]


def write_jsonl(path: pathlib.Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            # Validate every line as JSON before persisting evidence.
            parsed = json.loads(row)
            f.write(json.dumps(parsed, separators=(",", ":"), ensure_ascii=False))
            f.write("\n")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_rows(run_id: str, inner_sql: str):
    query = f"""
SELECT row_to_json(x)::text
FROM (
{inner_sql}
) x;
"""
    return psql_lines(query)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--git-commit", required=True)
    ap.add_argument("--condition-id", required=True)
    ap.add_argument("--strategy-label", required=True)
    ap.add_argument("--repetition", required=True, type=int)
    args = ap.parse_args()

    run_id = args.run_id
    out_dir = pathlib.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets = {
        "experiment_run": f"""
SELECT
  run_id,
  name,
  random_seed,
  config,
  git_commit,
  started_at,
  completed_at
FROM research.experiment_runs
WHERE run_id = '{run_id}'::uuid
""",
        "booking_attempts": f"""
SELECT
  attempt_id,
  experiment_run_id,
  logical_booking_id,
  client_reference,
  strategy,
  state,
  supplier_order_id,
  create_call_count,
  retrieve_call_count,
  started_at,
  resolved_at,
  resolution_ms,
  error_code
FROM research.booking_attempts
WHERE experiment_run_id = '{run_id}'::uuid
ORDER BY logical_booking_id
""",
        "booking_events": f"""
SELECT
  event_id,
  experiment_run_id,
  attempt_id,
  logical_booking_id,
  client_reference,
  event_type,
  supplier_order_id,
  metadata,
  occurred_at
FROM research.booking_events
WHERE experiment_run_id = '{run_id}'::uuid
ORDER BY event_id
""",
        "supplier_orders": f"""
SELECT
  supplier_order_id,
  experiment_run_id,
  logical_booking_id,
  client_reference,
  create_attempt_no,
  origin,
  destination,
  created_at,
  visible_at,
  response_lost
FROM simulator.supplier_orders
WHERE experiment_run_id = '{run_id}'::uuid
ORDER BY logical_booking_id, create_attempt_no, supplier_order_id
""",
        "supplier_calls": f"""
SELECT
  supplier_call_id,
  experiment_run_id,
  logical_booking_id,
  client_reference,
  operation,
  operation_attempt_no,
  outcome,
  supplier_order_id,
  configured_delay_ms,
  occurred_at
FROM simulator.supplier_calls
WHERE experiment_run_id = '{run_id}'::uuid
ORDER BY supplier_call_id
""",
    }

    files = []
    row_counts = {}
    for name, sql in datasets.items():
        rows = json_rows(run_id, sql)
        path = out_dir / f"{name}.jsonl"
        write_jsonl(path, rows)
        count = len(rows)
        row_counts[name] = count
        files.append({
            "name": path.name,
            "rows": count,
            "sha256": sha256(path),
        })

    if row_counts["experiment_run"] != 1:
        raise SystemExit(
            f"Expected exactly one experiment_run row for {run_id}, "
            f"got {row_counts['experiment_run']}"
        )

    manifest = {
        "evidenceSchemaVersion": 1,
        "protocol": args.protocol,
        "gitCommit": args.git_commit,
        "conditionId": args.condition_id,
        "strategyLabel": args.strategy_label,
        "repetition": args.repetition,
        "runId": run_id,
        "rowCounts": row_counts,
        "files": files,
    }

    manifest_path = out_dir / "evidence-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Manifest digest excludes itself by design; the GitHub artifact digest then
    # covers the entire uploaded archive.
    print(json.dumps(manifest, separators=(",", ":")))


if __name__ == "__main__":
    main()
