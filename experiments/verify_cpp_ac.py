"""Verify C++ Forward-Backward Sweep AC solver against pandapower & benchmark speed."""
import ctypes
from pathlib import Path
import time

import numpy as np

from semele.ac_feeder import RadialStreetFeeder

LIB_PATH = Path(__file__).resolve().parents[1] / "src" / "semele" / "cpp" / "libfbs.dylib"
lib = ctypes.CDLL(str(LIB_PATH))

lib.solve_radial_ac.argtypes = [
    ctypes.c_int,
    np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS"),
    np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS"),
    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
    np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS"),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
lib.solve_radial_ac.restype = None


def main() -> None:
    n_houses = 20
    spacing_km = 0.04  # urban 40m spacing
    trafo_mva = 0.25
    pf = 0.98

    # 1. Initialize pandapower reference feeder & extract exact cable parameters
    pp_feeder = RadialStreetFeeder(n_houses=n_houses, spacing_km=spacing_km, trafo_mva=trafo_mva, use_cpp=False)
    line_row = pp_feeder.net.line.iloc[0]
    r_seg = float(line_row["r_ohm_per_km"] * spacing_km)
    x_seg = float(line_row["x_ohm_per_km"] * spacing_km)
    i_max = float(line_row["max_i_ka"])

    # 2. Test on heavy synchronized charging (e.g., 8-12 kW per house)
    rng = np.random.default_rng(123)
    p_kw = np.ascontiguousarray(rng.uniform(8.0, 12.0, size=n_houses), dtype=np.float64)
    q_kvar = np.ascontiguousarray(np.abs(p_kw) * np.tan(np.arccos(pf)), dtype=np.float64)

    # Solve with pandapower
    pp_res = pp_feeder.step(p_kw, pf=pf)
    v_pp = pp_feeder.net.res_bus.loc[pp_feeder.house_buses, "vm_pu"].to_numpy()

    # Solve with C++
    v_cpp = np.zeros(n_houses, dtype=np.float64)
    trafo_cpp = ctypes.c_double()
    line_cpp = ctypes.c_double()
    lib.solve_radial_ac(
        n_houses, p_kw, q_kvar, 0.4, trafo_mva, 4.0, 1.2, 0.6, r_seg, x_seg, i_max,
        v_cpp, ctypes.byref(trafo_cpp), ctypes.byref(line_cpp)
    )

    print("=== ACCURACY CHECK (C++ FBS vs pandapower Newton-Raphson) ===")
    print(f"Max bus voltage diff : {np.max(np.abs(v_pp - v_cpp)):.2e} p.u.")
    print(f"V_min (pp vs C++)    : {pp_res['v_min_pu']:.6f} vs {v_cpp.min():.6f} p.u.")
    print(f"Trafo % (pp vs C++)  : {pp_res['trafo_loading_pct']:.3f}% vs {trafo_cpp.value:.3f}%")
    print(f"Line  % (pp vs C++)  : {pp_res['line_loading_pct']:.3f}% vs {line_cpp.value:.3f}%")

    # 3. Speed benchmark: 10,000 AC power flow solves
    n_bench = 10_000
    t0 = time.perf_counter()
    for _ in range(n_bench):
        lib.solve_radial_ac(
            n_houses, p_kw, q_kvar, 0.4, trafo_mva, 4.0, 1.2, 0.6, r_seg, x_seg, i_max,
            v_cpp, ctypes.byref(trafo_cpp), ctypes.byref(line_cpp)
        )
    dt_cpp = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(500):
        pp_feeder.step(p_kw, pf=pf)
    dt_pp = (time.perf_counter() - t0) * (n_bench / 500)

    print(f"\n=== SPEED BENCHMARK ({n_bench:,} AC Solves) ===")
    print(f"pandapower (est.)    : {dt_pp:.2f} s ({n_bench / dt_pp:,.0f} solves/sec)")
    print(f"C++ FBS solver       : {dt_cpp:.4f} s ({n_bench / dt_cpp:,.0f} solves/sec)")
    print(f"Speedup              : {dt_pp / dt_cpp:.1f}x faster!")


if __name__ == "__main__":
    main()