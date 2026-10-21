#!/usr/bin/env python3
"""Reproduce every plot of the README.

  python experiments.py            # full run (~1-2 min)
  python experiments.py --quick    # fewer seeds, for a smoke test

Experiments
  1. scale      : hosts / switches / links as a function of k                    (basic)
  2. failures   : reachability, path length and ECMP path diversity vs. failure rate (advanced)
  3. multi_fail : #switches with >= 2 failed links at 1% failures vs. k, simulation
                  vs. closed-form Binomial prediction                              (intermediate)
Results go to results/*.csv and results/*.png.
"""
from __future__ import annotations

import argparse
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from draw import draw
from fattree import FatTree, sample_failures
from metrics import (expected_switches_with_multiple_failures, host_pair_metrics,
                     switches_with_multiple_failures)

OUT = "results"
plt.rcParams.update({"figure.dpi": 130, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.spines.top": False, "axes.spines.right": False})
PALETTE = ["#1971c2", "#e8590c", "#2b8a3e", "#862e9c"]


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ---------------------------------------------------------------- experiment 1
def exp_scale():
    ks = list(range(4, 50, 4))
    rows = [[k, *(FatTree(k).summary()[c] for c in ("hosts", "switches", "core_switches", "links"))]
            for k in ks]
    write_csv("scale.csv", ["k", "hosts", "switches", "core_switches", "links"], rows)

    a = np.array(rows)
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for col, label, c in ((1, "hosts  (k³/4)", PALETTE[0]), (4, "links  (3k³/4)", PALETTE[1]),
                          (2, "switches  (5k²/4)", PALETTE[2])):
        ax.loglog(a[:, 0], a[:, col], "o-", label=label, color=c, ms=4)
    for k in (24, 48):
        h = k**3 // 4
        ax.annotate(f"k={k}: {h:,} hosts", (k, h), textcoords="offset points",
                    xytext=(-90, 8), fontsize=8)
    ax.set_xlabel("switch port count k (log)")
    ax.set_ylabel("count (log)")
    ax.set_title("Fat-tree size vs. switch port count")
    ax.set_xticks(ks[::2], [str(k) for k in ks[::2]])
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "scale.png"))
    plt.close(fig)
    return rows


# ---------------------------------------------------------------- experiment 2
def exp_failures(seeds):
    ks = [4, 8, 16, 24]
    rates = np.round(np.arange(0, 0.51, 0.05), 2)
    keys = ["reachable_fraction", "avg_path_length", "ecmp_fraction", "full_ecmp_pair_fraction"]
    rows, agg = [], {}
    for k in ks:
        topo = FatTree(k)
        for r in rates:
            vals = {key: [] for key in keys}
            for s in range(seeds):
                m = host_pair_metrics(topo, sample_failures(topo, float(r), seed=s))
                for key in keys:
                    vals[key].append(m[key])
            agg[(k, r)] = {key: (np.mean(v), np.std(v)) for key, v in vals.items()}
            rows.append([k, r, *(f"{agg[(k, r)][key][i]:.5f}" for key in keys for i in (0, 1))])
        print(f"  failures: k={k} done")
    write_csv("failures.csv", ["k", "failure_rate"] + [f"{key}_{s}" for key in keys for s in ("mean", "std")],
              rows)

    titles = {"reachable_fraction": "Host pairs still connected",
              "avg_path_length": "Avg. host-to-host path length (hops, connected pairs)",
              "ecmp_fraction": "Avg. inter-pod shortest paths / (k/2)²",
              "full_ecmp_pair_fraction": "Inter-pod pairs keeping ALL (k/2)² 6-hop paths"}
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5))
    for ax, key in zip(axes.flat, keys):
        for k, c in zip(ks, PALETTE):
            mean = np.array([agg[(k, r)][key][0] for r in rates])
            std = np.array([agg[(k, r)][key][1] for r in rates])
            ax.plot(rates * 100, mean, "o-", ms=3.5, color=c, label=f"k={k}")
            ax.fill_between(rates * 100, mean - std, mean + std, color=c, alpha=0.15)
        if key == "ecmp_fraction":
            ax.plot(rates * 100, (1 - rates) ** 4, "k--", lw=1, label="theory (1−r)⁴")
            ax.legend(fontsize=8)
        ax.set_title(titles[key], fontsize=10)
        ax.set_xlabel("switch-to-switch links failed (%)")
    axes[0, 0].legend()
    fig.suptitle(f"Fat-tree under random link failures (mean ± std over {seeds} seeds)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "failures.png"))
    plt.close(fig)
    return agg


# ---------------------------------------------------------------- experiment 3
def exp_multi_fail(seeds, p=0.01):
    ks = list(range(4, 50, 4))
    rows = []
    for k in ks:
        topo = FatTree(k)
        n_sw = topo.summary()["switches"]
        sims = [switches_with_multiple_failures(
            topo, sample_failures(topo, p, seed=s, model="bernoulli", include_host_links=True))
            for s in range(seeds)]
        theory = expected_switches_with_multiple_failures(k, p)
        rows.append([k, n_sw, np.mean(sims), np.std(sims), theory])
    write_csv("multi_fail.csv", ["k", "switches", "sim_mean", "sim_std", "theory"],
              [[r[0], r[1], f"{r[2]:.3f}", f"{r[3]:.3f}", f"{r[4]:.3f}"] for r in rows])

    a = np.array(rows, dtype=float)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ax1.errorbar(a[:, 0], a[:, 2], yerr=a[:, 3], fmt="o", color=PALETTE[0], ms=4,
                 capsize=3, label=f"simulation ({seeds} seeds)")
    ax1.plot(a[:, 0], a[:, 4], "-", color=PALETTE[1], label="Binomial(k, p) prediction")
    ax1.set_title("Switches with ≥ 2 failed links  (p = 1%)")
    ax1.set_xlabel("switch port count k")
    ax1.set_ylabel("number of switches")
    ax1.legend()
    ax2.plot(a[:, 0], 100 * a[:, 2] / a[:, 1], "o-", color=PALETTE[2], ms=4)
    ax2.set_title("… as a share of all switches")
    ax2.set_xlabel("switch port count k")
    ax2.set_ylabel("% of switches")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "multi_fail.png"))
    plt.close(fig)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    t = FatTree(4)
    draw(t, path=os.path.join(OUT, "topology_k4.png"), title="Fat-tree k=4 (16 hosts, 20 switches)")
    draw(t, sample_failures(t, 0.15, seed=7), os.path.join(OUT, "topology_k4_failures.png"),
         title="Fat-tree k=4 with 15% switch-to-switch links failed (red)")

    print("1/3 scale");      exp_scale()
    print("2/3 failures");   exp_failures(5 if args.quick else 20)
    print("3/3 multi_fail"); exp_multi_fail(20 if args.quick else 200)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
