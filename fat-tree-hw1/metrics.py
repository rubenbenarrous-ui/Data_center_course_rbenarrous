"""Structural metrics for (possibly damaged) fat-trees."""
from __future__ import annotations

from collections import Counter, deque
from math import comb

from fattree import EDGE, HOST, FatTree


def bfs_shortest_paths(adj: dict, src: str):
    """BFS from src. Returns (dist, count) where count[v] = number of distinct
    shortest paths from src to v. Each node's count is final when it is dequeued,
    because all of its predecessors (one level closer) were dequeued before it."""
    dist, count = {src: 0}, {src: 1}
    queue = deque([src])
    while queue:
        u = queue.popleft()
        for v in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                count[v] = count[u]
                queue.append(v)
            elif dist[v] == dist[u] + 1:
                count[v] += count[u]
    return dist, count


def host_pair_metrics(topo: FatTree, failed: set | None = None) -> dict:
    """Exact all-pairs host metrics, computed at the edge-switch level.

    Every host hangs off exactly one edge switch, so a host pair (x, y) on edge switches
    (a, b) has path length dist(a, b) + 2 and the same number of shortest paths as (a, b).
    We therefore run one BFS per edge switch (k^2/2 BFS) instead of one per host (k^3/4),
    weighting each edge pair by (#live hosts on a) * (#live hosts on b).
    """
    failed = failed or set()
    k, half = topo.k, topo.k // 2
    adj = topo.adjacency(failed, switches_only=True)

    live = Counter()                              # live hosts per edge switch
    for host, edge in topo.links:
        if topo.nodes[host]["kind"] == HOST and (host, edge) not in failed:
            live[edge] += 1

    edges = topo.nodes_of(EDGE)
    n_hosts = len(topo.nodes_of(HOST))
    total_pairs = comb(n_hosts, 2)
    inter_total = comb(n_hosts, 2) - k * comb(n_hosts // k, 2)   # pairs in different pods

    reach = sum_len = 0
    inter_reach = sum_paths = full_ecmp = 0
    max_len = 0
    for i, a in enumerate(edges):
        na = live[a]
        if na >= 2:                                # hosts under the same edge switch
            w = comb(na, 2)
            reach += w
            sum_len += 2 * w
            max_len = max(max_len, 2)
        if na == 0:
            continue
        dist, cnt = bfs_shortest_paths(adj, a)
        pod_a = topo.nodes[a]["pod"]
        for b in edges[i + 1:]:
            nb = live[b]
            if nb == 0 or b not in dist:
                continue
            w = na * nb
            hops = dist[b] + 2
            reach += w
            sum_len += w * hops
            max_len = max(max_len, hops)
            if topo.nodes[b]["pod"] != pod_a:
                inter_reach += w
                sum_paths += w * cnt[b]
                if cnt[b] == half * half and dist[b] == 4:
                    full_ecmp += w

    ideal_paths = half * half                      # (k/2)^2 shortest paths between pods
    return {
        "reachable_fraction": reach / total_pairs if total_pairs else 1.0,
        "avg_path_length": sum_len / reach if reach else float("nan"),
        "max_path_length": max_len,
        "inter_pod_reachable_fraction": inter_reach / inter_total if inter_total else 1.0,
        "avg_shortest_paths_inter_pod": sum_paths / inter_reach if inter_reach else 0.0,
        "ecmp_fraction": (sum_paths / inter_reach) / ideal_paths if inter_reach else 0.0,
        "full_ecmp_pair_fraction": full_ecmp / inter_total if inter_total else 1.0,
    }


def failed_links_per_switch(topo: FatTree, failed: set) -> Counter:
    c = Counter()
    for u, v in failed:
        for n in (u, v):
            if topo.nodes[n]["kind"] != HOST:
                c[n] += 1
    return c


def switches_with_multiple_failures(topo: FatTree, failed: set, threshold: int = 2) -> int:
    return sum(1 for n in failed_links_per_switch(topo, failed).values() if n >= threshold)


def expected_switches_with_multiple_failures(k: int, p: float, threshold: int = 2,
                                             include_host_links: bool = True) -> float:
    """Closed form under the Bernoulli model: each switch has d candidate links, each
    failing independently with probability p, so #failed ~ Binomial(d, p)."""
    def p_at_least(d):
        return 1 - sum(comb(d, i) * p**i * (1 - p)**(d - i) for i in range(threshold))
    half = k // 2
    n_edge = n_agg = k * half
    n_core = half * half
    d_edge = k if include_host_links else half
    return n_edge * p_at_least(d_edge) + (n_agg + n_core) * p_at_least(k)
