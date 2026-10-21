import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fattree import AGG, CORE, EDGE, HOST, FatTree, sample_failures  # noqa: E402
from metrics import host_pair_metrics  # noqa: E402


@pytest.mark.parametrize("k", [2, 4, 6, 8, 16])
def test_counts_match_paper(k):
    s = FatTree(k).summary()
    assert s["hosts"] == k**3 // 4
    assert s["core_switches"] == (k // 2) ** 2
    assert s["edge_switches"] == s["aggregation_switches"] == k * k // 2
    assert s["switches"] == 5 * k * k // 4
    assert s["links"] == 3 * k**3 // 4


@pytest.mark.parametrize("k", [4, 8])
def test_every_switch_uses_all_k_ports(k):
    t = FatTree(k)
    adj = t.adjacency()
    for n, d in t.nodes.items():
        assert len(adj[n]) == (1 if d["kind"] == HOST else k)


def test_each_core_reaches_every_pod_once():
    t = FatTree(8)
    adj = t.adjacency()
    for c in t.nodes_of(CORE):
        pods = [t.nodes[a]["pod"] for a in adj[c]]
        assert sorted(pods) == list(range(8))


def test_addresses_unique_and_paper_format():
    t = FatTree(4)
    ips = [d["ip"] for d in t.nodes.values()]
    assert len(ips) == len(set(ips))
    assert t.nodes["c_1_1"]["ip"] == "10.4.1.1"
    assert t.nodes["e_0_0"]["ip"] == "10.0.0.1"
    assert t.nodes["a_1_2"]["ip"] == "10.1.2.1"
    assert t.nodes["h_3_1_3"]["ip"] == "10.3.1.3"


@pytest.mark.parametrize("k", [4, 6, 8])
def test_intact_metrics(k):
    m = host_pair_metrics(FatTree(k))
    assert m["reachable_fraction"] == 1.0
    assert m["max_path_length"] == 6
    assert m["avg_shortest_paths_inter_pod"] == (k // 2) ** 2
    assert m["full_ecmp_pair_fraction"] == 1.0
    # analytic average: same edge 2 hops, same pod 4, different pods 6
    H, h = k**3 // 4, k // 2
    same_edge = (k * k // 2) * h * (h - 1) / 2
    same_pod = k * (H // k) * (H // k - 1) / 2 - same_edge
    total = H * (H - 1) / 2
    expected = (2 * same_edge + 4 * same_pod + 6 * (total - same_edge - same_pod)) / total
    assert m["avg_path_length"] == pytest.approx(expected)


def test_exact_failure_count_and_reproducibility():
    t = FatTree(8)
    f1 = sample_failures(t, 0.1, seed=3)
    f2 = sample_failures(t, 0.1, seed=3)
    assert f1 == f2
    assert len(f1) == round(0.1 * 256)          # 256 switch-switch links for k=8
    assert all(t.nodes[u]["kind"] != HOST for u, _ in f1)


def test_all_links_failed_disconnects_everything():
    t = FatTree(4)
    m = host_pair_metrics(t, sample_failures(t, 1.0, seed=0))
    # only hosts under the same edge switch can still talk
    assert m["inter_pod_reachable_fraction"] == 0.0
    assert m["max_path_length"] == 2


def test_bad_k_rejected():
    for bad in (0, 3, -2, 5):
        with pytest.raises(ValueError):
            FatTree(bad)
