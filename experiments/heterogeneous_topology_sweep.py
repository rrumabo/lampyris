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
n_runs         = 20
alpha          = 0.3
noise_sigma    = 0.3
noise_rho      = 0.7
leader_frac    = 0.15     # 15% leaders

topologies = {
    "linear":      lambda: make_linear(n_agents, k=1.0, alpha=alpha),
    "star":        lambda: make_star(n_agents, k=1.0, alpha=alpha),
    "small_world": lambda: make_small_world(n_agents, k_nn=4, p=0.1,
                                             k=1.0, alpha=alpha),
}


def assign_k(net: Network, distribution: str) -> dict:
    """
    Assign k_i values to agents according to distribution.
    Returns dict {agent_id: k_i} for tracking.
    """
    ids = sorted(net.agents.keys())
    n   = len(ids)

    if distribution == "homogeneous":
        k_vals = np.full(n, 0.15)

    elif distribution == "bimodal":
        n_leaders = max(1, int(leader_frac * n))
        k_vals    = np.random.uniform(0.1, 0.5, n)
        leader_ids = np.random.choice(n, n_leaders, replace=False)
        k_vals[leader_ids] = np.random.uniform(1.0, 1.5, n_leaders)

    elif distribution == "uniform":
        k_vals = np.random.uniform(0.1, 1.5, n)

    for i, aid in enumerate(ids):
        net.agents[aid].k = float(k_vals[i])

    return {aid: float(k_vals[i]) for i, aid in enumerate(ids)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_once(net: Network, k_map: dict) -> dict:
    n = len(net.agents)
    d = np.zeros(n)
    final_states = None

    for t in range(n_steps):
        d = noise_rho * d + (1.0 - noise_rho) * np.random.normal(0, noise_sigma, n)
        d = np.clip(d, -1.0, 1.0)
        loads = {i: float(d[i]) for i in range(n)}
        net.step(loads)

        if t == n_steps - 1:
            final_states = net.state_vector()

    std_final = float(np.std(final_states))
    synced    = bool(std_final < 0.05)

    # Leader/follower analysis
    k_vals  = np.array([k_map[aid] for aid in sorted(k_map)])
    abs_states = np.abs(final_states)

    # Correlation between k_i and |x_i| at end
    if np.std(k_vals) > 0 and np.std(abs_states) > 0:
        corr = float(np.corrcoef(k_vals, abs_states)[0, 1])
    else:
        corr = 0.0

    # Leader vs follower mean |state|
    threshold = np.percentile(k_vals, 85)
    leader_mask   = k_vals >= threshold
    follower_mask = ~leader_mask

    leader_state   = float(np.mean(abs_states[leader_mask]))
    follower_state = float(np.mean(abs_states[follower_mask])) if np.any(follower_mask) else 0.0
    return {
        "final_std":      std_final,
        "synced":         synced,
        "k_state_corr":   corr,
        "leader_state":   leader_state,
        "follower_state": follower_state,
    }


def run_averaged(topo_fn, distribution: str, n_runs: int) -> dict:
    metrics_list = []
    for _ in range(n_runs):
        net   = topo_fn()
        k_map = assign_k(net, distribution)
        m     = run_once(net, k_map)
        metrics_list.append(m)

    keys = metrics_list[0].keys()
    averaged = {}
    for key in keys:
        if key == "synced":
            averaged["sync_fraction"] = float(
                sum(m[key] for m in metrics_list) / n_runs)
        else:
            vals = [m[key] for m in metrics_list]
            averaged[f"{key}_avg"] = float(np.mean(vals))
            averaged[f"{key}_err"] = float(np.std(vals))
    return averaged


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

distributions = ["homogeneous", "bimodal", "uniform"]
all_results   = []

print(f"=== Heterogeneous k sweep ({n_runs} runs each) ===\n")
print(f"  {'topology':<14} {'distribution':<14} {'std':>8}  "
      f"{'sync':>6}  {'k-corr':>8}  {'leader|x|':>10}  {'follow|x|':>10}")
print(f"  {'-'*14} {'-'*14} {'-'*8}  {'-'*6}  {'-'*8}  {'-'*10}  {'-'*10}")

for topo_name, topo_fn in topologies.items():
    for dist in distributions:
        m = run_averaged(topo_fn, dist, n_runs)
        all_results.append({
            "topology":     topo_name,
            "distribution": dist,
            **m,
        })
        print(
            f"  {topo_name:<14} {dist:<14} "
            f"{m['final_std_avg']:8.3f}  "
            f"{m['sync_fraction']:6.2f}  "
            f"{m['k_state_corr_avg']:8.3f}  "
            f"{m['leader_state_avg']:10.3f}  "
            f"{m['follower_state_avg']:10.3f}"
        )

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

df = pd.DataFrame(all_results)
output_dir = Path("results")
output_dir.mkdir(exist_ok=True)
csv_path = output_dir / "heterogeneous_k_results.csv"
df.to_csv(csv_path, index=False)
print(f"\nSaved: {csv_path}")

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

fig, axes = plt.subplots(1, 3, figsize=(14, 5))
colors = {"homogeneous": "#2196F3", "bimodal": "#FF5722", "uniform": "#4CAF50"}
x = np.arange(len(topologies))
width = 0.25

metrics_plot = [
    ("final_std_avg",      "final_std_err",      "Final std(states) — disorder"),
    ("sync_fraction",      None,                  "Sync fraction"),
    ("k_state_corr_avg",   "k_state_corr_err",   "Corr(k_i, |x_i|) — leader signal"),
]

for ax, (metric, err_col, title) in zip(axes, metrics_plot):
    for di, dist in enumerate(distributions):
        sub = df[df["distribution"] == dist].sort_values("topology")
        vals = sub[metric].values
        errs = sub[err_col].values if err_col and err_col in sub.columns else None
        ax.bar(x + di * width, vals, width,
               label=dist, color=colors[dist], alpha=0.85,
               yerr=errs, capsize=3)

    ax.set_xticks(x + width)
    ax.set_xticklabels(list(topologies.keys()), rotation=10)
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

plt.tight_layout()
plot_path = output_dir / "heterogeneous_k_plot.png"
plt.savefig(plot_path, dpi=150)
plt.close()
print(f"Saved: {plot_path}")