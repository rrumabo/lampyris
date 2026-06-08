from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from src.battery import Battery


@dataclass
class SimulationResult:
    """Aggregate and per-battery outcomes from one simulation run."""

    aggregate_load_kw:           np.ndarray
    aggregate_battery_power_kw:  np.ndarray
    feeder_violations:           np.ndarray
    per_battery_curtailment_kwh: np.ndarray
    per_battery_requested_kwh:   np.ndarray
    omega_hz:                    np.ndarray


def run_simulation(
    load_profiles_kw:  np.ndarray,
    prices:            np.ndarray,
    batteries:         list[Battery],
    controller,                          # single controller OR list of controllers
    dt_hours:          float = 1.0,
    low_threshold:     float = 30.0,
    high_threshold:    float = 70.0,
    feeder_limit_kw:   float = 60.0,
    neighborhood_size: int   = 2,
    positions:         list[float] | None = None,
    position_alpha:    float = 0.5,
    M:                 float = 0.0,
    omega_nominal:     float = 50.0,
    generation_kw                = 0.0,
) -> SimulationResult:
    """
    Simulate one battery fleet under a shared or per-battery controller.

    controller: either a single callable (all batteries use the same),
                or a list of callables (one per battery, for mixed fleet).

    All other parameters unchanged from Phase 1-4.
    """

    n_steps, n_batteries = load_profiles_kw.shape

    if positions is None:
        positions = [0.0] * n_batteries

    # Normalise controller to a list — one entry per battery
    if callable(controller):
        controllers = [controller] * n_batteries
    else:
        controllers = list(controller)

    # Normalise generation to per-timestep array
    if np.isscalar(generation_kw):
        generation_array = np.full(n_steps, float(generation_kw))
    else:
        generation_array = np.asarray(generation_kw, dtype=float)

    aggregate_load          = np.zeros(n_steps)
    aggregate_battery_kw    = np.zeros(n_steps)
    feeder_violations       = np.zeros(n_steps, dtype=bool)
    per_battery_curtailment = np.zeros(n_batteries)
    per_battery_requested   = np.zeros(n_batteries)
    omega_history           = np.zeros(n_steps)

    prev_actions   = np.zeros(n_batteries)
    omega          = omega_nominal
    prev_imbalance = 0.0

    for t in range(n_steps):

        if M > 0.0:
            omega += (dt_hours / M) * prev_imbalance
            omega  = float(np.clip(omega, omega_nominal - 5.0, omega_nominal + 5.0))
        omega_history[t] = omega

        base_load_kw    = float(load_profiles_kw[t].sum())
        battery_powers: list[float] = []

        for i, battery in enumerate(batteries):

            neighbour_idx   = [(i + j) % n_batteries for j in range(1, neighborhood_size + 1)]
            neighbor_avg_kw = float(np.mean(prev_actions[neighbour_idx]))
            local_limit_kw  = feeder_limit_kw * (1.0 - positions[i] * position_alpha)

            requested_kw = controllers[i](
                price           = float(prices[t]),
                low_threshold   = low_threshold,
                high_threshold  = high_threshold,
                max_power_kw    = battery.max_charge_kw,
                soc             = battery.soc,
                feeder_load_kw  = base_load_kw,
                feeder_limit_kw = local_limit_kw,
                neighbor_avg_kw = neighbor_avg_kw,
                omega           = omega,
                omega_nominal   = omega_nominal,
            )

            actual_kw = battery.apply_power(requested_kw, dt_hours)
            battery_powers.append(actual_kw)

            price_t = float(prices[t])
            if price_t <= low_threshold:
                tou_desire_kw = -battery.max_charge_kw
            elif price_t >= high_threshold:
                tou_desire_kw = battery.max_discharge_kw
            else:
                tou_desire_kw = 0.0

            if tou_desire_kw < 0.0:
                desired_energy   = abs(tou_desire_kw) * dt_hours
                delivered_energy = max(0.0, -actual_kw) * dt_hours
                curtailed_energy = max(0.0, desired_energy - delivered_energy)
                per_battery_requested[i]   += desired_energy
                per_battery_curtailment[i] += curtailed_energy

        prev_actions     = np.array(battery_powers)
        total_battery_kw = float(sum(battery_powers))
        feeder_load_kw   = base_load_kw - total_battery_kw

        aggregate_load[t]       = feeder_load_kw
        aggregate_battery_kw[t] = total_battery_kw
        feeder_violations[t]    = feeder_load_kw > feeder_limit_kw

        prev_imbalance = float(generation_array[t]) + total_battery_kw - base_load_kw

    return SimulationResult(
        aggregate_load_kw           = aggregate_load,
        aggregate_battery_power_kw  = aggregate_battery_kw,
        feeder_violations           = feeder_violations,
        per_battery_curtailment_kwh = per_battery_curtailment,
        per_battery_requested_kwh   = per_battery_requested,
        omega_hz                    = omega_history,
    )


# ---------------------------------------------------------------------------
# Metric helpers — Phases 1–3
# ---------------------------------------------------------------------------

def compute_peak_kw(aggregate_load_kw: np.ndarray) -> float:
    return float(np.max(aggregate_load_kw))

def compute_max_ramp_kw(aggregate_load_kw: np.ndarray) -> float:
    if len(aggregate_load_kw) < 2:
        return 0.0
    return float(np.max(np.abs(np.diff(aggregate_load_kw))))

def count_feeder_violations(feeder_violations: np.ndarray) -> int:
    return int(np.sum(feeder_violations))

def compute_total_feeder_excess_kw(
    aggregate_load_kw: np.ndarray,
    feeder_limit_kw:   float,
) -> float:
    return float(np.sum(np.maximum(0.0, aggregate_load_kw - feeder_limit_kw)))


# ---------------------------------------------------------------------------
# Metric helpers — Phase 4
# ---------------------------------------------------------------------------

def compute_frequency_nadir(omega_hz: np.ndarray) -> float:
    return float(np.min(omega_hz))

def compute_frequency_peak(omega_hz: np.ndarray) -> float:
    return float(np.max(omega_hz))

def compute_frequency_recovery_time(
    omega_hz:      np.ndarray,
    omega_nominal: float = 50.0,
    tolerance:     float = 0.1,
    dt_hours:      float = 1.0,
) -> float:
    recovered = np.where(np.abs(omega_hz - omega_nominal) <= tolerance)[0]
    if len(recovered) == 0:
        return float(len(omega_hz)) * dt_hours
    return float(recovered[0]) * dt_hours

def compute_frequency_std(omega_hz: np.ndarray) -> float:
    return float(np.std(omega_hz))