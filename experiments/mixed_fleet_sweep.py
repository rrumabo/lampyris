import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.battery import Battery
from src.controllers import droop_controller, tou_controller
from src.simulator import (
    compute_frequency_nadir,
    compute_frequency_peak,
    compute_frequency_std,
    compute_peak_kw,
    run_simulation,
)

np.random.seed(42)
random.seed(42)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

n_steps       = 24
n_batteries   = 10
M             = 10.0
omega_nominal = 50.0
droop_gain    = 1.0
generation_kw = 30.0

positions = [round((i + 1) / n_batteries, 1) for i in range(n_batteries)]

n_droop_list          = list(range(1, n_batteries + 1))
assignment_strategies = ["near_source_first", "end_of_line_first", "random"]

loads_master = np.random.uniform(1, 5, size=(n_steps, n_batteries))
prices       = np.random.uniform(10, 100, n_steps)


def make_batteries(n: int) -> list[Battery]:
    return [
        Battery(capacity_kwh=50, max_charge_kw=10, max_discharge_kw=10,
                initial_soc=random.uniform(0.2, 0.8))
        for _ in range(n)
    ]


def assign_controllers(n_droop: int, strategy: str) -> list:
    """
    Returns a list of n_batteries controllers.
    n_droop batteries get droop_controller, the rest get tou_controller.
    Assignment order depends on strategy.
    """
    indices = list(range(n_batteries))

    if strategy == "near_source_first":
        droop_indices = set(indices[:n_droop])
    elif strategy == "end_of_line_first":
        droop_indices = set(indices[-n_droop:])
    else:
        droop_indices = set(random.sample(indices, n_droop))

    result = []
    for i in indices:
        if i in droop_indices:
            result.append(lambda **kw: droop_controller(**kw, droop_gain=droop_gain))
        else:
            result.append(tou_controller)
    return result


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

all_results = []

for strategy in assignment_strategies:
    for n_droop in n_droop_list:

        ctrl_list = assign_controllers(n_droop, strategy)

        result = run_simulation(
            load_profiles_kw = loads_master,
            prices           = prices,
            batteries        = make_batteries(n_batteries),
            controller       = ctrl_list,
            dt_hours         = 1.0,
            feeder_limit_kw  = 60.0,
            generation_kw    = generation_kw,
            M                = M,
            omega_nominal    = omega_nominal,
            positions        = positions,
        )

        nadir   = compute_frequency_nadir(result.omega_hz)
        std     = compute_frequency_std(result.omega_hz)
        stable  = nadir > 45.1 and compute_frequency_peak(result.omega_hz) < 54.9

        all_results.append({
            "strategy":           strategy,
            "n_droop":            n_droop,
            "pct_droop":          round(n_droop / n_batteries * 100),
            "frequency_nadir_hz": nadir,
            "frequency_peak_hz":  compute_frequency_peak(result.omega_hz),
            "frequency_std_hz":   std,
            "stable":             stable,
            "peak_kw":            compute_peak_kw(result.aggregate_load_kw),
        })

        print(
            f"  {strategy:<22} n_droop={n_droop:2d}  "
            f"nadir={nadir:.3f}  std={std:.3f}  "
            f"{'STABLE' if stable else 'UNSTABLE'}"
        )

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

df = pd.DataFrame(all_results)
output_dir  = Path("results")
output_dir.mkdir(exist_ok=True)
output_path = output_dir / "mixed_fleet_sweep_results.csv"
df.to_csv(output_path, index=False)
print(f"\nSaved: {output_path}")