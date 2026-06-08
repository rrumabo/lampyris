# Battery Coordination Sandbox

## What this is

A simulation study of how multiple batteries sharing a feeder create aggregate behavior that no individual battery intended.

The central question:

> When many batteries follow simple local rules, what happens to the grid?

This is not a grid tool. It is an experimental sandbox for studying coordination failure.

---

## What Phase 1 showed

Four controllers were compared across multiple system regimes (light, medium, hard feeder stress):

- **TOU** — naive local dispatch. Causes strong synchronization and the worst feeder peaks.
- **Randomized TOU** — breaks synchronization partially, but effect is fragile and regime-dependent.
- **Hard Capped TOU** — suppresses overloads abruptly. Best for peak and ramp in hard regimes, but rigid.
- **Soft Capped TOU** — scales battery response continuously with feeder stress. Most balanced overall.

### Key findings

1. Local rationality does not scale. Rules that seem harmless for one battery can be harmful for many.
2. Controller performance is regime-dependent. No single strategy dominates across all conditions.
3. Soft coordination outperforms randomization because its parameter has structured, predictable effects.
4. In hard regimes, simple controllers do not eliminate failure — they reshape how the system fails.
5. Violation count is a misleading metric. Total excess is more informative under stress.

---

## What Phase 2 showed

**Question:** How much information does an agent need before its local behavior stops being harmful?

Four information levels were tested, each mapped to a controller:

- **None** — price signal only (TOU)
- **Local** — own state only (SoC-proportional scaling)
- **Neighborhood** — average of k neighbours' previous actions
- **Global** — full feeder load (soft capped TOU)

Tested across a 2×2 robustness design:

|                       | Deterministic prices | Stochastic prices |
|-----------------------|---------------------|-------------------|
| **Uniform SoC**       | ✓                   | ✓                 |
| **Heterogeneous SoC** | ✓                   | ✓                 |

Neighborhood size was additionally swept from 1 to n−1 (full fleet visibility).

### Key findings

1. **Neighborhood information provides zero benefit at every scale.** Peak reduction was 0% of baseline across all regimes, all configurations, and all neighborhood sizes from 1 to 19. The failure is not about how many peers you observe — it is about the nature of the signal. Lagged peer actions do not approximate real-time feeder state regardless of fleet coverage.

2. **Local self-awareness reduces peak by ~25% under predictable prices, ~13% under stochastic prices.** The SoC-proportional mechanism works by natural self-limiting — batteries that are nearly full charge less aggressively. Effectiveness depends on predictable price structure to build consistent SoC patterns.

3. **Global feeder visibility is robust to price uncertainty and gets stronger under stochastic prices.** Peak reduction holds at 40–46% in medium and hard regimes regardless of price structure, because the controller responds directly to system stress rather than inferring it through price signals.

4. **The type of information matters more than the quantity.** Direct measurement of the system variable you care about (feeder load) is more robust than indirect inference through individual state (SoC). Neighbourhood information — neither direct nor individual — adds nothing.

5. **The original hypothesis was wrong in an interesting way.** Most benefit does not come from minimal information sharing. It comes from the right kind of information. Minimal sharing (neighbourhood) failed entirely; individual state (local) gave partial benefit; only system-level visibility (global) gave consistent results.

---

## What Phase 3 showed

**Question:** Can a system be globally optimal and locally unjust at the same time — and does that injustice require anyone to have intended it?

Ten identical batteries. Same charging desire. Same controller. Same day. Only feeder position differs.

End-of-line batteries face a tighter local constraint — not because a regulator decided to penalize them, but because the physics of the feeder makes their section harder to serve. The controller responds to that physics correctly. The aggregate system is optimal. The distribution of burden is not.

### Key findings

1. **Optimal aggregate outcomes do not imply fair individual outcomes.** In the medium regime, the near-source battery bore 0% of total curtailment. The end-of-line battery bore 33.8% — 3.4× its proportional share. Every battery wanted the same thing. Position determined who was denied.

2. **In hard regimes, end-of-line batteries are completely blocked.** Batteries at positions 0.8–1.0 charged nothing. Batteries near the source charged freely. The system managed feeder stress correctly. Three identical agents were systematically excluded.

3. **The injustice emerged from the rules, not from malice.** No controller decided to penalize end-of-line batteries. The asymmetry was produced automatically by the interaction of physical constraints and a locally rational coordination mechanism. This is the same structure as pricing outcomes in real distribution grids — households in constrained areas see worse returns on solar investment not because of policy intent but because uniform tariffs ignore physical asymmetry.

4. **This system is complex but not yet chaotic.** The transition to sensitive-initial-condition behavior would require adaptive or memory-based agents and is an open question for future work.

