"""
Sweep cross-agent belief correlation (rho_agents) across network topologies.

Question:
    What is the critical belief correlation rho_c above which topology can no
    longer prevent synchronization-driven collective failure?

Controller:
    tou_controller with correlated price-signal noise.

Metrics:
    sync_index = mean_t(std_i(per_battery_power_kw[t, i]))
        Low sync_index  -> batteries act similarly / synchronized
        High sync_index -> batteries act differently / desynchronized

    rho_c_sync_collapse:
        First rho where sync_index falls below the rho=0 baseline by 2 std.

    rho_c_failure:
        First rho where feeder violation fraction rises above the rho=0
        baseline by 2 std.

    protection_gap:
        rho_c_failure - rho_c_sync_collapse
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.battery import Battery
from src.controllers import tou_controller
from src.network import make_linear, make_small_world, make_star
from src.simulator import run_simulation


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

seed = 42
rng = np.random.default_rng(seed)

rho_values = np.linspace(0.0, 1.0, 20)
n_runs = 20

n_steps = 24
n_batteries = 30

M = 10.0
forecast_error_sigma_kw = 1.0
price_sigma = 20.0
feeder_limit_kw = 120.0

battery_capacity_kwh = 20.0
battery_power_kw = 5.0

alpha = 0.1
network_k = 0.2

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CSV_PATH = RESULTS_DIR / "rho_sweep_results.csv"
SUMMARY_PATH = RESULTS_DIR / "rho_sweep_summary.csv"
THRESHOLD_PATH = RESULTS_DIR / "rho_sweep_thresholds.csv"
PLOT_PATH = RESULTS_DIR / "rho_sweep_plot.png"
GAP_PLOT_PATH = RESULTS_DIR / "rho_sweep_protection_gap.png"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def make_loads_and_prices(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Create randomized load and price profiles that excite the controller."""
    load_profiles_kw = rng.uniform(1.0, 5.0, size=(n_steps, n_batteries))
    prices = rng.uniform(10.0, 100.0, size=n_steps)
    return load_profiles_kw, prices


def make_batteries(rng: np.random.Generator) -> list[Battery]:
    """Create a fresh heterogeneous battery fleet for each run."""
    return [
        Battery(
            capacity_kwh=battery_capacity_kwh,
            max_charge_kw=battery_power_kw,
            max_discharge_kw=battery_power_kw,
            initial_soc=float(rng.uniform(0.2, 0.8)),
        )
        for _ in range(n_batteries)
    ]


def build_topologies():
    """Return topology factories. legacy_ring uses simulator fallback logic."""
    return {
        "legacy_ring": lambda: None,
        "linear": lambda: make_linear(n_batteries, k=network_k, alpha=alpha),
        "star": lambda: make_star(n_batteries, k=network_k, alpha=alpha),
        "small_world": lambda: make_small_world(
            n_batteries,
            k_nn=4,
            p=0.1,
            k=network_k,
            alpha=alpha,
        ),
    }


def synchronization_index(per_battery_power_kw: np.ndarray) -> float:
    """Average cross-agent action spread through time."""
    return float(np.mean(np.std(per_battery_power_kw, axis=1)))


def find_rho_c_lower(
    rho_values_in: np.ndarray,
    metric_means: np.ndarray,
    baseline_mean: float,
    baseline_std: float,
) -> float | None:
    """First rho where metric falls below rho=0 baseline by two std."""
    threshold = baseline_mean - 2.0 * baseline_std
    below = np.where(metric_means < threshold)[0]
    return float(rho_values_in[below[0]]) if len(below) > 0 else None


def find_rho_c_upper(
    rho_values_in: np.ndarray,
    metric_means: np.ndarray,
    baseline_mean: float,
    baseline_std: float,
) -> float | None:
    """First rho where metric exceeds rho=0 baseline by two std."""
    threshold = baseline_mean + 2.0 * baseline_std
    above = np.where(metric_means > threshold)[0]
    return float(rho_values_in[above[0]]) if len(above) > 0 else None


