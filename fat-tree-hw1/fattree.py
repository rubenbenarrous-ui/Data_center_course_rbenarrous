"""
k-ary fat-tree topology generator, following

  M. Al-Fares, A. Loukissas, A. Vahdat,
  "A scalable, commodity data center network architecture", SIGCOMM 2008.

Structure for an even switch port count k:
  * k pods, each with k/2 edge switches and k/2 aggregation switches
  * (k/2)^2 core switches
  * each edge switch connects to k/2 hosts and to all k/2 aggregation switches of its pod
  * aggregation switch number t in a pod (t = k/2 .. k-1) connects to the k/2 core
    switches of core group j = t - k/2 + 1
  * k^3/4 hosts, 5k^2/4 switches, 3k^3/4 links

Addressing follows Section 3.2 of the paper:
  * pod switch   : 10.pod.switch.1        (switch in [0, k-1], edge first, then aggregation)
  * core switch  : 10.k.j.i               (j, i in [1, k/2])
  * host         : 10.pod.switch.ID       (ID in [2, k/2 + 1])
"""
from __future__ import annotations

import json
import random

HOST, EDGE, AGG, CORE = "host", "edge", "aggregation", "core"
SWITCH_KINDS = (EDGE, AGG, CORE)


class FatTree:
    def __init__(self, k: int):
        if not isinstance(k, int) or k < 2 or k % 2:
            raise ValueError(f"k must be an even integer >= 2 (got {k!r})")
        self.k = k
        self.nodes: dict[str, dict] = {}          # name -> {kind, ip, pod}
        self.links: list[tuple[str, str]] = []    # (lower node, upper node)
        self._build()

    # ------------------------------------------------------------------ build
    def _add_node(self, name, kind, ip, pod=None):
        self.nodes[name] = {"kind": kind, "ip": ip, "pod": pod}

    def _build(self):
        k, half = self.k, self.k // 2

        # core layer: (k/2)^2 switches, grid coordinates (j, i)
        for j in range(1, half + 1):
            for i in range(1, half + 1):
                self._add_node(f"c_{j}_{i}", CORE, f"10.{k}.{j}.{i}")

        for p in range(k):
            # edge layer (switch numbers 0 .. k/2-1) + their hosts
            for s in range(half):
                edge = f"e_{p}_{s}"
                self._add_node(edge, EDGE, f"10.{p}.{s}.1", p)
                for h in range(2, half + 2):
                    host = f"h_{p}_{s}_{h}"
                    self._add_node(host, HOST, f"10.{p}.{s}.{h}", p)
                    self.links.append((host, edge))

            # aggregation layer (switch numbers k/2 .. k-1)
            for t in range(half, k):
                self._add_node(f"a_{p}_{t}", AGG, f"10.{p}.{t}.1", p)

            # edge <-> aggregation: complete bipartite graph inside the pod
            for s in range(half):
                for t in range(half, k):
                    self.links.append((f"e_{p}_{s}", f"a_{p}_{t}"))

            # aggregation <-> core: aggregation t goes to core group j
            for t in range(half, k):
                j = t - half + 1
                for i in range(1, half + 1):
                    self.links.append((f"a_{p}_{t}", f"c_{j}_{i}"))

    # ---------------------------------------------------------------- queries
    def nodes_of(self, kind: str) -> list[str]:
        return [n for n, d in self.nodes.items() if d["kind"] == kind]

    def switches(self) -> list[str]:
        return [n for n, d in self.nodes.items() if d["kind"] in SWITCH_KINDS]

    def link_kind(self, link: tuple[str, str]) -> str:
        return f"{self.nodes[link[0]]['kind']}-{self.nodes[link[1]]['kind']}"

    def adjacency(self, failed: set | None = None, switches_only: bool = False) -> dict[str, list[str]]:
        """Adjacency lists of the graph after removing `failed` links."""
        failed = failed or set()
        names = self.switches() if switches_only else list(self.nodes)
        adj = {n: [] for n in names}
        for u, v in self.links:
            if (u, v) in failed or u not in adj or v not in adj:
                continue
            adj[u].append(v)
            adj[v].append(u)
        return adj

    def summary(self) -> dict:
        kinds = {kind: len(self.nodes_of(kind)) for kind in (HOST, EDGE, AGG, CORE)}
        return {
            "k": self.k,
            "pods": self.k,
            "hosts": kinds[HOST],
            "edge_switches": kinds[EDGE],
            "aggregation_switches": kinds[AGG],
            "core_switches": kinds[CORE],
            "switches": kinds[EDGE] + kinds[AGG] + kinds[CORE],
            "links": len(self.links),
        }

    def to_dict(self, failed: set | None = None) -> dict:
        failed = failed or set()
        return {
            "summary": self.summary(),
            "nodes": [{"name": n, **d} for n, d in self.nodes.items()],
            "links": [{"a": u, "b": v, "type": self.link_kind((u, v)), "failed": (u, v) in failed}
                      for u, v in self.links],
        }

    def save_json(self, path: str, failed: set | None = None):
        with open(path, "w") as f:
            json.dump(self.to_dict(failed), f, indent=1)


# ------------------------------------------------------------------- failures
FAILURE_MODELS = ("exact", "bernoulli")


def sample_failures(topo: FatTree, rate: float, seed: int | None = None,
                    model: str = "exact", include_host_links: bool = False) -> set:
    """Return the set of failed links.

    model="exact":     exactly round(rate * N) links fail, chosen uniformly at random
                       (rate is "the percentage of failed links").
    model="bernoulli": every link fails independently with probability `rate`.

    By default only switch-to-switch links can fail (host links excluded), because a
    failed host link simply isolates one host and says nothing about the fabric.
    """
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"failure rate must be in [0, 1] (got {rate})")
    if model not in FAILURE_MODELS:
        raise ValueError(f"unknown failure model {model!r}, choose from {FAILURE_MODELS}")
    rng = random.Random(seed)
    candidates = [l for l in topo.links
                  if include_host_links or topo.nodes[l[0]]["kind"] != HOST]
    if model == "exact":
        n = int(rate * len(candidates) + 0.5)
        return set(rng.sample(candidates, n))
    return {l for l in candidates if rng.random() < rate}
