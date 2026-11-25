"""Battery controllers.

Every controller returns requested power in kW: < 0 charge, > 0 discharge.
Extra keyword arguments from the simulator are ignored (**_ignored).
"""
from __future__ import annotations


def tou_controller(price: float, low_threshold: float, high_threshold: float,
                   max_power_kw: float, **_ignored) -> float:
    """Charge at full power when price is low, discharge when high, else idle."""
    if price <= low_threshold:
        return -max_power_kw
    if price >= high_threshold:
        return max_power_kw
    return 0.0


def belief_neighborhood_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    feeder_load_kw: float,
    feeder_limit_kw: float,
    neighbor_avg_kw: float = 0.0,
    belief_weight: float = 0.5,
    **_ignored,
) -> float:
    """The paper's hybrid controller."""
    request = tou_controller(price, low_threshold, high_threshold, max_power_kw)
    if request >= 0.0:
        return request

    alpha = max(0.0, min(1.0, belief_weight))
    feeder_scale = max(0.0, min(1.0, 1.0 - feeder_load_kw / feeder_limit_kw))
    neighbor_pressure = max(0.0, -neighbor_avg_kw) / max_power_kw
    neighbor_scale = max(0.0, min(1.0, 1.0 - neighbor_pressure))

    return request * (alpha * feeder_scale + (1.0 - alpha) * neighbor_scale)


def volt_watt_droop_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    feeder_load_kw: float,
    feeder_limit_kw: float,
    neighbor_avg_kw: float = 0.0,
    belief_weight: float = 0.5,
    v_pu: float = 1.0,
    v_low_start: float = 0.96,
    v_low_cutoff: float = 0.95,
    v_high_start: float = 1.04,
    v_high_cutoff: float = 1.05,
    **_ignored,
) -> float:
    """Hybrid controller + local EN 50549-1 Volt-Watt droop P(V)."""
    request = belief_neighborhood_controller(
        price=price,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        max_power_kw=max_power_kw,
        feeder_load_kw=feeder_load_kw,
        feeder_limit_kw=feeder_limit_kw,
        neighbor_avg_kw=neighbor_avg_kw,
        belief_weight=belief_weight,
    )

    if request < 0.0 and v_pu < v_low_start:
        scale = max(0.0, (v_pu - v_low_cutoff) / (v_low_start - v_low_cutoff))
        return request * scale

    if request > 0.0 and v_pu > v_high_start:
        scale = max(0.0, (v_high_cutoff - v_pu) / (v_high_cutoff - v_high_start))
        return request * scale

    return request