"""Steps 1-3: a PV energy community on a real AC radial distribution feeder using real Paphos PV data.

Step 1  rho in the realistic range 0.7-1 (same clouds over the same street),
        plus rho = 0 as a reference.
Step 2  two price rules: "fixed" (PV-shaped price) vs "sdr"
        (set every step by the community's supply and demand -> feedback).
Step 3  full nonlinear AC power flow (C++ FBS solver) across urban (40m) vs rural (100m)
        radial street topologies using real hourly PVGIS-SARAH3 Paphos solar profiles.

Run from the repo root:   python -m experiments.run_community
Outputs: results/community/raw.csv, summary.csv, gates.txt, community_ac.png
"""
from __future__ import annotations

import functools
import io
from pathlib import Path

from joblib import Parallel, delayed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm

from experiments.reproduce_core_result import (
    make_load_profiles, make_batteries, compute_pv_metrics,
)
from experiments.spectral_diagnostics import spectral_diagnostics
from semele.ac_feeder import RadialStreetFeeder
from semele.battery import Battery
from semele.controllers import belief_neighborhood_controller
from semele.network import make_small_world
from semele.pricing import pv_shaped_price
from semele.simulator import run_simulation

# --- configuration ------------------------------------------------------
SEED = 42
N_HOUSES = 20
N_STEPS = 24
N_RUNS = 100

