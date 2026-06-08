import sys
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.network import Network, make_linear, make_star, make_small_world

np.random.seed(42)
random.seed(42)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

n_agents       = 20
n_steps        = 500
n_transient    = 200
n_runs         = 20       # runs per (topology, k) — statistical reliability
alpha          = 0.3
noise_sigma    = 0.3
noise_rho      = 0.7      # temporal correlation of local load signal
sync_threshold = 0.05

k_values  = np.linspace(0.0, 2.0, 40)

topologies = {
    "linear":      lambda k: make_linear(n_agents, k=k, alpha=alpha),
    "star":        lambda k: make_star(n_agents, k=k, alpha=alpha),
    "small_world": lambda k: make_small_world(n_agents, k_nn=4, p=0.1, k=k, alpha=alpha),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_once(net: Network, sigma: float, rho: float) -> dict:
    """
    Run one network for n_steps with temporally correlated noise.

    Local load signal:
        d_i(t+1) = rho * d_i(t) + (1-rho) * noise_i(t)
    This gives temporal structure to the forcing — agents don't
    see completely uncorrelated input every step.
    """
    n = len(net.agents)
    d = np.zeros(n)                  # initial load state
    std_history = []

    for t in range(n_steps):
        # Correlated noise update
        d = rho * d + (1.0 - rho) * np.random.normal(0, sigma, n)
        d = np.clip(d, -1.0, 1.0)

        loads = {i: float(d[i]) for i in range(n)}
        net.step(loads)

        if t >= n_transient:
            std_history.append(float(np.std(net.state_vector())))

    std_arr = np.array(std_history)
    below = np.where(std_arr < sync_threshold)[0]

    return {
        "mean_std":     float(np.mean(std_arr)),
        "final_std":    float(std_arr[-1]),
        "time_to_sync": int(below[0]) if len(below) > 0 else len(std_arr),
        "synced":       bool(std_arr[-1] < sync_threshold),
    }


def run_averaged(topo_fn, k: float, n_runs: int) -> dict:
    """
    Run n_runs independent realisations and return mean ± std.
    Each run gets a fresh network with the same k.
    """
    mean_stds, final_stds, times = [], [], []
    synced_count = 0

    for _ in range(n_runs):
        net = topo_fn(k)
        m = run_once(net, noise_sigma, noise_rho)
        mean_stds.append(m["mean_std"])
        final_stds.append(m["final_std"])
        times.append(m["time_to_sync"])
        if m["synced"]:
            synced_count += 1

    return {
        "mean_std_avg":   float(np.mean(mean_stds)),
        "mean_std_err":   float(np.std(mean_stds)),
        "final_std_avg":  float(np.mean(final_stds)),
        "time_sync_avg":  float(np.mean(times)),
        "sync_fraction":  synced_count / n_runs,
    }


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

all_results = []

print(f"=== Topology × k sweep  ({n_runs} runs each) ===\n")
print(f"  {'topology':<14} {'k':>6}  {'mean_std':>10}  {'sync_frac':>10}")
print(f"  {'-'*14} {'-'*6}  {'-'*10}  {'-'*10}")

for topo_name, topo_fn in topologies.items():
    for k in k_values:
        m = run_averaged(topo_fn, float(k), n_runs)

        all_results.append({
            "topology":      topo_name,
            "k":             round(float(k), 4),
            **m,
        })

        if abs(k - round(k * 2) / 2) < 0.03:    # print at 0, 0.5, 1.0, 1.5, 2.0
            print(
                f"  {topo_name:<14} {k:6.2f}  "
                f"{m['mean_std_avg']:10.4f}  "
                f"{m['sync_fraction']:10.2f}"
            )

# ---------------------------------------------------------------------------
# Save CSV
# ---------------------------------------------------------------------------

df = pd.DataFrame(all_results)
output_dir = Path("results")
output_dir.mkdir(exist_ok=True)
csv_path = output_dir / "topology_sweep_results.csv"
df.to_csv(csv_path, index=False)
print(f"\nSaved: {csv_path}")

# ---------------------------------------------------------------------------
# Plot: k vs order parameter per topology
# ---------------------------------------------------------------------------

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

colors = {"linear": "#2196F3", "star": "#FF5722", "small_world": "#4CAF50"}

# Left: mean_std ± error
ax = axes[0]
for topo_name in topologies:
    sub = df[df["topology"] == topo_name].sort_values("k")
    ax.plot(sub["k"], sub["mean_std_avg"],
            label=topo_name, color=colors[topo_name], linewidth=2)
    ax.fill_between(
        sub["k"],
        sub["mean_std_avg"] - sub["mean_std_err"],
        sub["mean_std_avg"] + sub["mean_std_err"],
        color=colors[topo_name], alpha=0.15,
    )
ax.axhline(sync_threshold, color="gray", linestyle="--", linewidth=1,
           label="sync threshold")
ax.set_xlabel("Coupling strength k")
ax.set_ylabel("mean std(states)")
ax.set_title("Order parameter vs k")
ax.legend()
ax.grid(alpha=0.3)

# Right: sync fraction
ax = axes[1]
for topo_name in topologies:
    sub = df[df["topology"] == topo_name].sort_values("k")
    ax.plot(sub["k"], sub["sync_fraction"],
            label=topo_name, color=colors[topo_name], linewidth=2)
ax.set_xlabel("Coupling strength k")
ax.set_ylabel("Fraction of runs that synchronised")
ax.set_title("Synchronisation probability vs k")
ax.legend()
ax.grid(alpha=0.3)

plt.tight_layout()
plot_path = output_dir / "topology_sweep_plot.png"
plt.savefig(plot_path, dpi=150)
plt.close()
print(f"Saved: {plot_path}")