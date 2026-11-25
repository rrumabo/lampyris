# Lampyris

# Short summary
A cyber physical simulator of distributed home batteries and rooftop PV communities on low voltage distribution feeders.
The repository is called **`Lampyris`**. The Python package inside it is called **`semele`**. It models the distribution level battery and feeder dynamics that feed into a Cyprus national transmission simulator (**`phaethon`**).

**Lampyris** (Python package: **`semele`**) is a neighborhood-level power grid simulator that models what happens when dozens of homes on the same street install rooftop solar panels and home batteries that all react to the same electricity prices or weather forecasts. Using real solar data from Paphos, Cyprus, it shows how synchronized charging and discharging can overload local street voltage long before the neighborhood's main transformer hits its limit, and tests how built-in smart-inverter safety settings prevent blackouts at the cost of charging less energy for homes at the far end of the street. When paired with [**phaethon**](https://github.com)—which models Cyprus's national high-voltage transmission grid—the two repositories form an end-to-end digital twin of the island's power system, making it possible to test whether a single price signal or passing cloud over one city can trigger a ripple effect across the entire country.

---

## 1. Published Result (Cyber / Communication Layer)

**Paper:** S. Savva, *When a common price signal is present, network topology leaves no fingerprint on a storage fleet's collective dynamics*, [arXiv:2607.06381](https://arxiv.org) (nlin.CD), July 2026.

Each battery observes the market price through a correlated forecast error:

```text
eps_i(t) = sqrt(rho) * Z(t) + sqrt(1 - rho) * eta_i(t)
```

where `Z(t)` is shared across the fleet, `eta_i(t)` is private to each battery, and `rho` is the pairwise error correlation. Because `Z(t)` projects onto the graph-invariant consensus mode `1/sqrt(N)`, communication topology's share of the dynamics scales as `O(1 / (rho * N))`.

**Measured** (`N = 20` batteries; linear, star, and small-world graphs; 30 seeds)

| Metric | `rho = 0` | `rho = 1` |
|---|---|---|
| `w1` (dominant SVD mode energy) | 0.43–0.44 | 0.963 |
| `PR` (effective active modes) | 4.3–4.4 | 1.08 |
| Dominant mode alignment with `1/sqrt(N)` | 0.96 | 0.998 |

- Between-topology spread is `0.0043` (`alpha = 0.5`) and `0.0181` (`alpha = 0`), both below the single-graph random-seed noise floor (`~0.03`).
- On a scalar kW feeder limit, violations rise smoothly with `rho` with no critical cliff (`rho ≈ 0.84` threshold falsified).

---

## 2. Physical AC Distribution Layer (Cyprus Calibration)

To capture electrical limits hidden by scalar feeder models, `semele` couples the battery fleet to a nonlinear AC radial feeder calibrated to Cyprus/European standards and real solar data:

- **Radial Street Feeder (`src/semele/ac_feeder.py`):** 20-house, `11 kV / 0.4 kV` (`50 Hz`) low-voltage feeder per Electricity Authority of Cyprus (EAC) Distribution Grid Rules (`250 kVA` transformer, `u_k = 4.0%`, `u_kr = 1.2%` per IEC 60076-5; standard `NAYY 4x150 SE` 150 mm² LV cable; `pf = 0.98`). Evaluates **EAC ±5% planning limits (`0.95–1.05 p.u.`)** and **CYS EN 50160 ±10% statutory limits (`0.90–1.10 p.u.`)**.
- **C++17 Forward-Backward Sweep Engine (`src/semele/cpp/fbs_solver.cpp`):** Compiled complex AC solver verified against `pandapower` Newton-Raphson (`7.33e-06 p.u.` max bus voltage error, `110,452 solves/sec`, `588.9x` speedup).
- **Solar Dataset (`data/paphos_pv_hourly.csv`):** 365 days of hourly rooftop PV output (`5.5 kWp`, `30°` tilt, due South, `14%` system loss) for **Paphos, Cyprus (`34.775°N, 32.424°E`)** from **EU PVGIS-SARAH3**.

**Measured Findings (`rho = 1.0`, 100 seasonal Paphos days)**

