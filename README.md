# Grid Battery Control — From Greedy to Risk-Aware MPC

## Overview

This project studies how different control strategies manage a battery connected to a power grid with renewable generation.

We compare three approaches:

- **Greedy baseline** — reacts only to current conditions  
- **Deterministic MPC** — optimizes over a future horizon  
- **Uncertainty-aware MPC** — accounts for forecast errors  

The goal is not realism.

The goal is **understanding how control strategies behave under identical conditions**.

------

## Core Idea

All controllers use the same data.

What changes is how they treat the future:

- Greedy → *reactive*
- MPC → *predictive*
- Uncertainty-aware MPC → *risk-aware*

------

## System Setup

- Data: German load, solar, and wind forecasts  
- Net load:
  ```
  net_load = demand − (solar + wind)
  ```
- Battery:
  - Fixed capacity (intentionally small)
  - Charge/discharge limits
  - State-of-charge (SOC) dynamics

### Why a small battery?

Because it exposes bad control immediately.

A large battery hides mistakes.  
A small one forces discipline.

------

## Controllers

### 1. Greedy Baseline

Rule-based:

- Charge when surplus  
- Discharge when deficit  

No planning. No anticipation.

------

### 2. Deterministic MPC

Optimizes over a time horizon using forecasted data.

- Looks ahead (e.g. 24 hours)  
- Minimizes a cost function  
- Balances battery usage and grid smoothing  

Key idea: **plan instead of react**

------

### 3. Uncertainty-Aware MPC

Extends MPC by incorporating forecast uncertainty.

- Adds reserve margin  
- Adjusts decisions based on risk  
- Acts more conservatively when needed  

Key idea: **plan for error, not just prediction**

------

## What We Tested

All controllers were evaluated on:

- Same dataset  
- Same battery constraints  
- Same time horizon  

This ensures **fair comparison**.

------

## Key Findings

### 1. Greedy fails long-term

- Quickly depletes battery  
- Cannot react later  
- Strong short-term, weak overall  

------

### 2. MPC smooths behavior

- Reduces volatility  
- Preserves battery capacity  
- Makes consistent decisions  

------

### 3. Uncertainty-aware MPC changes behavior

- More cautious actions  
- Earlier adjustments  
- Accounts for forecast error  

------

## Important Insight

Better control does **not always mean lower cost**.

Different controllers optimize different objectives:

- Greedy → immediate gain  
- MPC → stability  
- Risk-aware MPC → robustness  

Your result depends on what you care about.

------

## Project Structure

```
data/
  processed/        # datasets and results

src/
  deterministic_mpc.py
  uncertainty_aware_mpc.py

notebooks/
  phase_1_...ipynb
  ...
  phase_5_...ipynb
```

------

## How to Run

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Run notebooks in order:
```
notebooks/
```

3. Outputs are saved in:
```
data/processed/
```

------

## Final Note

This is not a production system.

It is a **control experiment**.

The point is simple:

> Different ways of thinking about the future lead to fundamentally different system behavior.

And that’s the whole game.