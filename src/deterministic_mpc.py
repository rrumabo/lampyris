import os
from typing import Any, Dict, List, cast

import cvxpy as cp
from cvxpy.constraints.constraint import Constraint
import numpy as np
import pandas as pd

DATA_DIR = "data/processed"
MERGED_FILE = os.path.join(DATA_DIR, "DE_merged_2025.csv")

BATTERY_CONFIG: Dict[str, float] = {
    "energy_capacity_mwh": 100.0,
    "power_capacity_mw": 25.0,
    "initial_soc_mwh": 50.0,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "time_step_hours": 1.0,
}

HORIZON_HOURS = 24

MPC_MODE = "conservative"  

WEIGHT_PRESETS = {
    "aggressive": {
        "W_NET": 1.0,
        "W_POWER": 0.0005,
        "W_SOC": 0.0005,
        "W_THROUGHPUT": 0.00005,
    },
    "balanced": {
        "W_NET": 1.0,
        "W_POWER": 0.005,
        "W_SOC": 0.005,
        "W_THROUGHPUT": 0.0005,
    },
    "conservative": {
        "W_NET": 1.0,
        "W_POWER": 0.05,
        "W_SOC": 0.05,
        "W_THROUGHPUT": 0.005,
    },
}

W_NET = WEIGHT_PRESETS[MPC_MODE]["W_NET"]
W_POWER = WEIGHT_PRESETS[MPC_MODE]["W_POWER"]
W_SOC = WEIGHT_PRESETS[MPC_MODE]["W_SOC"]
W_THROUGHPUT = WEIGHT_PRESETS[MPC_MODE]["W_THROUGHPUT"]

OUTPUT_FILE = os.path.join(DATA_DIR, f"deterministic_mpc_{MPC_MODE}_2025.csv")

