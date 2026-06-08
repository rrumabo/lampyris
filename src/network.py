from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import numpy as np

# ---------------------------------------------------------------------------
# Core classes
# ---------------------------------------------------------------------------

@dataclass
class Agent:
    """
    A distributed energy agent on a network node.

    state x_i ∈ [-1, 1]:
        -1 = discharge hard
         0 = idle
        +1 = charge hard

    This is not a physical quantity — it is an internal decision variable.
    Actual power is derived via: P_i = p_max * tanh(x_i)

    Dynamics (one step):
        x_i(t+1) = (1-alpha)*x_i(t)
                 + alpha*d_i(t)
                 + k_i * sum_{j in N(i)} (x_j - x_i)

    where:
        alpha   — memory decay (how fast agent forgets past state)
        d_i(t)  — local load signal (external disturbance)
        k_i     — coupling strength (how much neighbours influence agent)
    """

    id:       int
    p_max:    float = 10.0    # kW
    capacity: float = 50.0    # kWh
    soc:      float = 0.5

    alpha:    float = 0.3     # memory decay [0, 1]
    k:        float = 1.0     # coupling strength

    state:    float = field(default=0.0)       # x_i — internal decision variable
    neighbors: List[int] = field(default_factory=list)  # neighbour agent ids

    @property
    def power_kw(self) -> float:
        """Actual power from internal state. Positive = charge, negative = discharge."""
        return self.p_max * float(np.tanh(self.state))

    def step(
        self,
        local_load:      float,
        neighbor_states: List[float],
    ) -> None:
        """
        Update internal state for one timestep.

        local_load: d_i(t) — normalised to [-1, 1].
        neighbor_states: x_j for each j in N(i).
        """
        consensus = sum(ns - self.state for ns in neighbor_states)
        self.state = (
            (1.0 - self.alpha) * self.state
            + self.alpha * local_load
            + self.k * consensus
        )
        # Clamp to [-1, 1]
        self.state = float(np.clip(self.state, -1.0, 1.0))


@dataclass
class Edge:
    """
    Directed information edge from source to target.

    weight w_ij: how strongly agent j influences agent i.
    Default 1.0 — uniform coupling.
    """
    source: int
    target: int
    weight: float = 1.0


@dataclass
class Network:
    """
    A collection of agents connected by edges.

    Stores adjacency as both edge list and dict for fast lookup.
    """
    agents: Dict[int, Agent] = field(default_factory=dict)
    edges:  List[Edge]       = field(default_factory=list)

    def add_agent(self, agent: Agent) -> None:
        self.agents[agent.id] = agent

    def add_edge(self, source: int, target: int, weight: float = 1.0) -> None:
        self.edges.append(Edge(source, target, weight))
        # Undirected — add both directions
        if target not in self.agents[source].neighbors:
            self.agents[source].neighbors.append(target)
        if source not in self.agents[target].neighbors:
            self.agents[target].neighbors.append(source)

    def neighbor_states(self, agent_id: int) -> List[float]:
        return [self.agents[j].state for j in self.agents[agent_id].neighbors]

    def step(self, local_loads: Dict[int, float]) -> None:
        """
        Advance all agents one timestep simultaneously.
        All agents read neighbour states BEFORE anyone updates — simultaneous decisions.
        """
        neighbor_states_snapshot = {
            aid: self.neighbor_states(aid)
            for aid in self.agents
        }
        for aid, agent in self.agents.items():
            agent.step(
                local_load      = local_loads.get(aid, 0.0),
                neighbor_states = neighbor_states_snapshot[aid],
            )

    def adjacency_matrix(self) -> np.ndarray:
        n = len(self.agents)
        ids = sorted(self.agents.keys())
        idx = {aid: i for i, aid in enumerate(ids)}
        A = np.zeros((n, n))
        for edge in self.edges:
            i, j = idx[edge.source], idx[edge.target]
            A[i, j] = edge.weight
            A[j, i] = edge.weight
        return A

    def state_vector(self) -> np.ndarray:
        return np.array([self.agents[aid].state for aid in sorted(self.agents)])

    def power_vector(self) -> np.ndarray:
        return np.array([self.agents[aid].power_kw for aid in sorted(self.agents)])


# ---------------------------------------------------------------------------
# Topology factory functions
# ---------------------------------------------------------------------------

def make_linear(n: int, k: float = 1.0, alpha: float = 0.3) -> Network:
    """
    Linear chain: 0 -- 1 -- 2 -- ... -- n-1
    Each agent connected to left and right neighbours only.
    """
    net = Network()
    for i in range(n):
        net.add_agent(Agent(id=i, k=k, alpha=alpha))
    for i in range(n - 1):
        net.add_edge(i, i + 1)
    return net


def make_star(n: int, k: float = 1.0, alpha: float = 0.3) -> Network:
    """
    Star: agent 0 is hub, connected to all others.
    Agents 1..n-1 are leaves, connected only to hub.
    """
    net = Network()
    for i in range(n):
        net.add_agent(Agent(id=i, k=k, alpha=alpha))
    for i in range(1, n):
        net.add_edge(0, i)
    return net


def make_small_world(
    n:     int,
    k_nn:  int   = 4,      # each node connected to k_nn nearest neighbours
    p:     float = 0.1,    # rewiring probability
    k:     float = 1.0,
    alpha: float = 0.3,
    seed:  int   = 42,
) -> Network:
    """
    Watts-Strogatz small-world network.

    Start with a ring where each node is connected to k_nn nearest neighbours.
    Rewire each edge with probability p to a random node.

    Low p  → regular lattice (local clusters, long paths)
    High p → random graph (short paths, no clusters)
    p ≈ 0.1 → small-world (local clusters AND short paths)
    """
    rng = random.Random(seed)
    net = Network()
    for i in range(n):
        net.add_agent(Agent(id=i, k=k, alpha=alpha))

    # Build initial ring
    connections: List[Tuple[int, int]] = []
    for i in range(n):
        for j in range(1, k_nn // 2 + 1):
            target = (i + j) % n
            connections.append((i, target))

    # Rewire
    for i, target in connections:
        if rng.random() < p:
            new_target = rng.randint(0, n - 1)
            # Avoid self-loops and duplicates
            attempts = 0
            while (new_target == i or new_target in net.agents[i].neighbors) and attempts < n:
                new_target = rng.randint(0, n - 1)
                attempts += 1
            if new_target != i and new_target not in net.agents[i].neighbors:
                net.add_edge(i, new_target)
        else:
            if target not in net.agents[i].neighbors:
                net.add_edge(i, target)

    return net