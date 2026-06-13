from __future__ import annotations
from typing import List
import random

#-------------------------------------------------
# CONTROLLER IDEA:
# Controllers decide what the battery should do.
# Battery decides what CAN be actually possible.
#--------------------------------------------------

def tou_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    **_ignored,
) -> float:
    """
    Simple Time-of-Use controller.

    - Charge when price is low
    - Discharge when price is high
    - Otherwise do nothing

    Returns requested power (kW):
        negative = charge
        positive = discharge
    """

    if price <= low_threshold:
        return -max_power_kw  # charge

    if price >= high_threshold:
        return max_power_kw  # discharge

    return 0.0


# -------------------------------------------------
# RANDOMIZED CONTROLLER (for coordination test)
# -------------------------------------------------

def randomized_tou_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    randomness: float,
    **_ignored,
) -> float:
    """
    Same as TOU but introduces randomness to avoid synchronization.
    randomness: value in [0,1] controlling probability of acting.
    """

    if random.random() > randomness:
        return 0.0

    return tou_controller(
        price=price,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        max_power_kw=max_power_kw,
    )

# -------------------------------------------------
# FEEDER-AWARE CAP CONTROLLER
# -------------------------------------------------

def capped_controller(requested_kw: float, feeder_load_kw: float, feeder_limit_kw: float) -> float:
    """
    Caps battery action if feeder is close to limit.

    This is a VERY simple coordination rule.
    """

    if feeder_load_kw >= feeder_limit_kw:
        return 0.0

    return requested_kw

# -------------------------------------------------
# TOU + CAP COORDINATION
# -------------------------------------------------


def capped_tou_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    feeder_load_kw: float,
    feeder_limit_kw: float,
    **_ignored,
) -> float:
    """
    First request a standard TOU action, then cap it using feeder stress.
    """

    requested_kw = tou_controller(
        price=price,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        max_power_kw=max_power_kw,
    )

    return capped_controller(
        requested_kw=requested_kw,
        feeder_load_kw=feeder_load_kw,
        feeder_limit_kw=feeder_limit_kw,
    )

# -------------------------------------------------
# SOFT (PROPORTIONAL) CAP CONTROLLER
# -------------------------------------------------

def soft_capped_tou_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    feeder_load_kw: float,
    feeder_limit_kw: float,
    softness: float = 0.3,
    **_ignored,
) -> float:
    """
    Proportional (soft) coordination:

    - Start from TOU request
    - Gradually scale action down as feeder approaches the limit

    softness: fraction of the feeder limit that defines the transition band
              (e.g., 0.3 means start reducing at 70% of the limit)
    """

    # Base request from TOU
    requested_kw = tou_controller(
        price=price,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        max_power_kw=max_power_kw,
    )

    # Define a linear scaling region
    start_reduce = feeder_limit_kw * (1.0 - softness)

    if feeder_load_kw <= start_reduce:
        # Plenty of margin: allow full action
        return requested_kw

    if feeder_load_kw >= feeder_limit_kw:
        # At/above limit: block action that worsens the situation
        # (allow discharge if it helps reduce load, block charging)
        return max(requested_kw, 0.0)

    # Between start_reduce and feeder_limit: scale linearly from 1 → 0
    margin = feeder_limit_kw - feeder_load_kw
    band = feeder_limit_kw - start_reduce  # = feeder_limit_kw * softness
    scale = max(0.0, min(1.0, margin / band))

    return requested_kw * scale

# -------------------------------------------------
# AGGREGATION HELPER (optional)
# -------------------------------------------------

def aggregate_requests(requests: List[float]) -> float:
    """
    Sum of all battery requested powers.
    """

    return sum(requests)

# -------------------------------------------------
# LOCAL-AWARE CONTROLLER  (information level: local)
# -------------------------------------------------
 
