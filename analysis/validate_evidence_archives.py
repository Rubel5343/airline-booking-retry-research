#!/usr/bin/env python3
import hashlib
import json
import pathlib
import sys

ROOTS = [
    pathlib.Path("results/v11-validation/raw"),
    pathlib.Path("results/v11-load-validation/raw"),
]
EXPECTED_MANIFESTS = 45


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


manifests = []
for root in ROOTS:
    if root.exists():
        manifests.extend(sorted(root.glob("*/evidence-manifest.json")))

if len(manifests) != EXPECTED_MANIFESTS:
    raise SystemExit(
        f"Expected {EXPECTED_MANIFESTS} evidence manifests, found {len(manifests)}"
    )

total_attempt_rows = 0
for manifest_path in manifests:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent

    expected_files = {
        "experiment_run.jsonl",
        "booking_attempts.jsonl",
        "booking_events.jsonl",
        "supplier_orders.jsonl",
        "supplier_calls.jsonl",
    }

    declared = {entry["name"]: entry for entry in manifest.get("files", [])}
    if set(declared) != expected_files:
        raise SystemExit(
            f"{manifest_path}: declared files mismatch: {sorted(declared)}"
        )

    for name, entry in declared.items():
        path = base / name
        if not path.exists():
            raise SystemExit(f"{manifest_path}: missing {name}")

        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines:
            json.loads(line)

        if len(lines) != int(entry["rows"]):
            raise SystemExit(
                f"{manifest_path}: {name} row mismatch "
                f"{len(lines)} != {entry['rows']}"
            )

        actual_hash = sha256(path)
        if actual_hash != entry["sha256"]:
            raise SystemExit(
                f"{manifest_path}: {name} sha256 mismatch "
                f"{actual_hash} != {entry['sha256']}"
            )

    if int(manifest["rowCounts"]["experiment_run"]) != 1:
        raise SystemExit(f"{manifest_path}: experiment_run row count must equal 1")

    total_attempt_rows += int(manifest["rowCounts"]["booking_attempts"])

if total_attempt_rows <= 0:
    raise SystemExit("Evidence archive contains no booking attempts")

print(
    f"evidence-archive-validation: PASS "
    f"(manifests={len(manifests)}, booking_attempt_rows={total_attempt_rows})"
)
