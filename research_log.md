Phase 1:
Finding: local rationality does not scale.
Mechanism: synchronized TOU charging creates feeder peaks
no individual battery intended.
Soft coordination reshapes failure rather than eliminating it.
Regime matters — no single controller dominates across all conditions.

Phase 2 — information gradient:
Finding: information type matters more than quantity.
Neighborhood (lagged peer signals) → zero benefit at every scale.
Local (own SoC) → ~25% peak reduction, weakens under stochastic prices.
Global (feeder load) → robust, strengthens under stochastic prices.
Reason: direct measurement of the variable you care about
outperforms indirect inference regardless of how much you share.

Phase 3 — fairness_sweep :
Finding: optimal aggregate outcomes do not imply fair distribution.
Same battery, same desire, only position differs.
End-of-line bears 3.4× its fair share of curtailment.
Hard regime: end-of-line batteries charged nothing.
No malice. Pure mechanism.

Note on scope:
This simulation is complex but tractable — deterministic agents,
smooth controllers, reproducible results.
Adaptive and memory-based agents are deliberately excluded.
Sensitivity to initial conditions and attractor identification
are open questions for future work.

Phase 4 — Part 1: frequency_sweep
Question: what is the stability boundary in M × droop_gain space?
Method: sweep M=[6-50] × droop_gain=[0.5-10].
Finding: stability condition is approximately M/droop_gain ≥ 5.
Below this ratio: frequency diverges (hits ±5 Hz clamp).
Above this ratio: frequency deviation stays within 1 Hz of nominal.
Best stable config: M=50, droop=2 → std=0.053 Hz.

Phase 4 — Part 2:
M=0 with droop is not well defined — division by zero in the swing equation.
Droop requires inertia to exist. They are not alternatives.

Phase 4 — disturbance sweep:
Stability boundary robust: droop ≤ 2 stable at M=10
regardless of disturbance size (5–25 kW).
Optimal droop: 1.0 — consistently lowest frequency std.
Timing matters: earlier disturbance → worse nadir,
independent of disturbance size.
Anomaly: disturbance=20 kW at t11 pushed droop=0.5
to near-instability (nadir=45.07 Hz).
New variable identified: drop timing interacts with droop gain.

Phase 5 — Mixed fleet:
Stability threshold: 60% droop fraction (6/10 batteries).
Near-source-first = random assignment — both stabilize at 60%.
End-of-line-first needs 70% — position matters at the margin.
Frequency is a global signal — droop effectiveness is
position-independent, unlike curtailment burden (Phase 3).
std improvement is smooth — each additional droop agent helps equally.

Phase 6 A — topology sweep:
Expected: disorder → order as k increases (Kuramoto-style).
Found: quasi-order → brief sync window → polarization.

Sync window:
  small_world: k=[0.05, 0.21], max 90% of runs
  linear:      k=[0.05, 0.41], max 75% of runs
  star:        never syncs

Polarization onset:
  small_world: k>0.31 (faster due to shortcuts)
  linear:      k>0.46
  star:        never — hub mediation prevents extremes

Finding: small-world accelerates BOTH synchronization AND polarization.
Shortcuts are a double-edged sword.

Phase 6 B — heterogeneous k:
Leader emergence confirmed: corr(k_i, |x_i|) = 0.84-0.86 for bimodal.
Agents with k∈[1.0,1.5] reach |x|≈1.0, followers partially dragged.

Small-world: best for homogeneous k (sync=70%),
             worst for heterogeneous (complete collapse).
Star: most robust — hub dampens leader influence.

Key finding: topology determines HOW leaders affect the system,
not WHETHER leaders exist.

Phase 7b — feeder_failure sweep: belief_neighborhood_controller
Question:
At what rho does synchronised charging cause feeder overload — and
how large is the protection window between collapse and failure?
Setup:
10 batteries
belief_neighborhood_controller
feeder_limit_kw = 60.0
price_sigma = 20.0
rho_agents swept 0 to 1
40 rho points, 20 runs per point
4 topologies
Baseline violations at rho=0: 0.01–0.03 (clean)
Finding — rho_c and protection windows:
  topology      rho_c_sync  rho_c_failure  window
  small_world   0.282       0.487          0.205
  linear        0.308       0.359          0.051
  legacy_ring   0.333       0.462          0.128
  star          0.410       0.590          0.179
Key findings:
Collapse onset and feeder failure are independent properties.
Small_world collapses earliest but has the largest protection window.
Linear collapses second but has the smallest protection window.
Spectral conjecture falsified: lambda_2 does not predict rho_c.
Local degree structure and information aggregation govern rho_c,
not global spectral mixing rate.
Delay-but-amplify pattern confirmed: topologies with higher rho_c
collapse more steeply once triggered (star slope 1.22, legacy_ring 0.76).