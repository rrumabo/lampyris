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