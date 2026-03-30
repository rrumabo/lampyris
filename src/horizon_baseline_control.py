import os
from typing import Dict, List, Tuple

import pandas as pd

DATA_DIR = "data/processed"
PROFILE_FILE = os.path.join(DATA_DIR, "uncertainty_profile_hourly.csv")
MERGED_FILE = os.path.join(DATA_DIR, "DE_merged_2025.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "horizon_baseline_2025.csv")

BATTERY_CONFIG: Dict[str, float] = {
    "energy_capacity_mwh": 100.0,
    "power_capacity_mw": 25.0,
    "initial_soc_mwh": 50.0,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "time_step_hours": 1.0,
}

HORIZON_HOURS = 24


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def load_hourly_uncertainty_profile() -> pd.DataFrame:
    if not os.path.exists(PROFILE_FILE):
        raise FileNotFoundError(
            f"Missing uncertainty profile file: {PROFILE_FILE}. Run build_uncertainty_profiles.py first."
        )

    profile = pd.read_csv(PROFILE_FILE)
    required = {"variable", "hour", "mean_error", "std_error"}
    missing = required.difference(profile.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns in uncertainty profile: {missing_str}")

    return profile[["variable", "hour", "mean_error", "std_error"]].copy()


def build_uncertainty_lookup(profile: pd.DataFrame) -> Dict[str, Dict[int, Dict[str, float]]]:
    lookup: Dict[str, Dict[int, Dict[str, float]]] = {}

    for _, row in profile.iterrows():
        variable = str(row["variable"])
        hour = int(row["hour"])
        mean_error = float(row["mean_error"])
        std_error = float(row["std_error"])

        if variable not in lookup:
            lookup[variable] = {}

        lookup[variable][hour] = {
            "mean_error": mean_error,
            "std_error": std_error,
        }

    return lookup


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

    return df.copy()


def compute_hourly_quantities(row: pd.Series, lookup: Dict[str, Dict[int, Dict[str, float]]]) -> Dict[str, float]:
    hour = int(row["hour"])

    load_fc = float(row["DE_load_forecast"])
    solar_fc = float(row["DE_solar_forecast"])
    wind_on_fc = float(row["DE_wind_onshore_forecast"])
    wind_off_fc = float(row["DE_wind_offshore_forecast"])

    load_mean = lookup["load"][hour]["mean_error"]
    load_std = lookup["load"][hour]["std_error"]

    solar_mean = lookup["solar"][hour]["mean_error"]
    solar_std = lookup["solar"][hour]["std_error"]

    wind_on_mean = lookup["wind_onshore"][hour]["mean_error"]
    wind_on_std = lookup["wind_onshore"][hour]["std_error"]

    wind_off_mean = lookup["wind_offshore"][hour]["mean_error"]
    wind_off_std = lookup["wind_offshore"][hour]["std_error"]

    corrected_load = load_fc + load_mean
    corrected_solar = solar_fc + solar_mean
    corrected_wind_on = wind_on_fc + wind_on_mean
    corrected_wind_off = wind_off_fc + wind_off_mean

    renewable_uncertainty = solar_std + wind_on_std + wind_off_std
    demand_uncertainty = load_std
    reserve_margin = demand_uncertainty + renewable_uncertainty

    forecast_net_load = load_fc - solar_fc - wind_on_fc - wind_off_fc
    corrected_net_load = corrected_load - corrected_solar - corrected_wind_on - corrected_wind_off
    risk_adjusted_net_load = corrected_net_load + reserve_margin

    return {
        "load_forecast_mw": load_fc,
        "solar_forecast_mw": solar_fc,
        "wind_onshore_forecast_mw": wind_on_fc,
        "wind_offshore_forecast_mw": wind_off_fc,
        "forecast_net_load_mw": forecast_net_load,
        "corrected_net_load_mw": corrected_net_load,
        "reserve_margin_mw": reserve_margin,
        "risk_adjusted_net_load_mw": risk_adjusted_net_load,
    }


def simulate_battery_step(
    soc_before: float,
    requested_power_mw: float,
    config: Dict[str, float],
) -> Tuple[float, float, float, float]:
    energy_capacity = config["energy_capacity_mwh"]
    power_capacity = config["power_capacity_mw"]
    charge_eff = config["charge_efficiency"]
    discharge_eff = config["discharge_efficiency"]
    dt = config["time_step_hours"]

    power_request = clamp(requested_power_mw, -power_capacity, power_capacity)

    if power_request >= 0.0:
        max_discharge_from_soc = max((soc_before * discharge_eff) / dt, 0.0)
        actual_discharge_mw = min(power_request, max_discharge_from_soc)
        actual_charge_mw = 0.0
    else:
        requested_charge_mw = abs(power_request)
        max_charge_from_soc = max((energy_capacity - soc_before) / (charge_eff * dt), 0.0)
        actual_charge_mw = min(requested_charge_mw, max_charge_from_soc)
        actual_discharge_mw = 0.0

    soc_after = soc_before + charge_eff * actual_charge_mw * dt - (actual_discharge_mw * dt) / discharge_eff
    soc_after = clamp(soc_after, 0.0, energy_capacity)

    battery_power_mw = actual_discharge_mw - actual_charge_mw
    return actual_charge_mw, actual_discharge_mw, battery_power_mw, soc_after


def choose_horizon_action(
    df: pd.DataFrame,
    start_idx: int,
    soc_now: float,
    lookup: Dict[str, Dict[int, Dict[str, float]]],
) -> Tuple[float, Dict[str, float]]:
    end_idx = min(start_idx + HORIZON_HOURS, len(df))
    horizon = df.iloc[start_idx:end_idx]

    avg_risk_adjusted_net_load = 0.0
    avg_reserve_margin = 0.0
    steps = 0

    first_step_quantities: Dict[str, float] | None = None

    for step_idx, (_, row) in enumerate(horizon.iterrows()):
        quantities = compute_hourly_quantities(row, lookup)
        avg_risk_adjusted_net_load += quantities["risk_adjusted_net_load_mw"]
        avg_reserve_margin += quantities["reserve_margin_mw"]
        steps += 1

        if step_idx == 0:
            first_step_quantities = quantities

    if steps == 0 or first_step_quantities is None:
        raise ValueError("Empty horizon encountered in choose_horizon_action")

    avg_risk_adjusted_net_load /= steps
    avg_reserve_margin /= steps

    energy_capacity = BATTERY_CONFIG["energy_capacity_mwh"]
    power_capacity = BATTERY_CONFIG["power_capacity_mw"]
    soc_midpoint = 0.5 * energy_capacity
    soc_deviation = soc_now - soc_midpoint
    soc_fraction = soc_now / energy_capacity

    horizon_margin = max(avg_reserve_margin, 1.0)

    absolute_signal = (
        first_step_quantities["risk_adjusted_net_load_mw"] / horizon_margin
    )

    deviation_from_horizon = (
        first_step_quantities["risk_adjusted_net_load_mw"]
        - avg_risk_adjusted_net_load
    )
    deviation_signal = deviation_from_horizon / horizon_margin

    soc_signal = soc_deviation / soc_midpoint

    # Mixed horizon baseline:
    # - absolute signal captures real system stress
    # - deviation signal captures whether now is worse than nearby hours
    # - SOC signal discourages living at the edges
    score = (
        0.35 * absolute_signal
        + 0.45 * deviation_signal
        + 0.20 * soc_signal
    )

    score = clamp(score, -1.0, 1.0)
    chosen_power_mw = power_capacity * score

    # Soft SOC guard near the boundaries.
    if soc_fraction < 0.15 and chosen_power_mw > 0.0:
        chosen_power_mw *= soc_fraction / 0.15

    if soc_fraction > 0.85 and chosen_power_mw < 0.0:
        chosen_power_mw *= (1.0 - soc_fraction) / 0.15
    return chosen_power_mw, first_step_quantities


def run_horizon_baseline_control() -> pd.DataFrame:
    profile = load_hourly_uncertainty_profile()
    lookup = build_uncertainty_lookup(profile)
    df = load_merged_data()

    soc = BATTERY_CONFIG["initial_soc_mwh"]
    records: List[Dict[str, float | int | str | pd.Timestamp]] = []

    for idx, row in enumerate(df.itertuples(index=False), start=0):
        chosen_power_mw, quantities = choose_horizon_action(df, idx, soc, lookup)

        soc_before = soc
        battery_charge_mw, battery_discharge_mw, battery_power_mw, soc = simulate_battery_step(
            soc_before=soc_before,
            requested_power_mw=chosen_power_mw,
            config=BATTERY_CONFIG,
        )

        hour_py: int = int()

        net_load_after_battery = quantities["corrected_net_load_mw"] - battery_power_mw

        records.append(
            {
                "utc_timestamp": row.utc_timestamp,
                "hour": hour_py,
                "horizon_hours": HORIZON_HOURS,
                "chosen_power_request_mw": chosen_power_mw,
                "load_forecast_mw": quantities["load_forecast_mw"],
                "solar_forecast_mw": quantities["solar_forecast_mw"],
                "wind_onshore_forecast_mw": quantities["wind_onshore_forecast_mw"],
                "wind_offshore_forecast_mw": quantities["wind_offshore_forecast_mw"],
                "forecast_net_load_mw": quantities["forecast_net_load_mw"],
                "corrected_net_load_mw": quantities["corrected_net_load_mw"],
                "reserve_margin_mw": quantities["reserve_margin_mw"],
                "risk_adjusted_net_load_mw": quantities["risk_adjusted_net_load_mw"],
                "battery_charge_mw": battery_charge_mw,
                "battery_discharge_mw": battery_discharge_mw,
                "battery_power_mw": battery_power_mw,
                "soc_before_mwh": soc_before,
                "soc_after_mwh": soc,
                "net_load_after_battery_mw": net_load_after_battery,
            }
        )

    result = pd.DataFrame(records)
    result.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved horizon baseline results: {OUTPUT_FILE}")
    print(result.head(12))

    return result


if __name__ == "__main__":
    run_horizon_baseline_control()