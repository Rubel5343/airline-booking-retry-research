#!/usr/bin/env python3
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_run(root, strategy, run_id, duplicate_second):
    d = root / f"A1-{strategy}-{run_id}"
    d.mkdir(parents=True)

    attempts = [
        {
            "attempt_id": f"att-{strategy}-1",
            "experiment_run_id": run_id,
            "logical_booking_id": "BKG-shared-1",
            "client_reference": "REF-1",
            "strategy": strategy,
            "state": "SUCCESS",
            "supplier_order_id": "ORD-1",
            "create_call_count": 2 if strategy == "S1" else 1,
            "retrieve_call_count": 0 if strategy == "S1" else 1,
            "started_at": "2026-09-20T00:00:00Z",
            "resolved_at": "2026-09-20T00:00:01Z",
            "resolution_ms": 1000,
            "error_code": None,
        },
        {
            "attempt_id": f"att-{strategy}-2",
            "experiment_run_id": run_id,
            "logical_booking_id": "BKG-shared-2",
            "client_reference": "REF-2",
            "strategy": strategy,
            "state": "SUCCESS",
            "supplier_order_id": "ORD-2",
            "create_call_count": 1,
            "retrieve_call_count": 0,
            "started_at": "2026-09-20T00:00:00Z",
            "resolved_at": "2026-09-20T00:00:00.5Z",
            "resolution_ms": 500,
            "error_code": None,
        },
    ]
    events = [
        {
            "event_id": 1,
            "experiment_run_id": run_id,
            "attempt_id": f"att-{strategy}-1",
            "logical_booking_id": "BKG-shared-1",
            "client_reference": "REF-1",
            "event_type": "ORDER_CREATE_AMBIGUOUS",
            "supplier_order_id": None,
            "metadata": {"createCall": 1},
            "occurred_at": "2026-09-20T00:00:00.3Z",
        }
    ]
    orders = [
        {
            "supplier_order_id": "ORD-1",
            "experiment_run_id": run_id,
            "logical_booking_id": "BKG-shared-1",
            "client_reference": "REF-1",
            "create_attempt_no": 1,
            "origin": "DAC",
            "destination": "LHR",
            "created_at": "2026-09-20T00:00:00.2Z",
            "visible_at": "2026-09-20T00:00:00.2Z",
            "response_lost": True,
        },
        {
            "supplier_order_id": "ORD-2",
            "experiment_run_id": run_id,
            "logical_booking_id": "BKG-shared-2",
            "client_reference": "REF-2",
            "create_attempt_no": 1,
            "origin": "DAC",
            "destination": "LHR",
            "created_at": "2026-09-20T00:00:00.2Z",
            "visible_at": "2026-09-20T00:00:00.2Z",
            "response_lost": False,
        },
    ]
    if duplicate_second:
        orders.append({
            "supplier_order_id": "ORD-DUP",
            "experiment_run_id": run_id,
            "logical_booking_id": "BKG-shared-1",
            "client_reference": "REF-1",
            "create_attempt_no": 2,
            "origin": "DAC",
            "destination": "LHR",
            "created_at": "2026-09-20T00:00:00.8Z",
            "visible_at": "2026-09-20T00:00:00.8Z",
            "response_lost": False,
        })

    datasets = {
        "experiment_run.jsonl": [{"run_id": run_id}],
        "booking_attempts.jsonl": attempts,
        "booking_events.jsonl": events,
        "supplier_orders.jsonl": orders,
        "supplier_calls.jsonl": [],
    }
    files = []
    row_counts = {}
    for name, rows in datasets.items():
        p = d / name
        write_jsonl(p, rows)
        files.append({"name": name, "rows": len(rows), "sha256": sha(p)})
        row_counts[name.replace(".jsonl", "")] = len(rows)

    manifest = {
        "evidenceSchemaVersion": 1,
        "protocol": "v1.1.1",
        "gitCommit": "test",
        "conditionId": "A1",
        "strategyLabel": strategy,
        "repetition": 1,
        "runId": run_id,
        "rowCounts": row_counts,
        "files": files,
    }
    (d / "evidence-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td) / "input"
    out = pathlib.Path(td) / "out"
    root.mkdir()
    build_run(root, "S1", "run-s1", True)
    build_run(root, "S3B3", "run-s3", False)

    subprocess.run(
        [sys.executable, "analysis/paper_results.py", str(root), "--out", str(out)],
        check=True,
    )

    agg = (out / "condition_strategy_summary.csv").read_text(encoding="utf-8")
    paired = (out / "paired_duplicate_comparisons.csv").read_text(encoding="utf-8")
    manifest = json.loads((out / "analysis_manifest.json").read_text(encoding="utf-8"))

    assert manifest["evidenceManifests"] == 2
    assert manifest["runs"] == 2
    assert "S1" in agg and "S3B3" in agg
    assert "a_duplicate_b_not" in paired
    assert ",1,0," in paired or ",0,1," in paired

print("paper-results synthetic self-test: PASS")
