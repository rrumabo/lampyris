# Battery Coordination Sandbox: Exploring Emergent Dynamics in Distributed Energy Systems

## Abstract

This document describes an ongoing simulation study designed to probe the epistemic foundations of coordination among distributed batteries. The central question is deliberately broad and fundamental:

> **When many agents follow simple local rules, what aggregate behaviour emerges and why?**

The work does not present a grid-control tool nor a ready-to-deploy algorithm. Instead, it offers a controlled environment—a sandbox—in which to examine collective phenomena. By varying information flows, physical constraints and control strategies, we seek to expose the limits of local rationality and to make explicit the conditions under which rational local actions produce unintended global outcomes. Throughout this document we favour clarity over marketing, highlight failure modes as well as successes, and openly discuss the epistemic uncertainties that remain.

## Introduction

Distributed energy resources promise autonomy and flexibility, yet they also introduce unprecedented collective dynamics. A battery owner may act rationally based on local price signals, but when many such agents act simultaneously, their combined behaviour can stress the feeder, destabilise the grid, or impose unfair burdens on specific participants. Traditional simulations often gloss over these emergent effects. In contrast, this sandbox deliberately isolates simple mechanisms to observe how they interact. The philosophy guiding this project is that complexity emerges from composition, and careful scientific inquiry must identify which aspects of that composition matter.

To that end, we progress through a series of phases, each asking a focused question. We use stylised controllers, simplified feeders and controlled disturbances to ensure that any observed behaviour can be traced back to specific assumptions. The results are discussed critically: when a hypothesis fails, we treat the failure as a finding rather than a setback. Metrics are chosen for interpretability—e.g., total excess power over a constraint is more informative than simply counting violations—and we resist the temptation to declare a single 'best' solution.

## Phase 1 – Controllers under Stress

**Question:** How do different local control strategies perform under varying degrees of feeder stress?

We compared four controllers—Time‑Of‑Use (TOU), Randomised TOU, Hard Capped TOU and Soft Capped TOU—across light, medium and hard loading conditions. The naive TOU controller caused strong synchronisation: many batteries charged at the same time, resulting in the worst feeder peaks. Randomisation broke synchronisation only partially and its benefit was sensitive to the regime. Hard capping (abruptly shutting down charging once a threshold was reached) suppressed overloads most effectively in the hard regime but at the cost of rigidity. Soft capping (scaling charge rates continuously with feeder stress) offered the best balance across regimes.

**Key findings:**

1. Local rationality does not scale. A rule that is harmless for one battery can be harmful for many.
2. Performance is regime-dependent. No single controller dominates across all stress levels; a control philosophy that ignores regime dependence risks misleading conclusions.
3. Structured coordination outperforms randomisation. The soft capping controller’s parameter has predictable effects, whereas randomisation acts blindly.
4. Metrics matter. The 'violation count' (number of times a threshold is exceeded) can mask the severity of overloads; total excess power is a more honest measure of harm.

## Phase 2 – Information as a Resource

**Question:** How much and what kind of information does an agent need to mitigate its harmful impact?

We tested four information levels: None (price only), Local (own state of charge), Neighbourhood (average of k neighbours’ previous actions) and Global (real-time feeder load). Each was mapped to a controller and evaluated under deterministic and stochastic price scenarios with both uniform and heterogeneous initial states.

**Key findings:**

1. Neighbourhood information adds no value. Observing neighbours’ past actions did not reduce peaks at any scale: the average reduction was 0 % of baseline across all neighbourhood sizes. Inference through lagged peer behaviour is a dead end.
2. Self-awareness helps only when prices are predictable. Scaling charge power proportional to state-of-charge reduces peaks by ~25 % under deterministic prices and ~13 % under stochastic prices. The benefit arises from natural self-limiting: nearly full batteries charge less aggressively.
3. Global visibility is robust. Access to the feeder load reduces peaks by 40–46 % across regimes and price structures because the controller responds to the variable it actually cares about—system stress—rather than guessing through proxies.
4. Quality matters more than quantity. Minimal information is not necessarily beneficial; information must be relevant. Our original hypothesis—that small neighbourhoods would suffice—was falsified, underscoring the value of negative results.

## Phase 3 – Fairness and Physical Asymmetry