def compute_threshold_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """Compute rho_c metrics and topology protection gap."""
    rows: list[dict[str, float | str | None]] = []

    for topology_name in summary["topology"].unique():
        sub = summary[summary["topology"] == topology_name].sort_values("rho_agents")

        rho = sub["rho_agents"].to_numpy(dtype=float)
        sync_means = sub["sync_mean"].to_numpy(dtype=float)
        violation_means = sub["violation_mean"].to_numpy(dtype=float)

        baseline = sub[sub["rho_agents"] == 0.0]
        if baseline.empty:
            raise ValueError(f"missing rho=0 baseline for topology={topology_name}")

        sync_baseline_mean = float(baseline["sync_mean"].iloc[0])
        sync_baseline_std = float(baseline["sync_std"].fillna(0.0).iloc[0])
        violation_baseline_mean = float(baseline["violation_mean"].iloc[0])
        violation_baseline_std = float(baseline["violation_std"].fillna(0.0).iloc[0])

        sync_threshold = sync_baseline_mean - 2.0 * sync_baseline_std
        failure_threshold = violation_baseline_mean + 2.0 * violation_baseline_std

        rho_c_sync_collapse = find_rho_c_lower(
            rho,
            sync_means,
            sync_baseline_mean,
            sync_baseline_std,
        )
        rho_c_failure = find_rho_c_upper(
            rho,
            violation_means,
            violation_baseline_mean,
            violation_baseline_std,
        )

        protection_gap = (
            rho_c_failure - rho_c_sync_collapse
            if rho_c_failure is not None and rho_c_sync_collapse is not None
            else None
        )

        print(
            f"thresholds topology={topology_name:12s} "
            f"sync_collapse={sync_threshold:.6f} "
            f"failure={failure_threshold:.6f} "
            f"rho_c_sync_collapse={rho_c_sync_collapse} "
            f"rho_c_failure={rho_c_failure}"
        )

        rows.append(
            {
                "topology": topology_name,
                "sync_collapse_threshold": sync_threshold,
                "failure_threshold": failure_threshold,
                "rho_c_sync_collapse": rho_c_sync_collapse,
                "rho_c_failure": rho_c_failure,
                "protection_gap": protection_gap,
            }
        )

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Experiment
# -----------------------------------------------------------------------------


def main() -> None:
    load_profiles_kw, prices = make_loads_and_prices(rng)
    topology_factories = build_topologies()
    rows: list[dict[str, float | int | str]] = []

    for topology_name, topology_factory in topology_factories.items():
        for rho_agents in rho_values:
            for run_id in range(n_runs):
                run_seed = int(rng.integers(0, 2**32 - 1))
                np.random.seed(run_seed)

                network = topology_factory()
                batteries = make_batteries(rng)

                result = run_simulation(
                    load_profiles_kw=load_profiles_kw,
                    prices=prices,
                    batteries=batteries,
                    controller=tou_controller,
                    M=M,
                    feeder_limit_kw=feeder_limit_kw,
                    rho_agents=float(rho_agents),
                    forecast_error_sigma_kw=forecast_error_sigma_kw,
                    price_sigma=price_sigma,
                    network=network,
                )

                sync_index = synchronization_index(result.per_battery_power_kw)

                rows.append(
                    {
                        "topology": topology_name,
                        "rho_agents": float(rho_agents),
                        "run_id": run_id,
                        "run_seed": run_seed,
                        "sync_index": sync_index,
                        "mean_aggregate_battery_kw": float(
                            np.mean(result.aggregate_battery_power_kw)
                        ),
                        "std_aggregate_battery_kw": float(
                            np.std(result.aggregate_battery_power_kw)
                        ),
                        "feeder_violation_fraction": float(
                            np.mean(result.feeder_violations)
                        ),
                    }
                )

            print(f"finished topology={topology_name:12s} rho={rho_agents:.3f}")

    df = pd.DataFrame(rows)
    df.to_csv(CSV_PATH, index=False)
    print(f"saved {CSV_PATH}")

    summary = (
        df.groupby(["topology", "rho_agents"], as_index=False)
        .agg(
            sync_mean=("sync_index", "mean"),
            sync_std=("sync_index", "std"),
            violation_mean=("feeder_violation_fraction", "mean"),
            violation_std=("feeder_violation_fraction", "std"),
        )
        .sort_values(["topology", "rho_agents"])
    )
    summary.to_csv(SUMMARY_PATH, index=False)
    print(f"saved {SUMMARY_PATH}")

    threshold_summary = compute_threshold_summary(summary)
    threshold_summary.to_csv(THRESHOLD_PATH, index=False)
    print(f"saved {THRESHOLD_PATH}")

    plt.figure(figsize=(9, 5))
    for topology_name in summary["topology"].unique():
        sub = summary[summary["topology"] == topology_name]
        plt.plot(sub["rho_agents"], sub["sync_mean"], marker="o", label=topology_name)

    plt.xlabel("rho_agents")
    plt.ylabel("sync_index")
    plt.title("Synchronization spread vs correlated price-signal noise across topologies")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_PATH, dpi=200)
    print(f"saved {PLOT_PATH}")

    gap_df = threshold_summary.dropna(subset=["protection_gap"])
    if not gap_df.empty:
        plt.figure(figsize=(8, 5))
        plt.bar(gap_df["topology"], gap_df["protection_gap"])
        plt.xlabel("Topology")
        plt.ylabel("rho_c_failure - rho_c_sync_collapse")
        plt.title("Topology protection window")
        plt.tight_layout()
        plt.savefig(GAP_PLOT_PATH, dpi=200)
        print(f"saved {GAP_PLOT_PATH}")
    else:
        print("no finite protection gaps to plot")


if __name__ == "__main__":
    main()