| Feeder Topology | Battery / House | `V_min` (Fixed) | `V_min` (SDR) | Battery-Caused ±5% Viol (Fixed → SDR) | Peak Trafo Load (Fixed / SDR) |
|---|---|---|---|---|---|
| **Urban (`40 m`)** | `3 kW` | `0.942 p.u.` | `0.933 p.u.` | `-5.1%` → `+5.2%` | `35.6% / 40.7%` |
| **Urban (`40 m`)** | `5 kW` | `0.928 p.u.` | `0.899 p.u.` | `-0.5%` → `+21.0%` | `43.9% / 60.9%` |
| **Urban (`40 m`)** | `7 kW` | `0.899 p.u.` | `0.873 p.u.` | `+4.7%` → `+27.2%` | `60.9% / 76.0%` |
| **Urban (`40 m`)** | `10 kW` | `0.851 p.u.` | `0.836 p.u.` | `+22.0%` → `+44.6%` | `89.2% / 98.1%` |
| **Rural (`100 m`)** | `3 kW` | `0.853 p.u.` | `0.829 p.u.` | `-13.2%` → `-1.9%` | `38.1% / 44.0%` |
| **Rural (`100 m`)** | `5 kW` | `0.812 p.u.` | `0.718 p.u.` | `-4.0%` → `+6.1%` | `48.2% / 70.9%` |
| **Rural (`100 m`)** | `7 kW` | `0.715 p.u.` | `0.599 p.u.` | `+8.1%` → `+13.0%` | `71.2% / 97.5%` |
| **Rural (`100 m`)** | `10 kW` | `0.243 p.u.` | `0.020 p.u.` | `+10.2%` → `+17.3%` | `107.8% / 123.1%` |

1. **Voltage breaches statutory limits before transformer overload:** On `urban_40m` (`10 kW`), peak transformer loading remains below 100% (`89.2%` fixed, `98.1%` SDR), yet bus voltage drops to `0.851 p.u.` (fixed) and `0.836 p.u.` (SDR), violating the `0.90 p.u.` CYS EN 50160 limit.
2. **Endogenous SDR cobweb oscillation & collapse:** One-hour lagged local Supply–Demand Ratio (`SDR`) pricing flip-flops `46%–75%` of hours (`80 -> 20 -> 80`), synchronizing charging without correlated forecast noise and driving `10 kW` rural feeders (`100 m` spacing) into saddle-node AC voltage collapse (`V_min = 0.020 p.u.`).
3. **Helper-to-breaker capacity crossover:** Under fixed PV-shaped pricing, `3–5 kW` batteries absorb midday solar peaks and reduce net ±5% voltage violations (`-5.1%` urban, `-13.2%` rural at `3 kW`). Above `7 kW`, synchronized charging flips them into net voltage violators.
4. **EN 50549-1 Volt-Watt droop (`P(V)`) equity trade-off:** Instantaneous closed-loop Volt-Watt droop (`0.96 -> 0.95 p.u.` charging cutoff; `1.04 -> 1.05 p.u.` discharging cutoff) eliminates rural voltage collapse (`0.020 -> 0.791 p.u.` SDR; `0.243 -> 0.787 p.u.` fixed) and restores urban statutory compliance (`V_min >= 0.913 p.u.`) without peer-to-peer communication (1-hour lagged droop fails), at the cost of >91% charging curtailment at the feeder tail (`tail_to_head_charge_ratio = 0.042–0.088` at `10 kW`).

---

## 3. Repository Structure

```text
data/
  paphos_pv_hourly.csv         EU PVGIS-SARAH3 hourly solar dataset (Paphos, Cyprus)

src/semele/
  cpp/fbs_solver.cpp           C++17 nonlinear AC Forward-Backward Sweep solver
  ac_feeder.py                 11 kV / 0.4 kV radial street model (C++ & pandapower)
  battery.py                   Battery power, energy, and efficiency limits
  controllers.py               TOU, belief/neighbor hybrid, and EN 50549-1 Volt-Watt droop
  network.py                   Information graphs (linear, star, small-world) + Laplacian
  pricing.py                   Fixed PV-shaped price and local SDR price
  simulator.py                 Coupled cyber-physical daily simulation loop

experiments/
  reproduce_core_result.py     Core rho sweep: peaks, violations, curtailment
  make_paper_plots.py          arXiv:2607.06381 figures 1 and 2
  check_consensus_mode.py      Dominant mode vs 1/sqrt(N)
  run_null_topology_test.py    Same-graph noise floor
  run_belief_rho_sweep.py      2D sweep over rho and alpha
  run_belief_rho_multiseed.py  2D sweep over 30 seeds
  run_spectral_sweep.py        w1 / PR along rho
  spectral_diagnostics.py      SVD measures w1 and PR
  verify_cpp_ac.py             Verifies C++ FBS solver against pandapower NR
  run_community.py             AC feeder x Paphos PV x price rules x battery size x rho
  run_droop_test.py            Unmitigated vs closed-loop EN 50549-1 Volt-Watt droop
```

---

## 4. Setup & Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Compile C++17 AC solver (macOS / Linux)
clang++ -O3 -std=c++17 -shared -fPIC src/semele/cpp/fbs_solver.cpp -o src/semele/cpp/libfbs.dylib

python -m experiments.make_paper_plots      # results/paper/
python -m experiments.verify_cpp_ac         # C++ vs pandapower accuracy & speed check
python -m experiments.run_community         # results/community/
python -m experiments.run_droop_test        # results/droop/
```

Run scripts as modules (`python -m experiments.…`) so package imports resolve cleanly.

## License

MIT. See `LICENSE`.