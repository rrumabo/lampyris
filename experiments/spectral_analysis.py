from __future__ import annotations
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.network import make_linear, make_star, make_small_world


N = 10

THRESHOLD_PATH = Path("results/price_sync_thresholds.csv")
PLOT_PATH = Path("results/spectral_conjecture.png")


def circular_chain_adjacency(n: int, neighborhood_size: int = 2) -> np.ndarray:
    """
    Match simulator legacy_ring fallback:
    each node observes the next `neighborhood_size` nodes with wrap-around.

    The simulator's fallback is directed:
        i -> i+1, i+2, ...
    Spectral Laplacian theory expects an undirected symmetric graph,
    so we symmetrize A before building L.
    """
    A = np.zeros((n, n), dtype=float)

    for i in range(n):
        for j in range(1, neighborhood_size + 1):
            A[i, (i + j) % n] = 1.0

    A = np.maximum(A, A.T)
    return A


def adjacency_from_network(network, n: int) -> np.ndarray:
    """Build adjacency from the repo's Network object.

    In this project, network.agents is indexed by integer node IDs.
    Each entry has a .neighbors list.
    """
    A = np.zeros((n, n), dtype=float)

    for i in range(n):
        for j in network.agents[i].neighbors:
            A[i, j] = 1.0

    A = np.maximum(A, A.T)
    return A


def laplacian_spectrum(A: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    D = np.diag(A.sum(axis=1))
    L = D - A
    eigs = np.sort(np.linalg.eigvalsh(L))
    return L, eigs


def main() -> None:
    topologies: dict[str, np.ndarray] = {
        "legacy_ring": circular_chain_adjacency(N, neighborhood_size=2),
        "linear": adjacency_from_network(make_linear(N), N),
        "star": adjacency_from_network(make_star(N), N),
        "small_world": adjacency_from_network(make_small_world(N), N),
    }

    rows = []

    print("\nSpectral analysis")
    print("=================\n")

    for name, A in topologies.items():
        _, eigs = laplacian_spectrum(A)
        lambda_2 = float(eigs[1])

        rows.append(
            {
                "topology": name,
                "lambda_2": lambda_2,
                "spectrum": eigs,
            }
        )

        spectrum_text = ", ".join(f"{value:.4f}" for value in eigs)
        print(f"{name}")
        print(f"  lambda_2 = {lambda_2:.6f}")
        print(f"  spectrum = [{spectrum_text}]")
        print()

    if not THRESHOLD_PATH.exists():
        raise FileNotFoundError(
            f"Missing {THRESHOLD_PATH}. Run experiments/rho_sweep.py first."
        )

    thresholds = pd.read_csv(THRESHOLD_PATH)
    spectral = pd.DataFrame(
        [{"topology": row["topology"], "lambda_2": row["lambda_2"]} for row in rows]
    )

    merged = spectral.merge(thresholds, on="topology", how="inner")

    if "rho_c_sync_collapse" not in merged.columns:
        raise ValueError(
            "rho_sweep_thresholds.csv must contain rho_c_sync_collapse."
        )

    print("rho_c vs lambda_2")
    print("=================")
    print(
        merged[
            [
                "topology",
                "lambda_2",
                "rho_c_sync_collapse",
                "rho_c_failure",
                "protection_gap",
            ]
        ].to_string(index=False)
    )

    PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8, 6))

    for _, row in merged.iterrows():
        x = row["lambda_2"]
        y = row["rho_c_sync_collapse"]

        if pd.isna(y):
            continue

        plt.scatter(x, y, s=90)
        plt.text(
            x,
            y,
            f" {row['topology']}",
            va="center",
            fontsize=9,
        )

    plt.xlabel("lambda_2 algebraic connectivity")
    plt.ylabel("rho_c_sync_collapse")
    plt.title("Spectral conjecture test: rho_c vs lambda_2")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(PLOT_PATH, dpi=200)

    print(f"\nsaved {PLOT_PATH}")


if __name__ == "__main__":
    main()
