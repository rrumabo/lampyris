"""Semele simulator: one day of a battery fleet behind one shared feeder.

Sign convention everywhere: battery power < 0 = charging, > 0 = discharging.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from semele.ac_feeder import RadialStreetFeeder
from semele.battery import Battery
from semele.network import Network
from semele.pricing import sdr_price


@dataclass
class SimulationResult:
    per_battery_power_kw:       np.ndarray  # (T, N) power of each battery
    aggregate_battery_power_kw: np.ndarray  # (T,)  sum over batteries
    feeder_net_kw:              np.ndarray  # (T,)  power drawn through the feeder (< 0 = export)
    feeder_violations:          np.ndarray  # (T,)  import OR export limit broken
    import_violations:          np.ndarray  # (T,)
    export_violations:          np.ndarray  # (T,)
    price:                      np.ndarray  # (T,)  true price announced each step
    # --- AC Power Flow Metrics (populated when ac_feeder is provided) ---
    v_min_pu:                   np.ndarray | None = None  # (T,)
    v_max_pu:                   np.ndarray | None = None  # (T,)
    voltage_planning_viol:      np.ndarray | None = None  # (T,) EAC +-5% limit
    voltage_statutory_viol:     np.ndarray | None = None  # (T,) EN 50160 +-10% limit
    trafo_loading_pct:          np.ndarray | None = None  # (T,)
    line_loading_pct:           np.ndarray | None = None  # (T,)
    thermal_overload:           np.ndarray | None = None  # (T,)


def run_simulation(
    load_profiles_kw: np.ndarray,
    prices: np.ndarray | None,
    batteries: list[Battery],
    controller,
    network: Network,
    dt_hours: float = 1.0,
    low_threshold: float = 30.0,
    high_threshold: float = 70.0,
    feeder_limit_kw: float = 60.0,
    rho_agents: float = 0.0,
    forecast_error_sigma_kw: float = 1.0,
    price_sigma: float = 0.0,
    pv_kw: np.ndarray | None = None,
    export_limit_kw: float | None = None,
    price_rule: str = "fixed",
    grid_price: float = 80.0,
    feed_in_price: float = 20.0,
    ac_feeder: RadialStreetFeeder | None = None,
) -> SimulationResult:
    n_steps, n_batteries = load_profiles_kw.shape

    if not 0.0 <= rho_agents <= 1.0:
        raise ValueError("rho_agents must be in [0, 1]")
    if price_rule not in ("fixed", "sdr"):
        raise ValueError("price_rule must be 'fixed' or 'sdr'")
    if price_rule == "fixed" and prices is None:
        raise ValueError("price_rule='fixed' needs prices")
    if price_rule == "sdr" and pv_kw is None:
        raise ValueError("price_rule='sdr' needs pv_kw")

    controllers = [controller] * n_batteries if callable(controller) else list(controller)
    pv = np.zeros(n_steps) if pv_kw is None else np.asarray(pv_kw, dtype=float)
    pv_per_house = pv / n_batteries
    export_limit = feeder_limit_kw if export_limit_kw is None else export_limit_kw

    # Correlated perception noise: sqrt(rho)*Z(t) + sqrt(1-rho)*eps_i(t).
    Z = np.random.normal(0, 1, n_steps)
    eps = np.random.normal(0, 1, (n_steps, n_batteries))
    noise = (np.sqrt(rho_agents) * Z[:, None] + np.sqrt(1 - rho_agents) * eps)
    noise *= forecast_error_sigma_kw

    power = np.zeros((n_steps, n_batteries))
    feeder_net = np.zeros(n_steps)
    price_hist = np.zeros(n_steps)
    prev_actions = np.zeros(n_batteries)
    prev_v_pu = np.ones(n_batteries)

    if ac_feeder is not None:
        v_min_arr = np.zeros(n_steps)
        v_max_arr = np.zeros(n_steps)
        v_plan_viol = np.zeros(n_steps, dtype=bool)
        v_stat_viol = np.zeros(n_steps, dtype=bool)
        trafo_load_arr = np.zeros(n_steps)
        line_load_arr = np.zeros(n_steps)
        therm_viol = np.zeros(n_steps, dtype=bool)

    for t in range(n_steps):
        load_t = load_profiles_kw[t]

        # 1. Price for this step.
        if price_rule == "fixed":
            price_t = float(prices[t])
        else:
            house_net = load_t - pv_per_house[t] - prev_actions  # > 0 imports
            supply = float(np.sum(np.maximum(0.0, -house_net)))
            demand = float(np.sum(np.maximum(0.0, house_net)))
            price_t = sdr_price(supply, demand, grid_price, feed_in_price)
        price_hist[t] = price_t

        # 2. Intra-step fixed-point loop so instantaneous inverter droop P(V) settles with AC grid V(P).
        perceived_feeder_kw = float(load_t.sum() - pv[t])
        v_iter = prev_v_pu.copy()
        n_inner = 12 if ac_feeder is not None else 1

        for _ in range(n_inner):
            requests = np.zeros(n_batteries)
            actions = np.zeros(n_batteries)
            for i, battery in enumerate(batteries):
                nbrs = network.agents[i].neighbors
                neighbor_avg_kw = float(np.mean(prev_actions[nbrs])) if nbrs else 0.0
                req = controllers[i](
                    price=price_t + float(noise[t, i]) * price_sigma,
                    low_threshold=low_threshold,
                    high_threshold=high_threshold,
                    max_power_kw=battery.max_charge_kw,
                    soc=battery.soc,
                    feeder_load_kw=perceived_feeder_kw,
                    feeder_limit_kw=feeder_limit_kw,
                    neighbor_avg_kw=neighbor_avg_kw,
                    v_pu=float(v_iter[i]),
                    agent_id=i,
                    t=t,
                )
                requests[i] = req
                # Clamp to physical power & SoC bounds without mutating battery state yet
                if req < 0.0:
                    max_in = (1.0 - battery.soc) * battery.capacity_kwh / (dt_hours * battery.charge_efficiency)
                    actions[i] = -min(-req, battery.max_charge_kw, max(0.0, max_in))
                elif req > 0.0:
                    max_out = battery.soc * battery.capacity_kwh * battery.discharge_efficiency / dt_hours
                    actions[i] = min(req, battery.max_discharge_kw, max(0.0, max_out))

            house_net_after = load_t - pv_per_house[t] - actions
            if ac_feeder is None:
                break
            ac_res = ac_feeder.step(house_net_after)
            if np.max(np.abs(ac_res["v_houses"] - v_iter)) < 1e-4:
                v_iter = ac_res["v_houses"]
                break
            v_iter = 0.5 * v_iter + 0.5 * ac_res["v_houses"]

        # 3. Apply converged requests once to update battery SoC & record feeder state.
        actions = np.array([batteries[i].apply_power(requests[i], dt_hours) for i in range(n_batteries)])
        power[t] = actions
        prev_actions = actions
        house_net_after = load_t - pv_per_house[t] - actions
        feeder_net[t] = float(house_net_after.sum())

        if ac_feeder is not None:
            ac_res = ac_feeder.step(house_net_after)
            prev_v_pu = ac_res["v_houses"]
            v_min_arr[t] = ac_res["v_min_pu"]
            v_max_arr[t] = ac_res["v_max_pu"]
            v_plan_viol[t] = ac_res["voltage_planning_viol"]
            v_stat_viol[t] = ac_res["voltage_statutory_viol"]
            trafo_load_arr[t] = ac_res["trafo_loading_pct"]
            line_load_arr[t] = ac_res["line_loading_pct"]
            therm_viol[t] = ac_res["thermal_overload"]

    import_viol = feeder_net > feeder_limit_kw
    export_viol = feeder_net < -export_limit if pv_kw is not None else np.zeros(n_steps, bool)

    return SimulationResult(
        per_battery_power_kw=power,
        aggregate_battery_power_kw=power.sum(axis=1),
        feeder_net_kw=feeder_net,
        feeder_violations=import_viol | export_viol,
        import_violations=import_viol,
        export_violations=export_viol,
        price=price_hist,
        v_min_pu=v_min_arr if ac_feeder is not None else None,
        v_max_pu=v_max_arr if ac_feeder is not None else None,
        voltage_planning_viol=v_plan_viol if ac_feeder is not None else None,
        voltage_statutory_viol=v_stat_viol if ac_feeder is not None else None,
        trafo_loading_pct=trafo_load_arr if ac_feeder is not None else None,
        line_loading_pct=line_load_arr if ac_feeder is not None else None,
        thermal_overload=therm_viol if ac_feeder is not None else None,
    )