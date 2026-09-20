#!/usr/bin/env python3
import os
import subprocess

for rate in (5, 20, 50):
    env = os.environ.copy()
    env.update({
        "CONDITION_ID": f"C-R{rate}",
        "RATE": str(rate),
        "MEASUREMENT_DURATION": "5s",
        "WARMUP_DURATION": "2s",
        "SEED": str(72000 + rate),
        "REPETITION": "1",
        "PRE_VUS": "100",
        "MAX_VUS": "500",
        "GRACEFUL_STOP": "10s",
        "STRATEGY_LABELS": "S1,S2,S3B3",
        "RESULTS_DIR": "results/v11-load-validation",
        "PROTOCOL_VERSION": os.environ.get("PROTOCOL_VERSION", "v1.1-draft"),
        "RUN_MODE": "validation",
        "GIT_COMMIT": os.environ.get("GITHUB_SHA", "unknown"),
    })
    print(f"\nValidating Stage C rate={rate} RPS", flush=True)
    subprocess.run(["python3", "scripts/load_cell_runner.py"], check=True, env=env)

print("\nprotocol-v1.1 reduced Stage C validation: PASS")
