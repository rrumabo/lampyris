# Pythia → Lambyris Handoff Contract

## Stack

Pneuma generates the world.
Risk Dispatch studies how one agent should act under uncertain forecasts of that world.
Polis studies what happens when many agents act using those rules inside shared infrastructure.

## The bridge

Correlated belief is the mechanism by which uncertainty becomes collective behaviour.

A single agent acting under forecast uncertainty is a control problem.
Many agents acting under the same forecast uncertainty is an emergence problem.

The parameter that crosses that boundary is `rho_agents`:

- `rho_agents: 0.0` — each agent has private uncertainty. Errors are independent.
- `rho_agents: 1.0` — all agents share the same forecast shock. Errors are identical.

When `rho_agents` is high, individually rational agents synchronize without communicating.
That synchronization is the collective failure mode this stack was built to study.

This was observed empirically in Battery Sandbox Phase 2: same price signal, same timing,
same inference, same action, collective failure. `rho_agents` is the formal version of that result.

## What this file governs

This contract defines the interface between Risk Dispatch (producer) and Polis (consumer).

Risk Dispatch outputs a handoff package describing:
- the controller a single agent uses
- the uncertainty regime it operates under
- the battery parameters
- the required input timeseries

Polis instantiates that controller across N agents and studies collective consequences.

Polis does not derive controllers. Risk Dispatch does not run multi-agent simulations.
The contract is the boundary.

## Machine-readable spec

See `interface_spec.yaml` in this directory.

## Version

schema_version: 0.1