def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def load_merged_data() -> pd.DataFrame:
    if not os.path.exists(MERGED_FILE):
        raise FileNotFoundError(
            f"Missing merged file: {MERGED_FILE}. Run merge_actuals_forecasts.py first."
        )

    df = pd.read_csv(MERGED_FILE, parse_dates=["utc_timestamp"])
    df["utc_timestamp"] = pd.to_datetime(df["utc_timestamp"], utc=True).dt.tz_convert("Europe/Berlin")
    df["hour"] = df["utc_timestamp"].dt.hour

    required_columns = {
        "utc_timestamp",
        "hour",
        "DE_load_forecast",
        "DE_solar_forecast",
        "DE_wind_onshore_forecast",
        "DE_wind_offshore_forecast",
    }
    missing = required_columns.difference(df.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns in merged data: {missing_str}")

    df["forecast_net_load_mw"] = (
        df["DE_load_forecast"]
        - df["DE_solar_forecast"]
        - df["DE_wind_onshore_forecast"]
        - df["DE_wind_offshore_forecast"]
    )

    return df.copy()


def solve_mpc_step(
    forecast_net_load: np.ndarray,
    soc_now: float,
    config: Dict[str, float],
    n_ref: float,
) -> Dict[str, np.ndarray | float]:
    horizon = forecast_net_load.shape[0]

    e_max = config["energy_capacity_mwh"]
    p_max = config["power_capacity_mw"]
    eta_ch = config["charge_efficiency"]
    eta_dis = config["discharge_efficiency"]
    dt = config["time_step_hours"]
    soc_mid = 0.5 * e_max

    p_ch = cp.Variable(horizon, nonneg=True)
    p_dis = cp.Variable(horizon, nonneg=True)
    soc = cp.Variable(horizon + 1)

    constraints: list[Constraint] = [soc[0] == soc_now]

    for t in range(horizon):
        constraints.extend(
            [
                soc[t + 1] == soc[t] + eta_ch * p_ch[t] * dt - (p_dis[t] * dt) / eta_dis,
                soc[t + 1] >= 0.0,
                soc[t + 1] <= e_max,
                p_ch[t] <= p_max,
                p_dis[t] <= p_max,
            ]
        )

    net_after_battery = forecast_net_load - (p_dis - p_ch)

    objective = cp.Minimize(
        cp.sum(
            W_NET * cp.square(net_after_battery / n_ref)
            + W_POWER * cp.square((p_dis - p_ch) / p_max)
            + W_SOC * cp.square((soc[1:] - soc_mid) / soc_mid)
            + W_THROUGHPUT * (cp.square(p_ch / p_max) + cp.square(p_dis / p_max))
        )
    )

    problem = cp.Problem(objective, constraints)
    problem.solve(solver=cp.OSQP, warm_start=True, verbose=False)
    objective_value = problem.value

    if problem.status not in {"optimal", "optimal_inaccurate"}:
        raise ValueError(f"MPC solve failed with status: {problem.status}")

    if objective_value is None:
        raise ValueError("MPC solve returned no objective value")

    return {
        "p_ch": np.asarray(p_ch.value).reshape(-1),
        "p_dis": np.asarray(p_dis.value).reshape(-1),
        "soc": np.asarray(soc.value).reshape(-1),
        "net_after_battery": np.asarray(net_after_battery.value).reshape(-1),
        "objective_value": float(cast(float, objective_value)),
    }


def run_deterministic_mpc() -> pd.DataFrame:
    df = load_merged_data()

    n_ref = max(float(df["forecast_net_load_mw"].abs().quantile(0.95)), 1.0)
    soc = BATTERY_CONFIG["initial_soc_mwh"]

    records: List[Dict[str, float | int | str | pd.Timestamp]] = []

    for idx, row in enumerate(df.itertuples(index=False), start=0):
        end_idx = min(idx + HORIZON_HOURS, len(df))
        horizon_df = df.iloc[idx:end_idx]
        forecast_net_load = horizon_df["forecast_net_load_mw"].to_numpy(dtype=float)

        solution = solve_mpc_step(
            forecast_net_load=forecast_net_load,
            soc_now=soc,
            config=BATTERY_CONFIG,
            n_ref=n_ref,
        )

        # Ensure solution entries are array-like even if they are returned as scalars
        p_ch_arr = np.asarray(solution["p_ch"]).reshape(-1)
        p_dis_arr = np.asarray(solution["p_dis"]).reshape(-1)
        soc_arr = np.asarray(solution["soc"]).reshape(-1)

        p_ch_0 = float(p_ch_arr[0])
        p_dis_0 = float(p_dis_arr[0])
        battery_power_0 = p_dis_0 - p_ch_0

        soc_before = soc
        # take the next SOC state if available, otherwise fall back to the only value
        soc = float(soc_arr[1]) if len(soc_arr) > 1 else float(soc_arr[0])

        forecast_net_load_0: float = float(cast(float, row.forecast_net_load_mw))
        load_fc_0: float = float(cast(float, row.DE_load_forecast))
        solar_fc_0: float = float(cast(float, row.DE_solar_forecast))
        wind_on_fc_0: float = float(cast(float, row.DE_wind_onshore_forecast))
        wind_off_fc_0: float = float(cast(float, row.DE_wind_offshore_forecast))
        objective_value_0: float = float(cast(float, solution["objective_value"]))
        net_after_battery_0 = forecast_net_load_0 - battery_power_0

        hour_value = cast(int, row.hour)
        hour_py: int = int(hour_value)

        utc_timestamp_0: pd.Timestamp = cast(pd.Timestamp, row.utc_timestamp)
        record: Dict[str, float | int | str | pd.Timestamp] = {
            "utc_timestamp": utc_timestamp_0,
            "hour": hour_py,
            "horizon_hours": HORIZON_HOURS,
            "objective_value": objective_value_0,
            "load_forecast_mw": load_fc_0,
            "solar_forecast_mw": solar_fc_0,
            "wind_onshore_forecast_mw": wind_on_fc_0,
            "wind_offshore_forecast_mw": wind_off_fc_0,
            "forecast_net_load_mw": forecast_net_load_0,
            "battery_charge_mw": p_ch_0,
            "battery_discharge_mw": p_dis_0,
            "battery_power_mw": battery_power_0,
            "soc_before_mwh": soc_before,
            "soc_after_mwh": soc,
            "net_load_after_battery_mw": net_after_battery_0,
        }
        records.append(record)

    result = pd.DataFrame(records)
    result.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved deterministic MPC results: {OUTPUT_FILE}")
    print(result.head(12))

    return result


if __name__ == "__main__":
    run_deterministic_mpc()