def local_aware_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    soc: float = 0.5,
    **_ignored,
) -> float:
    """
    TOU controller that scales aggressiveness based on own SoC.
 
    No feeder awareness. No neighbour awareness.
    The only extra information is the agent's own state.
 
    Charging:    scale by available room  (1 - soc).  Near-full  → charge softly.
    Discharging: scale by available energy (soc).     Near-empty → discharge softly.
    """
    base_request = tou_controller(price, low_threshold, high_threshold, max_power_kw)
 
    if base_request < 0.0:          # charging request
        return base_request * (1.0 - soc)
 
    if base_request > 0.0:          # discharging request
        return base_request * soc
 
    return 0.0
 
 
# -------------------------------------------------
# NEIGHBOURHOOD CONTROLLER  (information level: neighborhood)
# -------------------------------------------------
 
def neighborhood_controller(
    price: float,
    low_threshold: float,
    high_threshold: float,
    max_power_kw: float,
    neighbor_avg_kw: float = 0.0,
    **_ignored,
) -> float:
    """
    TOU controller that scales back when neighbours are charging.
 
    No direct feeder visibility.
    The only system signal is neighbours' average power from the previous timestep.
 
    If neighbours charged hard last step → scale back own charge this step.
    Scale: 1.0 when neighbours were idle, 0.0 when neighbours charged at full power.
 
    Discharge behaviour is unchanged — only charging is modulated.
    """
    base_request = tou_controller(price, low_threshold, high_threshold, max_power_kw)
 
    # Only modulate charging (charging is what creates feeder stress).
    if base_request >= 0.0:
        return base_request
 
    # How hard were neighbours charging? (negative avg → charging)
    neighbour_charge_pressure = max(0.0, -neighbor_avg_kw) / max_power_kw
    scale = max(0.0, 1.0 - neighbour_charge_pressure)
 
    return base_request * scale
 

# -------------------------------------------------
# BELIEF + NEIGHBOURHOOD HYBRID CONTROLLER
# -------------------------------------------------

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
    """
    Hybrid controller using two information channels.

    feeder_load_kw:
        Perceived feeder stress. This is where rho_agents enters through
        correlated belief noise in the simulator.

    neighbor_avg_kw:
        Observed average neighbour action from the previous timestep. This is
        where network topology enters.

    belief_weight:
        Fixed at 0.5 by default for the first rho/topology sweep.
        1.0 means trust only feeder belief.
        0.0 means trust only neighbour observation.

    Sign convention:
        negative = charge
        positive = discharge

    The hybrid only scales charging. Discharge is allowed because it helps
    relieve feeder stress.
    """
    base_request = tou_controller(
        price=price,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        max_power_kw=max_power_kw,
    )

    # Idle or discharging: do not suppress helpful action.
    if base_request >= 0.0:
        return base_request

    belief_weight = max(0.0, min(1.0, belief_weight))

    # Belief signal: if perceived feeder load is near/above limit, reduce charge.
    feeder_scale = max(0.0, min(1.0, 1.0 - feeder_load_kw / feeder_limit_kw))

    # Topology signal: if neighbours charged hard last step, reduce charge.
    neighbor_pressure = max(0.0, -neighbor_avg_kw) / max_power_kw
    neighbor_scale = max(0.0, min(1.0, 1.0 - neighbor_pressure))

    scale = belief_weight * feeder_scale + (1.0 - belief_weight) * neighbor_scale

    return base_request * scale

# -------------------------------------------------
# DROOP CONTROLLER (Phase 4 — frequency response)
# -------------------------------------------------

def droop_controller(
    omega: float = 50.0,
    omega_nominal: float = 50.0,
    droop_gain: float = 1.0,
    max_power_kw: float = 10.0,
    **_ignored,
) -> float:
    """
    Responds to frequency deviation.

    When frequency drops below nominal → discharge (positive power).
    When frequency rises above nominal → charge (negative power).
    Response is proportional to deviation, clipped to max power.

    droop_gain: how aggressively the battery responds.
                higher = faster response = more synthetic inertia.
    """
    delta_omega = omega - omega_nominal
    requested_kw = -droop_gain * delta_omega
    return float(max(-max_power_kw, min(requested_kw, max_power_kw)))