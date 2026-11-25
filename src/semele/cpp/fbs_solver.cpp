#include <cmath>
#include <complex>
#include <vector>

using cplx = std::complex<double>;

extern "C" {

/**
 * Solves exact nonlinear AC power flow for an N-bus radial street feeder
 * fed by a single HV/LV distribution transformer (Forward-Backward Sweep).
 *
 * Inputs:
 *   n_buses       : number of house buses along the radial feeder (e.g., 20)
 *   p_kw          : array [n_buses] net active power per house (kW, >0 import, <0 export)
 *   q_kvar        : array [n_buses] reactive power per house (kVAr)
 *   v_base_kv     : LV nominal line-to-line voltage (0.4 kV)
 *   trafo_mva     : transformer rated power (e.g., 0.25 MVA)
 *   vk_pct        : transformer short-circuit impedance (%) (e.g., 4.0)
 *   vkr_pct       : transformer resistive short-circuit voltage (%) (e.g., 1.2)
 *   pfe_kw        : transformer iron/core losses (kW) (e.g., 0.6)
 *   r_line_ohm    : resistance of each line segment (Ohm)
 *   x_line_ohm    : reactance of each line segment (Ohm)
 *   i_max_ka      : thermal current rating of the cable (kA)
 *
 * Outputs:
 *   out_v_pu      : array [n_buses] voltage magnitude (p.u.) at each house
 *   out_trafo_pct : pointer to transformer loading (%)
 *   out_line_pct  : pointer to max cable thermal loading (%)
 */
void solve_radial_ac(
    int n_buses,
    const double* p_kw,
    const double* q_kvar,
    double v_base_kv,
    double trafo_mva,
    double vk_pct,
    double vkr_pct,
    double pfe_kw,
    double r_line_ohm,
    double x_line_ohm,
    double i_max_ka,
    double* out_v_pu,
    double* out_trafo_pct,
    double* out_line_pct
) {
    // Convert base quantities to per-unit (S_base = 1 MVA, V_base = 0.4 kV)
    const double s_base_mva = 1.0;
    const double z_base_ohm = (v_base_kv * v_base_kv) / s_base_mva; // 0.16 Ohm at 0.4 kV

    // Line segment series impedance in p.u.
    const cplx z_line(r_line_ohm / z_base_ohm, x_line_ohm / z_base_ohm);

    // Transformer series impedance in p.u. (referred to 1 MVA base)
    const double z_tr_mag = (vk_pct / 100.0) * (s_base_mva / trafo_mva);
    const double r_tr = (vkr_pct / 100.0) * (s_base_mva / trafo_mva);
    const double x_tr = std::sqrt(std::max(0.0, z_tr_mag * z_tr_mag - r_tr * r_tr));
    const cplx z_trafo(r_tr, x_tr);

    // Shunt core conductance for iron losses (pfe_kw)
    const double g_core = (pfe_kw / 1000.0) / s_base_mva;

    // Complex power injections in p.u. (S = P + jQ)
    std::vector<cplx> S_load(n_buses);
    for (int i = 0; i < n_buses; ++i) {
        S_load[i] = cplx(p_kw[i] / 1000.0, q_kvar[i] / 1000.0);
    }

    // Node 0 = LV substation secondary bus; Nodes 1..n_buses = House 0..N-1
    std::vector<cplx> V(n_buses + 1, cplx(1.0, 0.0));
    std::vector<cplx> I_branch(n_buses + 1, cplx(0.0, 0.0)); // branch 0 = transformer

    const cplx V_slack(1.0, 0.0);
    const double tol = 1e-10;
    const int max_iter = 50;

    for (int iter = 0; iter < max_iter; ++iter) {
        // 1. Backward Sweep: sum load currents from end of street back to transformer
        cplx I_downstream(0.0, 0.0);
        for (int i = n_buses; i >= 1; --i) {
            cplx I_house = std::conj(S_load[i - 1] / V[i]);
            I_downstream += I_house;
            I_branch[i] = I_downstream;
        }
        // Transformer current = total feeder current + core magnetizing loss
        I_branch[0] = I_downstream + g_core * V[0];

        // 2. Forward Sweep: update bus voltages from HV slack -> LV bus -> House N
        double max_dv = 0.0;
        cplx V_new_0 = V_slack - z_trafo * I_branch[0];
        max_dv = std::max(max_dv, std::abs(V_new_0 - V[0]));
        V[0] = V_new_0;

        for (int i = 1; i <= n_buses; ++i) {
            cplx V_new = V[i - 1] - z_line * I_branch[i];
            max_dv = std::max(max_dv, std::abs(V_new - V[i]));
            V[i] = V_new;
        }

        if (max_dv < tol) {
            break;
        }
    }

    // Output bus voltage magnitudes
    for (int i = 0; i < n_buses; ++i) {
        out_v_pu[i] = std::abs(V[i + 1]);
    }

    // Transformer apparent power loading (%)
    double s_trafo_mva = std::abs(V_slack * std::conj(I_branch[0])) * s_base_mva;
    *out_trafo_pct = (s_trafo_mva / trafo_mva) * 100.0;

    // Max cable thermal loading (%) — base current I_base = S_base / (sqrt(3) * V_base)
    const double i_base_ka = s_base_mva / (std::sqrt(3.0) * v_base_kv);
    double max_i_ka = 0.0;
    for (int i = 1; i <= n_buses; ++i) {
        max_i_ka = std::max(max_i_ka, std::abs(I_branch[i]) * i_base_ka);
    }
    *out_line_pct = (max_i_ka / i_max_ka) * 100.0;
}

} // extern "C"