### The broader implication

Prices that look punitive, returns on investment that seem unfair, curtailment that falls on the same households repeatedly — these can be fully explained by physical mechanism and mathematical emergence, with no human malice or deliberate policy required.

---

## What Phase 4 showed

**Question:** Can distributed battery droop control produce collective frequency stability — and what governs the boundary between stability and collapse?

Droop control makes each battery respond to frequency deviation: discharge when frequency drops, charge when it rises. No central coordinator. No communication between agents. Each battery acts on one local signal.

The simulator was extended with the swing equation to track grid frequency as an evolving state variable. Two sweeps were run: stability boundary (M × droop_gain) and disturbance response (disturbance_size × droop_gain at fixed M=10).

### Key findings

1. **Stability is governed by the ratio M/droop_gain, not M or droop_gain independently.** The stability condition is approximately M/droop_gain ≥ 5. Below this ratio frequency diverges. Above it, deviation stays within 1 Hz of nominal.

2. **Droop alone cannot replace inertia — this is not well defined.** Setting M=0 produces division by zero in the swing equation. Inertia creates the frequency signal that droop reads. They are not alternatives; they are dependent. Removing inertia completely leaves droop with nothing to respond to.

3. **Droop gain 1.0 is the consistent optimum at M=10.** Across all disturbance sizes tested (5–25 kW), droop=1.0 produced the lowest frequency standard deviation. Lower gains are too passive; higher gains push the system toward instability.

4. **The stability boundary is robust to disturbance size but sensitive to disturbance timing.** The same droop gain that survives a 25 kW drop at t19 nearly fails under a 20 kW drop at t11. Earlier disturbances leave less recovery time. Timing interacts with droop gain in ways disturbance size alone does not predict.

5. **Best stable configuration found: M=50, droop=2 → frequency std=0.053 Hz.** Most aggressive stable configuration: M=30, droop=5 → std=0.165 Hz.

---

## Structure

```
src/              battery, controllers, simulator
experiments/      basic_run.py, information_sweep.py,
                  neighborhood_size_sweep.py, fairness_sweep.py,
                  frequency_sweep.py, disturbance_sweep.py
notebooks/        coordination_comparison.ipynb
results/          csv outputs per configuration
```

## Run

```bash
pip install -r requirements.txt

# Phase 1
python3 experiments/basic_run.py
jupyter notebook notebooks/coordination_comparison.ipynb

# Phase 2
python3 experiments/information_sweep.py
python3 experiments/neighborhood_size_sweep.py

# Phase 3
python3 experiments/fairness_sweep.py

# Phase 4
python3 experiments/frequency_sweep.py
python3 experiments/disturbance_sweep.py
```

---

## What Phase 5 showed

**Question:** What fraction of a fleet needs droop control before the system stabilizes — and does the assignment strategy matter?

A mixed fleet was simulated: some batteries using droop control, the rest using naive TOU. Three assignment strategies were tested — near-source-first, end-of-line-first, and random — across all possible droop fractions from 10% to 100%.

### Key findings

1. **60% of the fleet needs droop control to stabilize.** Below this threshold all three strategies fail regardless of which batteries receive droop. Above it, frequency deviation stays within acceptable bounds.

2. **Near-source-first and random assignment are equivalent.** Both stabilize at 60%. End-of-line-first requires 70% — one extra battery. Position matters at the margin but not dramatically.

3. **Frequency response is position-independent.** Droop effectiveness is the same regardless of where on the feeder the battery sits, because frequency is a global signal observed equally by all agents. This contrasts sharply with curtailment burden (Phase 3), which is strongly position-dependent.

4. **Stability improvement is smooth and predictable.** Each additional droop agent reduces frequency standard deviation consistently. No cliff, no sudden threshold jump — a gradual linear improvement across all strategies.

---

## Structure

```
src/              battery, controllers, simulator
experiments/      basic_run.py, information_sweep.py,
                  neighborhood_size_sweep.py, fairness_sweep.py,
                  frequency_sweep.py, disturbance_sweep.py,
                  mixed_fleet_sweep.py
notebooks/        coordination_comparison.ipynb
results/          csv outputs per configuration
```

## Run

```bash
pip install -r requirements.txt

# Phase 1
python3 experiments/basic_run.py
jupyter notebook notebooks/coordination_comparison.ipynb

# Phase 2
python3 experiments/information_sweep.py
python3 experiments/neighborhood_size_sweep.py

# Phase 3
python3 experiments/fairness_sweep.py

# Phase 4
python3 experiments/frequency_sweep.py
python3 experiments/disturbance_sweep.py

# Phase 5
python3 experiments/mixed_fleet_sweep.py
```