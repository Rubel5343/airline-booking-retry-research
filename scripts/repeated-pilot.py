#!/usr/bin/env python3
import json
import os
import pathlib
import random
import subprocess

REPETITIONS = int(os.environ.get("REPETITIONS", "3"))
BASE_SEED = int(os.environ.get("BASE_SEED", "42000"))
SCENARIO = os.environ.get("SCENARIO", "configs/scenario-baseline.json")
GIT_COMMIT = os.environ.get("GIT_COMMIT", os.environ.get("GITHUB_SHA", "unknown"))

strategies = ["S1", "S2", "S3A", "S3B"]
scenario_slug = pathlib.Path(SCENARIO).stem.replace("scenario-", "")
results_dir = pathlib.Path("results")
results_dir.mkdir(exist_ok=True)

manifest = {
    "repetitions": REPETITIONS,
    "baseSeed": BASE_SEED,
    "scenario": SCENARIO,
    "gitCommit": GIT_COMMIT,
    "runs": [],
}

for repetition in range(1, REPETITIONS + 1):
    seed = BASE_SEED + repetition - 1
    rng = random.Random(seed)
    order = strategies.copy()
    rng.shuffle(order)
    fault_cohort = f"{scenario_slug}-rep-{repetition}-seed-{seed}"

    manifest["runs"].append({
        "repetition": repetition,
        "seed": seed,
        "order": order,
        "faultCohort": fault_cohort,
    })

    env = os.environ.copy()
    env.update({
        "SEED": str(seed),
        "REPETITION": str(repetition),
        "ORDER": " ".join(order),
        "FAULT_COHORT": fault_cohort,
        "GIT_COMMIT": GIT_COMMIT,
        "SCENARIO": SCENARIO,
    })

    print(
        f"\n### repetition={repetition} seed={seed} "
        f"cohort={fault_cohort} order={' '.join(order)}",
        flush=True,
    )
    subprocess.run(["bash", "scripts/pilot-run.sh"], check=True, env=env)

manifest_path = results_dir / "manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"\nmanifest={manifest_path}")