RHO_VALUES = [0.0, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
PRICE_RULES = ["fixed", "sdr"]
BATTERY_POWER_KW = [3.0, 5.0, 7.0, 10.0]   # per house
BATTERY_HOURS = 4.0                         # capacity = power * 4 h
TOPOLOGIES = {
    "urban_40m": 0.04,   # 40 m spacing between houses (compact suburban/urban street)
    "rural_100m": 0.10,  # 100 m spacing between houses (long rural village feeder)
}

FEEDER_LIMIT_PER_HOUSE_KW = 6.0             # legacy scalar reference limit
GRID_PRICE, FEED_IN_PRICE = 80.0, 20.0
LOW_PRICE, HIGH_PRICE = 30.0, 70.0
PRICE_SIGMA, FORECAST_SIGMA = 20.0, 1.0
BELIEF_WEIGHT = 0.5

FEEDER_LIMIT_KW = FEEDER_LIMIT_PER_HOUSE_KW * N_HOUSES
ROOT = Path(__file__).resolve().parents[1]
PV_CSV = ROOT / "data" / "paphos_pv_hourly.csv"
OUT = ROOT / "results" / "community"
OUT.mkdir(parents=True, exist_ok=True)

# Per-process feeder cache so each CPU core builds its feeder object only once
_WORKER_FEEDERS: dict[str, RadialStreetFeeder] = {}


def _get_worker_feeder(topo_name: str, spacing_km: float) -> RadialStreetFeeder:
    if topo_name not in _WORKER_FEEDERS:
        _WORKER_FEEDERS[topo_name] = RadialStreetFeeder(
            n_houses=N_HOUSES, spacing_km=spacing_km, trafo_mva=0.25
        )
    return _WORKER_FEEDERS[topo_name]


def load_paphos_pv_days(csv_path: Path, n_houses: int) -> np.ndarray:
    """Parse raw EU PVGIS-SARAH3 hourly CSV into shape (N_days, 24) in kW for the whole street."""
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    start_idx = next(i for i, line in enumerate(lines) if line.startswith("time,"))
    end_idx = next(
        (i for i in range(start_idx + 1, len(lines)) if not lines[i] or not lines[i][0].isdigit()),
        len(lines),
    )
    df = pd.read_csv(io.StringIO("\n".join(lines[start_idx:end_idx])))
    df["ts_utc"] = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", utc=True)
    df["ts_cy"] = df["ts_utc"].dt.tz_convert("Asia/Nicosia")
    df["date"] = df["ts_cy"].dt.date
    df["hour"] = df["ts_cy"].dt.hour
    df["street_pv_kw"] = (df["P"] / 1000.0) * n_houses

    pivot = df.pivot_table(index="date", columns="hour", values="street_pv_kw", aggfunc="mean").dropna()
    return pivot.to_numpy(dtype=np.float64)


# --- one run --------------------------------------------------------------
def one_run(
    run_id: int,
    topo_name: str,
    spacing_km: float,
    rho: float,
    rule: str,
    p_kw: float,
    paphos_days_kw: np.ndarray,
) -> dict:
    feeder = _get_worker_feeder(topo_name, spacing_km)
    rng = np.random.default_rng(SEED + run_id)          # same world for every condition

    # Sample a real 24-hour Paphos PV day spread evenly across the year
    day_idx = (run_id * len(paphos_days_kw) // N_RUNS) % len(paphos_days_kw)
    pv_kw = paphos_days_kw[day_idx]
    prices_fixed = pv_shaped_price(pv_kw, high=GRID_PRICE, swing=GRID_PRICE - FEED_IN_PRICE)

    loads = make_load_profiles(rng, N_STEPS, N_HOUSES)
    soc0 = make_batteries(rng, N_HOUSES)                # reuse its random initial SoC
    batteries = [Battery(capacity_kwh=p_kw * BATTERY_HOURS, max_charge_kw=p_kw,
                         max_discharge_kw=p_kw, initial_soc=b.initial_soc) for b in soc0]

    np.random.seed(SEED + run_id)                       # same noise draws for every condition
    res = run_simulation(
        load_profiles_kw=loads, prices=prices_fixed, batteries=batteries,
        controller=functools.partial(belief_neighborhood_controller, belief_weight=BELIEF_WEIGHT),
        network=make_small_world(N_HOUSES, seed=SEED),
        low_threshold=LOW_PRICE, high_threshold=HIGH_PRICE,
        feeder_limit_kw=FEEDER_LIMIT_KW, rho_agents=rho,
        forecast_error_sigma_kw=FORECAST_SIGMA, price_sigma=PRICE_SIGMA,
        pv_kw=pv_kw, price_rule=rule, grid_price=GRID_PRICE, feed_in_price=FEED_IN_PRICE,
        ac_feeder=feeder,
    )

    # Same day with no batteries: legacy scalar limit AND real AC voltage baseline.
    net0 = loads.sum(axis=1) - pv_kw
    viol0 = (net0 > FEEDER_LIMIT_KW) | (net0 < -FEEDER_LIMIT_KW)

    pv_per_house = pv_kw / N_HOUSES
    v_plan_viol0 = np.zeros(N_STEPS, dtype=bool)
    for t in range(N_STEPS):
        ac0 = feeder.step(loads[t] - pv_per_house[t])
        v_plan_viol0[t] = ac0["voltage_planning_viol"]

    w1, pr, _ = spectral_diagnostics(res.per_battery_power_kw, subtract_mean=False)
    charging = np.maximum(0.0, -res.aggregate_battery_power_kw)
    pv = compute_pv_metrics(loads, pv_kw, res.aggregate_battery_power_kw, 1.0)
    return {
        "run_id": run_id, "topology": topo_name, "rho": rho, "rule": rule, "battery_kw": p_kw,
        "peak_charge_ratio": charging.max() / FEEDER_LIMIT_KW,
        "battery_caused_viol": res.feeder_violations.mean() - viol0.mean(),
        # --- New AC Physical Grid Metrics ---
        "v_min_pu": float(res.v_min_pu.min()),
        "v_max_pu": float(res.v_max_pu.max()),
        "v_plan_viol": float(res.voltage_planning_viol.mean()),
        "battery_caused_v_viol": float(res.voltage_planning_viol.mean() - v_plan_viol0.mean()),
        "v_stat_viol": float(res.voltage_statutory_viol.mean()),
        "trafo_max_pct": float(res.trafo_loading_pct.max()),
        "thermal_overload": float(res.thermal_overload.mean()),
        # --- Spectral & Price Diagnostics ---
        "curtailment": pv["pv_curtailment_fraction"],
        "w1": w1, "PR": pr,
        "price_std": res.price.std(),
        "price_flips": np.mean(np.abs(np.diff(res.price)) > 0.5 * (GRID_PRICE - FEED_IN_PRICE)),
    }


# --- gates ----------------------------------------------------------------
def gates(s: pd.DataFrame) -> str:
    lines = []
    for topo in TOPOLOGIES:
        hi = s[(s.topology == topo) & (s.rho == 1.0)]
        lines.append(f"=== TOPOLOGY: {topo} (rho = 1.0, Real Paphos PVGIS-SARAH3 PV) ===")
        lines.append("  battery  | V_min(pu) fixed sdr | bat-caused V-viol fixed sdr | trafo_max% fixed sdr | flips sdr")
        for p in BATTERY_POWER_KW:
            f = hi[(hi.rule == "fixed") & (hi.battery_kw == p)].iloc[0]
            d = hi[(hi.rule == "sdr") & (hi.battery_kw == p)].iloc[0]
            lines.append(
                f"  {p:4.0f} kW  |   {f.v_min_pu:.3f}   {d.v_min_pu:.3f}   |"
                f"       {f.battery_caused_v_viol:.3f}     {d.battery_caused_v_viol:.3f}   |"
                f"    {f.trafo_max_pct:5.1f}%   {d.trafo_max_pct:5.1f}%  |  {d.price_flips:.2f}"
            )
        lines.append("")
    return "\n".join(lines)

# --- plot -----------------------------------------------------------------
def plot(s: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    panels = [
        ("v_min_pu", "Worst-case bus voltage V_min (p.u.)"),
        ("battery_caused_v_viol", "Battery-caused voltage violations (+-5% limit)"),
        ("trafo_max_pct", "Peak transformer loading (%)"),
        ("w1", "w1 (fleet moving as one)"),
    ]
    for ax, (col, label) in zip(axes.flat, panels):
        for topo, marker in [("urban_40m", "o"), ("rural_100m", "s")]:
            for p, color in zip(BATTERY_POWER_KW, ["C0", "C1", "C2", "C3"]):
                for rule, ls in [("fixed", "-"), ("sdr", "--")]:
                    sub = s[(s.topology == topo) & (s.battery_kw == p) & (s.rule == rule)]
                    ax.plot(
                        sub.rho, sub[col], ls, color=color, marker=marker, ms=3, alpha=0.85,
                        label=f"{topo[:5]} {p:.0f}kW {rule}" if col == "v_min_pu" else None
                    )
        if col == "v_min_pu":
            ax.axhline(0.95, color="red", ls=":", lw=1.2, label="0.95 p.u. limit")
        if col == "trafo_max_pct":
            ax.axhline(100.0, color="red", ls=":", lw=1.2, label="100% thermal limit")
        ax.set_xlabel("rho")
        ax.set_ylabel(label)

    axes[0, 0].legend(fontsize=6, ncol=2)
    fig.suptitle("Real Paphos PV + AC Feeder: Urban (40m) vs Rural (100m) | Fixed (solid) vs SDR (dashed)")
    fig.tight_layout()
    fig.savefig(OUT / "community_ac.png", dpi=160)


def main() -> None:
    paphos_days_kw = load_paphos_pv_days(PV_CSV, N_HOUSES)
    print(f"Loaded {len(paphos_days_kw)} real Paphos PV days (max street PV: {paphos_days_kw.max():.1f} kW)")

    tasks = [
        (r, topo_name, spacing, rho, rule, p)
        for topo_name, spacing in TOPOLOGIES.items()
        for p in BATTERY_POWER_KW
        for rule in PRICE_RULES
        for rho in RHO_VALUES
        for r in range(N_RUNS)
    ]

    rows = Parallel(n_jobs=-1, batch_size=32)(
        delayed(one_run)(r, topo_name, spacing, rho, rule, p, paphos_days_kw)
        for r, topo_name, spacing, rho, rule, p in tqdm(tasks, desc="AC Sweep", unit="run")
    )

    raw = pd.DataFrame(rows)
    raw.to_csv(OUT / "raw.csv", index=False)

    summary = raw.groupby(["topology", "battery_kw", "rule", "rho"], as_index=False).mean(numeric_only=True)
    summary = summary.drop(columns="run_id")
    summary.to_csv(OUT / "summary.csv", index=False)

    text = gates(summary)
    (OUT / "gates.txt").write_text(text + "\n")
    print(text)
    plot(summary)
    print(f"\nsaved results to {OUT}")


if __name__ == "__main__":
    main()