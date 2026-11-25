"""
Theory-experiment bridge check.

The analytic argument (Lemma: orthogonality of common signal and topology)
predicts that the correlated forecast error projects ENTIRELY onto the
consensus mode v_1 = 1/sqrt(N) - the uniform vector. So at high rho, the
dominant SVD spatial mode u1 should be approximately UNIFORM across agents.

This script verifies that empirically. If u1 is near uniform at high rho, the
theory's central claim is confirmed directly. If u1 has structure, the linear
argument is missing something (likely controller saturation).

Metric: coefficient of variation (CV) of |u1| across agents.
    CV -> 0   : u1 is uniform  -> consensus mode -> theory confirmed
    CV large  : u1 has structure -> not pure consensus

We compare u1 WITHOUT subtracting the mean (subtract_mean=False), because we
want to see the common mode, not remove it.
"""

from __future__ import annotations
import functools
import numpy as np

from experiments.reproduce_core_result import (
    make_cyprus_style_pv_profile,
    make_price_signal,
    make_load_profiles,
    make_batteries,
    build_topologies,
    N_STEPS,
    N_BATTERIES,
    DT_HOURS,
    PV_PEAK_KW,
    FEEDER_LIMIT_KW,
    LOW_PRICE,
    HIGH_PRICE,
    FORECAST_ERROR_SIGMA_KW,
    PRICE_SIGMA,
)
from semele.controllers import belief_neighborhood_controller
from semele.simulator import run_simulation
from experiments.spectral_diagnostics import spectral_diagnostics


SEED = 42
# rho values to inspect: low (topology ish), mid, high (should be consensus).
RHO_PROBE = [0.0, 0.5, 0.85, 1.0]
BELIEF_WEIGHT = 0.5

_PV = make_cyprus_style_pv_profile(n_steps=N_STEPS, pv_peak_kw=PV_PEAK_KW)
_PRICES = make_price_signal(_PV)
_LOAD = make_load_profiles(rng=np.random.default_rng(SEED),
                           n_steps=N_STEPS, n_batteries=N_BATTERIES)


def u1_for(topology_factory, rho):
    controller = functools.partial(
        belief_neighborhood_controller, belief_weight=BELIEF_WEIGHT,
    )
    batteries = make_batteries(rng=np.random.default_rng(SEED), n_batteries=N_BATTERIES)
    network = topology_factory()
    np.random.seed(SEED)
    result = run_simulation(
        load_profiles_kw=_LOAD, prices=_PRICES, batteries=batteries,
        controller=controller, dt_hours=DT_HOURS,
        low_threshold=LOW_PRICE, high_threshold=HIGH_PRICE,
        feeder_limit_kw=FEEDER_LIMIT_KW, rho_agents=float(rho),
        forecast_error_sigma_kw=FORECAST_ERROR_SIGMA_KW, price_sigma=PRICE_SIGMA,
        network=network,
    )
    # subtract_mean=False so u1 reflects the actual dominant spatial mode,
    # including the common component.
    w1, PR, u1 = spectral_diagnostics(result.per_battery_power_kw, subtract_mean=False)
    return w1, PR, np.asarray(u1)


def uniformity(u1):
    """
    How close is u1 to uniform? Use |u1| (sign is arbitrary in SVD).
    CV = std/mean of |u1|. Uniform vector has CV = 0.
    Also report cosine similarity to the all-ones direction.
    """
    a = np.abs(u1)
    cv = float(a.std() / a.mean()) if a.mean() > 0 else float("nan")
    ones = np.ones_like(u1) / np.sqrt(len(u1))
    cos = float(abs(np.dot(u1, ones)) / (np.linalg.norm(u1) + 1e-12))
    return cv, cos


def main() -> None:
    topologies = build_topologies()
    print("Consensus-mode check: is the dominant SVD mode u1 uniform at high rho?")
    print("CV(|u1|) -> 0 and cos(u1, 1) -> 1 mean u1 = consensus vector "
          "= theory confirmed.\n")

    for name, factory in topologies.items():
        print(f"--- topology: {name} ---")
        print(f"  {'rho':>5}  {'w1':>6}  {'PR':>6}  {'CV(|u1|)':>9}  {'cos(u1,1)':>9}")
        for rho in RHO_PROBE:
            w1, PR, u1 = u1_for(factory, rho)
            cv, cos = uniformity(u1)
            print(f"  {rho:5.2f}  {w1:6.3f}  {PR:6.2f}  {cv:9.3f}  {cos:9.3f}")
        print()

    print("Reading:")
    print("  As rho rises, expect w1 -> ~1, PR -> ~1, CV -> small, cos -> ~1.")
    print("  cos(u1, 1) near 1 at high rho is the direct confirmation that the")
    print("  common signal drives the consensus mode, exactly as the Lemma predicts.")


if __name__ == "__main__":
    main()