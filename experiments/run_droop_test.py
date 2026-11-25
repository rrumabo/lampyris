"""Phase 13: Compare unmitigated vs EN 50549-1 Volt-Watt droop on real Paphos PV data.

Run from repo root: python -m experiments.run_droop_test
"""
from __future__ import annotations

import functools
from pathlib import Path

from joblib import Parallel, delayed
import numpy as np
import pandas as pd
from tqdm import tqdm

from experiments.reproduce_core_result import make_load_profiles, make_batteries
from experiments.run_community import (
    SEED, N_HOUSES, N_STEPS, N_RUNS, BATTERY_POWER_KW, BATTERY_HOURS,
    TOPOLOGIES, FEEDER_LIMIT_KW, GRID_PRICE, FEED_IN_PRICE, LOW_PRICE, HIGH_PRICE,
    PRICE_SIGMA, FORECAST_SIGMA, BELIEF_WEIGHT, PV_CSV, _get_worker_feeder, load_paphos_pv_days,
)
from semele.battery import Battery
from semele.controllers import belief_neighborhood_controller, volt_watt_droop_controller
from semele.network import make_small_world
from semele.pricing import pv_shaped_price
from semele.simulator import run_simulation

OUT = Path(__file__).resolve().parents[1] / "results" / "droop"
OUT.mkdir(parents=True, exist_ok=True)


def one_run(run_id: int, topo: str, spacing: float, rule: str, p_kw: float, use_droop: bool, days: np.ndarray) -> dict:
    feeder = _get_worker_feeder(topo, spacing)
    rng = np.random.default_rng(SEED + run_id)

    pv_kw = days[(run_id * len(days) // N_RUNS) % len(days)]
    prices_fixed = pv_shaped_price(pv_kw, high=GRID_PRICE, swing=GRID_PRICE - FEED_IN_PRICE)
    loads = make_load_profiles(rng, N_STEPS, N_HOUSES)
    soc0 = make_batteries(rng, N_HOUSES)
    batteries = [Battery(capacity_kwh=p_kw * BATTERY_HOURS, max_charge_kw=p_kw,
                         max_discharge_kw=p_kw, initial_soc=b.initial_soc) for b in soc0]

    ctrl_fn = volt_watt_droop_controller if use_droop else belief_neighborhood_controller
    np.random.seed(SEED + run_id)
    res = run_simulation(
        load_profiles_kw=loads, prices=prices_fixed, batteries=batteries,
        controller=functools.partial(ctrl_fn, belief_weight=BELIEF_WEIGHT),
        network=make_small_world(N_HOUSES, seed=SEED),
        low_threshold=LOW_PRICE, high_threshold=HIGH_PRICE,
        feeder_limit_kw=FEEDER_LIMIT_KW, rho_agents=1.0,
        forecast_error_sigma_kw=FORECAST_SIGMA, price_sigma=PRICE_SIGMA,
        pv_kw=pv_kw, price_rule=rule, grid_price=GRID_PRICE, feed_in_price=FEED_IN_PRICE,
        ac_feeder=feeder,
    )

    kwh_charged_per_house = np.sum(np.maximum(0.0, -res.per_battery_power_kw), axis=0)
    tail_to_head_ratio = float(kwh_charged_per_house[-1] / max(1e-6, kwh_charged_per_house[0]))

    return {
        "topology": topo, "rule": rule, "battery_kw": p_kw, "droop": use_droop,
        "v_min_pu": float(res.v_min_pu.min()),
        "v_plan_viol": float(res.voltage_planning_viol.mean()),
        "v_stat_viol": float(res.voltage_statutory_viol.mean()),
        "trafo_max_pct": float(res.trafo_loading_pct.max()),
        "tail_to_head_charge_ratio": tail_to_head_ratio,
    }


def main() -> None:
    days = load_paphos_pv_days(PV_CSV, N_HOUSES)
    tasks = [
        (r, topo, spacing, rule, p, droop)
        for topo, spacing in TOPOLOGIES.items()
        for rule in ["fixed", "sdr"]
        for p in BATTERY_POWER_KW
        for droop in [False, True]
        for r in range(N_RUNS)
    ]
    rows = Parallel(n_jobs=-1, batch_size=32)(
        delayed(one_run)(r, topo, spacing, rule, p, droop, days)
        for r, topo, spacing, rule, p, droop in tqdm(tasks, desc="Droop Sweep", unit="run")
    )
    df = pd.DataFrame(rows)
    summary = df.groupby(["topology", "rule", "battery_kw", "droop"], as_index=False).mean()
    summary.to_csv(OUT / "droop_summary.csv", index=False)

    for topo in TOPOLOGIES:
        print(f"\n=== {topo} (rho = 1.0): No Droop vs EN 50549-1 Volt-Watt Droop ===")
        sub = summary[summary.topology == topo]
        print(sub.pivot(index=["rule", "battery_kw"], columns="droop",
                        values=["v_min_pu", "v_plan_viol", "tail_to_head_charge_ratio"]).round(3))


if __name__ == "__main__":
    main()