

import os
from typing import Dict

import numpy as np
import pandas as pd

DATA_DIR = "data/processed"
PROFILE_FILE = os.path.join(DATA_DIR, "uncertainty_profile_hourly.csv")
MERGED_FILE = os.path.join(DATA_DIR, "DE_merged_2025.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "battery_baseline_2025.csv")

BATTERY_CONFIG: Dict[str, float] = {
    "energy_capacity_mwh": 100.0,
    "power_capacity_mw": 25.0,
    "initial_soc_mwh": 50.0,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "time_step_hours": 1.0,
}


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


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def run_simple_battery_model() -> pd.DataFrame:
    profile = load_hourly_uncertainty_profile()
    lookup = build_uncertainty_lookup(profile)
    df = load_merged_data()

    energy_capacity = BATTERY_CONFIG["energy_capacity_mwh"]
    power_capacity = BATTERY_CONFIG["power_capacity_mw"]
    charge_eff = BATTERY_CONFIG["charge_efficiency"]
    discharge_eff = BATTERY_CONFIG["discharge_efficiency"]
    dt = BATTERY_CONFIG["time_step_hours"]

    soc = BATTERY_CONFIG["initial_soc_mwh"]

    records = []

    for _, row in df.iterrows():
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

        target_discharge_mw = clamp(risk_adjusted_net_load, 0.0, power_capacity)
        target_charge_mw = clamp(-risk_adjusted_net_load, 0.0, power_capacity)

        max_charge_from_soc = max((energy_capacity - soc) / (charge_eff * dt), 0.0)
        max_discharge_from_soc = max((soc * discharge_eff) / dt, 0.0)

        actual_charge_mw = min(target_charge_mw, max_charge_from_soc)
        actual_discharge_mw = min(target_discharge_mw, max_discharge_from_soc)

        soc_before = soc
        soc = soc + charge_eff * actual_charge_mw * dt - (actual_discharge_mw * dt) / discharge_eff
        soc = clamp(soc, 0.0, energy_capacity)

        battery_power_mw = actual_discharge_mw - actual_charge_mw
        net_load_after_battery = corrected_net_load - battery_power_mw

        records.append(
            {
                "utc_timestamp": row["utc_timestamp"],
                "hour": hour,
                "load_forecast_mw": load_fc,
                "solar_forecast_mw": solar_fc,
                "wind_onshore_forecast_mw": wind_on_fc,
                "wind_offshore_forecast_mw": wind_off_fc,
                "forecast_net_load_mw": forecast_net_load,
                "corrected_net_load_mw": corrected_net_load,
                "reserve_margin_mw": reserve_margin,
                "risk_adjusted_net_load_mw": risk_adjusted_net_load,
                "battery_charge_mw": actual_charge_mw,
                "battery_discharge_mw": actual_discharge_mw,
                "battery_power_mw": battery_power_mw,
                "soc_before_mwh": soc_before,
                "soc_after_mwh": soc,
                "net_load_after_battery_mw": net_load_after_battery,
            }
        )

    result = pd.DataFrame(records)
    result.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved battery baseline results: {OUTPUT_FILE}")
    print(result.head(12))

    return result


if __name__ == "__main__":
    run_simple_battery_model()