**Question:** Can a globally optimal solution be locally unjust—and does that injustice require deliberate intent?

We simulated ten identical batteries placed along a feeder. Each followed the same controller and had the same charging desire, but physical constraints made the end-of-line sections more restrictive. Despite identical goals, near-source batteries enjoyed unconstrained charging while end-of-line batteries faced severe curtailment. In hard regimes, some end-of-line batteries charged nothing, while those near the source charged freely.

**Key findings:**

1. Aggregate optimality does not guarantee fairness. In the medium regime, the near-source battery bore 0 % of total curtailment while the end-of-line battery bore 33.8 %—over three times its proportional share.
2. Asymmetry emerges naturally. The controller did not 'punish' specific batteries; the physics did. This mirrors real distribution grids where uniform tariffs lead to unequal returns on solar investments, not because of malice but because physical infrastructure is ignored.
3. The system is complex but not chaotic. No sensitive dependence on initial conditions was observed. True chaos would require adaptive or memory-based agents, suggesting an avenue for future work.

## Phase 4 – Frequency Stability through Droop Control

**Question:** Can distributed battery droop control stabilise grid frequency—and what governs the boundary between stability and collapse?

We extended the simulator with the swing equation to track frequency as a state variable and implemented droop control: batteries discharge when frequency drops and charge when it rises. We ran sweeps over inertial constant M and droop gain and tested responses to disturbances.

**Key findings:**

1. The stability boundary scales with M/droop_gain. Stability requires M/droop_gain ≥ 5. Inertial constant and gain cannot be considered independently.
2. Droop is not a substitute for inertia. Setting M=0 is ill-posed: inertia generates the frequency signal droop responds to. Without it, droop has nothing to act upon.
3. Optimal gain depends on context. At M=10, droop gain ≈1.0 minimises frequency deviations across disturbance sizes. Higher gains may drive the system toward instability; lower gains are too passive.
4. Timing matters. The same droop gain can survive a 25 kW disturbance at t=19 but nearly fail under a 20 kW disturbance at t=11, illustrating that recovery time and disturbance timing interact in nontrivial ways.

## Phase 5 – Mixed Fleets and the Role of Participation

**Question:** What fraction of a fleet needs droop control to achieve stability, and does assignment strategy matter?

We simulated fleets where some batteries used droop control and others naive TOU. Strategies for selecting droop participants included near-source first, end-of-line first and random, and the fraction of droop agents varied from 10 % to 100 %.

**Key findings:**

1. A participation threshold exists. At least 60 % of the fleet must employ droop for stability. Below this, all strategies fail regardless of which batteries are selected.
2. Position has limited impact. Near-source and random assignment both stabilise at 60 %. End-of-line assignment requires 70 %. Unlike curtailment in Phase 3, frequency response is largely position-independent because frequency is a global signal.
3. Stability improves smoothly with participation. Each additional droop agent reduces frequency deviation predictably; there is no sharp cliff. This suggests that partial adoption of droop yields incremental benefits.

## Phase 6 – Network Topology and Emergent Synchronisation

**Question:** How do network topology and heterogeneity in coupling strength shape the transition between order and disorder?

We replaced the linear feeder with general graphs (linear chain, star and Watts–Strogatz small-world) and assigned each battery to a node. The coupling strength k between neighbours controlled how strongly each agent adjusted its internal state in response to neighbours. We first considered a homogeneous k and then introduced heterogeneity in k_i values.

**Key findings:**

1. Topology determines the synchronisation window. In small-world networks, synchronisation emerges for k as low as 0.05 and disappears by 0.21; in linear chains the window extends to about 0.41; in star networks it is absent. Shortcuts accelerate both synchronisation and polarisation.
2. Beyond a critical k the system polarises. For k above the synchronisation window, the state variance jumps abruptly and remains high: agents split into opposing factions with large positive or negative internal states. Small-world networks polarise at lower k than linear ones. The global signal amplifies local oscillations.
3. Heterogeneous coupling reveals leaders. When k_i are drawn from a distribution, agents with high k_i drive their neighbourhoods toward extreme states and correlate strongly with the magnitude of their final internal state. In star graphs, heterogeneity leads to clusters around the hub; in small-world graphs it triggers broader polarisation. Uniformly low k_i yields synchronisation in small-world networks but not in star networks.

