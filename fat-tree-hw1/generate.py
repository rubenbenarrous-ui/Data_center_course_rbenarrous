#!/usr/bin/env python3
"""Command-line topology generator.

Examples
  python generate.py --k 4
  python generate.py --k 8 --failure-rate 0.1 --seed 1 --export out/k8.json --draw out/k8.png
  python generate.py --config config.example.json
  python generate.py --config config.example.json --failure-rate 0.2   # CLI overrides config
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from fattree import FAILURE_MODELS, FatTree, sample_failures
from metrics import host_pair_metrics, switches_with_multiple_failures

DEFAULTS = {
    "k": 4,
    "failure_rate": 0.0,
    "failure_model": "exact",
    "include_host_links": False,
    "seed": None,
    "export": None,
    "draw": None,
    "metrics": True,
}


def build_parser():
    p = argparse.ArgumentParser(description="Generate a k-ary fat-tree (Al-Fares et al. 2008), "
                                            "optionally with random link failures.")
    p.add_argument("--config", help="JSON config file; explicit CLI flags override its values")
    p.add_argument("--k", type=int, help="switch port count (even, >= 2). Default 4")
    p.add_argument("--failure-rate", type=float, dest="failure_rate",
                   help="fraction of links that fail, in [0, 1] (0.05 = 5%%). Default 0")
    p.add_argument("--failure-model", choices=FAILURE_MODELS, dest="failure_model",
                   help="'exact': exactly rate*N links fail; 'bernoulli': each link fails "
                        "independently with prob. rate. Default exact")
    p.add_argument("--include-host-links", action="store_true", default=None, dest="include_host_links",
                   help="allow host-edge links to fail too (default: switch-switch links only)")
    p.add_argument("--seed", type=int, help="random seed for reproducible failures")
    p.add_argument("--export", help="write topology (nodes, links, failed flags) to this JSON file")
    p.add_argument("--draw", help="save a picture of the topology (PNG), best for k <= 8")
    p.add_argument("--no-metrics", action="store_false", default=None, dest="metrics",
                   help="skip the (slower for big k) path metrics")
    return p


def resolve_config(args) -> dict:
    cfg = dict(DEFAULTS)
    if args.config:
        with open(args.config) as f:
            file_cfg = json.load(f)
        unknown = set(file_cfg) - set(DEFAULTS)
        if unknown:
            sys.exit(f"Unknown keys in config file: {sorted(unknown)}")
        cfg.update(file_cfg)
    for key in DEFAULTS:
        val = getattr(args, key, None)
        if val is not None:
            cfg[key] = val
    return cfg


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = resolve_config(args)
    try:
        topo = FatTree(cfg["k"])
        failed = sample_failures(topo, cfg["failure_rate"], cfg["seed"],
                                 cfg["failure_model"], cfg["include_host_links"])
    except ValueError as e:
        sys.exit(f"error: {e}")

    print("Configuration:", json.dumps(cfg))
    print("Topology:     ", json.dumps(topo.summary()))
    print(f"Failed links:  {len(failed)}  "
          f"(switches with >= 2 failed links: {switches_with_multiple_failures(topo, failed)})")
    if cfg["metrics"]:
        m = host_pair_metrics(topo, failed)
        print("Metrics:       " + json.dumps({k: round(v, 4) for k, v in m.items()}))

    for key in ("export", "draw"):
        if cfg[key] and os.path.dirname(cfg[key]):
            os.makedirs(os.path.dirname(cfg[key]), exist_ok=True)
    if cfg["export"]:
        topo.save_json(cfg["export"], failed)
        print("Exported to", cfg["export"])
    if cfg["draw"]:
        from draw import draw
        draw(topo, failed, cfg["draw"])
        print("Drawing saved to", cfg["draw"])


if __name__ == "__main__":
    main()
