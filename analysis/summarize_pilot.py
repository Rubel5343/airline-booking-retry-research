#!/usr/bin/env python3
import glob
import json
import math
import statistics
from collections import defaultdict

rows = defaultdict(list)

for path in sorted(glob.glob("results/r*-*.json")):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    summary = payload.get("summary") or []
    if not summary:
        continue

    item = summary[0]
    name = path.split("/")[-1]
    parts = name.split("-")
    label = parts[1] if len(parts) > 1 else item["strategy"]
    logical = int(item["logicalBookings"])
    unresolved = int(item["unresolvedBookings"])

    rows[label].append({
        "duplicate_rate_pct": float(item["duplicateRatePct"]),
        "unknown_rate_pct": 100.0 * unresolved / logical if logical else math.nan,
        "avg_resolution_ms": float(item["avgResolutionMs"]),
        "p95_resolution_ms": float(item["p95ResolutionMs"]),
        "avg_supplier_calls": float(item["avgSupplierCallsPerBooking"]),
        "logical_bookings": logical,
    })

def describe(values):
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        return {"mean": math.nan, "sd": math.nan, "min": math.nan, "max": math.nan}
    return {
        "mean": statistics.fmean(clean),
        "sd": statistics.stdev(clean) if len(clean) > 1 else 0.0,
        "min": min(clean),
        "max": max(clean),
    }

out = {}
for label, items in sorted(rows.items()):
    out[label] = {
        "runs": len(items),
        "duplicateRatePct": describe([x["duplicate_rate_pct"] for x in items]),
        "unknownRatePct": describe([x["unknown_rate_pct"] for x in items]),
        "avgResolutionMs": describe([x["avg_resolution_ms"] for x in items]),
        "p95ResolutionMs": describe([x["p95_resolution_ms"] for x in items]),
        "avgSupplierCalls": describe([x["avg_supplier_calls"] for x in items]),
        "logicalBookingsPerRun": describe([x["logical_bookings"] for x in items]),
    }

print(json.dumps(out, indent=2))
with open("results/aggregate-summary.json", "w", encoding="utf-8") as handle:
    json.dump(out, handle, indent=2)
