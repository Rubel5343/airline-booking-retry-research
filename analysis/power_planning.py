#!/usr/bin/env python3
import math
from statistics import NormalDist

ALPHA = 0.05
POWER = 0.80

def cohen_h(p1: float, p2: float) -> float:
    return abs(2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2)))

def n_per_group(p1: float, p2: float, alpha: float = ALPHA, power: float = POWER) -> int:
    h = cohen_h(p1, p2)
    if h == 0:
        return math.inf
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(power)
    return math.ceil(2 * ((z_alpha + z_power) / h) ** 2)

comparisons = [
    (0.10, 0.05, "10% vs 5%"),
    (0.15, 0.08, "15% vs 8%"),
    (0.20, 0.10, "20% vs 10%"),
    (0.15, 0.05, "15% vs 5%"),
    (0.30, 0.15, "30% vs 15%"),
    (0.10, 0.02, "10% vs 2%"),
]

print("Conservative two-proportion planning approximation")
print(f"alpha={ALPHA}, power={POWER}")
print()
print("| Comparison | Cohen h | Approx. N / strategy |")
print("|---|---:|---:|")
for p1, p2, label in comparisons:
    h = cohen_h(p1, p2)
    n = n_per_group(p1, p2)
    print(f"| {label} | {h:.3f} | {n} |")

print()
print("Planning choice: 500 logical bookings per strategy per correctness cell.")
print("This exceeds the conservative requirement for detecting 10% vs 5% in a simple")
print("independent-proportion comparison. Final analysis additionally uses repeated seeds,")
print("paired fault cohorts, and run-level sensitivity checks; therefore this calculation")
print("is a lower-level planning aid, not the inferential model itself.")
