import ctypes
from pathlib import Path
import numpy as np
import pandapower as pp
from pandapower.auxiliary import LoadflowNotConverged

_LIB_PATH = Path(__file__).resolve().parent / "cpp" / "libfbs.dylib"


class RadialStreetFeeder:
    def __init__(
        self,
        n_houses: int = 20,
        spacing_km: float = 0.04,
        trafo_mva: float = 0.25,
        use_cpp: bool = True,
    ):
        self.n_houses = n_houses
        self.spacing_km = spacing_km
        self.trafo_mva = trafo_mva
        self.net = pp.create_empty_network(f_hz=50.0)

        hv_bus = pp.create_bus(self.net, vn_kv=11.0, name="MV_Grid")
        lv_bus = pp.create_bus(self.net, vn_kv=0.4, name="LV_Substation")
        pp.create_ext_grid(self.net, bus=hv_bus, vm_pu=1.0)
        pp.create_transformer_from_parameters(
            self.net, hv_bus=hv_bus, lv_bus=lv_bus,
            sn_mva=trafo_mva, vn_hv_kv=11.0, vn_lv_kv=0.4,
            vkr_percent=1.2, vk_percent=4.0, pfe_kw=0.6, i0_percent=0.25
        )

        self.house_buses = []
        prev_bus = lv_bus
        for i in range(n_houses):
            b = pp.create_bus(self.net, vn_kv=0.4, name=f"House_{i}")
            pp.create_line(
                self.net, from_bus=prev_bus, to_bus=b,
                length_km=spacing_km, std_type="NAYY 4x150 SE"
            )
            pp.create_load(self.net, bus=b, p_mw=0.0, q_mvar=0.0, name=f"NetLoad_{i}")
            self.house_buses.append(b)
            prev_bus = b

        line_row = self.net.line.iloc[0]
        self.r_seg = float(line_row["r_ohm_per_km"] * spacing_km)
        self.x_seg = float(line_row["x_ohm_per_km"] * spacing_km)
        self.i_max_ka = float(line_row["max_i_ka"])

        self._lib = None
        if use_cpp and _LIB_PATH.exists():
            self._lib = ctypes.CDLL(str(_LIB_PATH))
            self._lib.solve_radial_ac.argtypes = [
                ctypes.c_int,
                np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS"),
                np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS"),
                ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS"),
                ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_double),
            ]
            self._lib.solve_radial_ac.restype = None

    def step(self, house_net_kw: np.ndarray, pf: float = 0.98) -> dict:
        p_kw = np.ascontiguousarray(house_net_kw, dtype=np.float64)
        q_kvar = np.ascontiguousarray(np.abs(p_kw) * np.tan(np.arccos(pf)), dtype=np.float64)

        if self._lib is not None:
            v_houses = np.zeros(self.n_houses, dtype=np.float64)
            trafo_pct = ctypes.c_double()
            line_pct = ctypes.c_double()
            self._lib.solve_radial_ac(
                self.n_houses, p_kw, q_kvar, 0.4, self.trafo_mva,
                4.0, 1.2, 0.6, self.r_seg, self.x_seg, self.i_max_ka,
                v_houses, ctypes.byref(trafo_pct), ctypes.byref(line_pct)
            )
            v_min = float(v_houses.min())
            v_max = float(v_houses.max())
            collapsed = (not np.isfinite(v_min)) or (v_min < 0.50)
            if collapsed:
                v_min = 0.0
                v_houses = np.zeros(self.n_houses, dtype=np.float64)
            return {
                "v_houses": v_houses,
                "v_min_pu": v_min,
                "v_max_pu": v_max if not collapsed else 0.0,
                "voltage_collapse": collapsed,
                "voltage_planning_viol": collapsed or (v_min < 0.95) or (v_max > 1.05),
                "voltage_statutory_viol": collapsed or (v_min < 0.90) or (v_max > 1.10),
                "trafo_loading_pct": float(trafo_pct.value) if not collapsed else 100.0,
                "line_loading_pct": float(line_pct.value) if not collapsed else 100.0,
                "thermal_overload": collapsed or (trafo_pct.value > 100.0) or (line_pct.value > 100.0),
            }

        self.net.load["p_mw"] = p_kw / 1000.0
        self.net.load["q_mvar"] = q_kvar / 1000.0
        try:
            pp.runpp(self.net, algorithm="nr", numba=True, init="flat")
        except LoadflowNotConverged:
            return {
                "v_houses": np.zeros(self.n_houses, dtype=np.float64),
                "v_min_pu": 0.0,
                "v_max_pu": 0.0,
                "voltage_collapse": True,
                "voltage_planning_viol": True,
                "voltage_statutory_viol": True,
                "trafo_loading_pct": 100.0,
                "line_loading_pct": 100.0,
                "thermal_overload": True,
            }

        v_houses = self.net.res_bus.loc[self.house_buses, "vm_pu"].to_numpy()
        v_min = float(v_houses.min())
        v_max = float(v_houses.max())
        trafo_loading = float(self.net.res_trafo["loading_percent"].max())
        line_loading = float(self.net.res_line["loading_percent"].max())

        return {
            "v_houses": v_houses,
            "v_min_pu": v_min,
            "v_max_pu": v_max,
            "voltage_collapse": False,
            "voltage_planning_viol": (v_min < 0.95) or (v_max > 1.05),
            "voltage_statutory_viol": (v_min < 0.90) or (v_max > 1.10),
            "trafo_loading_pct": trafo_loading,
            "line_loading_pct": line_loading,
            "thermal_overload": (trafo_loading > 100.0) or (line_loading > 100.0),
        }