These results caution against naive application of consensus theories: the 'correct' value of k depends on the network’s spectral properties, and heterogeneity can destabilise even otherwise stable networks.

## Phase 7 – Correlated Belief, Synchronisation Collapse, and Feeder Failure

**Question:** What is the critical belief correlation ρ_c above which
topology can no longer prevent synchronisation-driven collective failure —
and how does topology modulate the gap between collapse and actual grid failure?

Two experiments were run. The price-sync sweep used a TOU controller and
corrupted only the price signal, sweeping ρ_agents from 0 to 1 across four
topologies with 30 batteries and 20 runs per point. The feeder-failure sweep
used the hybrid belief–neighbourhood controller with a calibrated feeder
limit, measuring when synchronised behaviour produced actual feeder overload.

**Key findings:**

1. **Topology modulates ρ_c.** The critical correlation at which
synchronisation collapse begins depends on network structure:
small-world collapses first (ρ_c ≈ 0.21), legacy ring and linear
chain follow (ρ_c ≈ 0.23–0.26), and the star resists longest
(ρ_c ≈ 0.31–0.41 depending on controller).

2. **Star topology delays onset but amplifies collapse.** The hub
structure mediates neighbour signals and postpones the synchronisation
threshold. Once the threshold is crossed the star collapses more
steeply than other topologies. Resistance and catastrophic collapse
are two sides of the same hub-mediation mechanism.

3. **The decline is gradual, not a sharp phase transition.** Diversity
erodes continuously from ρ = 0 to ρ = 1. This is consistent with
common-noise synchronisation theory, where shared external forcing
degrades independence incrementally rather than triggering a sudden
bifurcation.

4. **The spectral conjecture is falsified.** The initial hypothesis
that ρ_c scales with 1/λ₂ (inverse algebraic connectivity) is not
supported. Linear and legacy-ring share nearly identical ρ_c despite
an 18-fold difference in λ₂. ρ_c is governed by local degree
structure and information aggregation, not global spectral mixing rate.

5. **Topology changes collapse curve shape, not only position.**
The slope of the sync-index curve near ρ_c differs across topologies:
star is steepest (slope 1.22), legacy-ring is gentlest (slope 0.76).
More resistant topologies collapse more steeply once triggered —
a delay-but-amplify pattern. Total collapse magnitude (~82%) is
topology-independent.

6. **Collapse onset and feeder failure are independent events.**
With a feeder-aware controller and calibrated feeder limit, both
thresholds were measured. The protection window — the gap between
ρ_c_sync and ρ_c_failure — varies significantly by topology:

| Topology    | ρ_c_sync | ρ_c_failure | Protection window |
|-------------|----------|-------------|-------------------|
| linear      | 0.308    | 0.359       | 0.051             |
| legacy_ring | 0.333    | 0.462       | 0.128             |
| star        | 0.410    | 0.590       | 0.179             |
| small_world | 0.282    | 0.487       | 0.205             |

Small-world collapses earliest but has the largest protection window.
Linear collapses second but has the smallest window. Collapse onset
does not predict failure onset — they are independent properties of
the topology.

7. **Local degree structure governs ρ_c, not spectral mixing.**
Topologies with the same local degree structure (linear and legacy-ring,
both degree-2) share the same ρ_c regardless of global topology.
The protection window is also governed by local topology: small-world
shortcuts distribute synchronised load across multiple paths, delaying
feeder impact despite early collapse onset. Linear chains propagate
synchronised load directly, leaving almost no buffer.

## Discussion and Outlook

A new direction has emerged from Phase 7. The central question is no
longer only what happens when agents share information, but what happens
when they share the same mistaken belief. Correlated forecast errors —
arising naturally from shared weather APIs, common aggregators, or
synchronised market signals — act as a hidden coordination mechanism.
Each agent behaves rationally given its belief; the collective failure
is a property of the belief structure, not of any individual decision.
This connects the sandbox to recent work on mean-field games for
distributed storage (Al Dandachly et al., 2026), which proves
equilibrium existence under independent private noise but leaves the
correlated noise regime open. The sandbox provides the first empirical
map of that regime.
