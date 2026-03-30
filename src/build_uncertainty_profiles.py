import os
from typing import Any, Dict, List

import pandas as pd

DATA_DIR = "data/processed"
INPUT_FILE = os.path.join(DATA_DIR, "error_stats_hourly.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "uncertainty_profile_hourly.csv")

KEEP_COLUMNS = [
    "mean_error",
    "std_error",
    "p50",
    "p90",
    "p95",
    "p99",
]


def build_uncertainty_profiles() -> None:
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"Missing hourly error stats file: {INPUT_FILE}. Run compute_error_stats.py first."
        )

    df = pd.read_csv(INPUT_FILE)

    required_columns = {"variable", "hour", *KEEP_COLUMNS}
    missing = required_columns.difference(df.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns in {INPUT_FILE}: {missing_str}")

    profile = (
        df.groupby(["variable", "hour"], as_index=False)[KEEP_COLUMNS]
        .mean()
        .sort_values(["variable", "hour"])
        .reset_index(drop=True)
    )

    profile.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved uncertainty profile: {OUTPUT_FILE}")
    print(profile.head(12))


if __name__ == "__main__":
    build_uncertainty_profiles()