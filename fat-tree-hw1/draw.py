"""Layered drawing of a fat-tree (readable up to k = 8)."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fattree import AGG, CORE, EDGE, HOST, FatTree

LEVEL = {HOST: 0, EDGE: 1, AGG: 2, CORE: 3}
COLOR = {HOST: "#9aa5b1", EDGE: "#2b8a3e", AGG: "#1971c2", CORE: "#c2255c"}


def layout(topo: FatTree) -> dict:
    k, half = topo.k, topo.k // 2
    pos, hosts = {}, topo.nodes_of(HOST)
    for x, h in enumerate(hosts):
        pos[h] = (x, LEVEL[HOST])
    width = len(hosts) - 1
    pod_w = len(hosts) / k
    for p in range(k):
        x0 = p * pod_w
        for s in range(half):
            pos[f"e_{p}_{s}"] = (x0 + (s + 0.5) * pod_w / half - 0.5, LEVEL[EDGE])
        for t in range(half, k):
            pos[f"a_{p}_{t}"] = (x0 + (t - half + 0.5) * pod_w / half - 0.5, LEVEL[AGG])
    cores = topo.nodes_of(CORE)
    for idx, c in enumerate(cores):
        pos[c] = (width * (idx + 0.5) / len(cores), LEVEL[CORE])
    return pos


def draw(topo: FatTree, failed: set | None = None, path: str = "topology.png", title: str | None = None):
    failed = failed or set()
    pos = layout(topo)
    fig, ax = plt.subplots(figsize=(max(8, len(topo.nodes_of(HOST)) * 0.35), 5))
    for u, v in topo.links:
        (x1, y1), (x2, y2) = pos[u], pos[v]
        if (u, v) in failed:
            ax.plot([x1, x2], [y1, y2], color="red", lw=1.6, ls="--", zorder=2)
        else:
            ax.plot([x1, x2], [y1, y2], color="#ced4da", lw=0.7, zorder=1)
    for kind in (HOST, EDGE, AGG, CORE):
        names = topo.nodes_of(kind)
        ax.scatter([pos[n][0] for n in names], [pos[n][1] for n in names],
                   s=40 if kind == HOST else 110, c=COLOR[kind], label=kind,
                   marker="o" if kind == HOST else "s", zorder=3, edgecolors="white")
    ax.set_yticks([0, 1, 2, 3], ["hosts", "edge", "aggregation", "core"])
    ax.set_xticks([])
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    ax.set_title(title or f"Fat-tree k={topo.k}  ({len(failed)} failed links in red)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
