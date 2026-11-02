#!/usr/bin/env python3
"""
eval_13_modules.py — SAS Multimetric Tribunal v1.3.0 Evaluation
═══════════════════════════════════════════════════════════════════════════════
Evaluates the 13-module tribunal over hallucination datasets and produces
a complete report with per-module firing statistics.

Datasets: halueval_qa, halueval_dialogue, truthfulqa
Format:   {id}_A_clean.txt (source) + {id}_B_hallucination.txt (response)

Metrics:
  - F1 / Precision / Recall / Accuracy (hallucination detection)
  - Per-module firing frequency (how often each of the 13 modules fires)
  - Per-module contribution to detection (fires on hallucination vs control)
  - ISI distribution by zone
  - Latency statistics

Usage:
    python eval_13_modules.py --suite halueval_qa --limit 500
    python eval_13_modules.py --all --limit 500
    python eval_13_modules.py --all --limit 500 --output reports/eval_13_modules.json

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Path setup ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from core.tribunal_multimetrico import TribunalMultimetrico  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────
CORPUS_ROOT = Path(r"C:\ProgramData\benchmark_corpus")
KAPPA_D = 0.56
KAPPA_R = 0.15

SUITES = {
    "halueval_qa": "HaluEval QA",
    "halueval_dialogue": "HaluEval Dialogue",
    "truthfulqa": "TruthfulQA",
}

# The 13 modules in display order
MODULE_NAMES = [
    "lexical_baseline_score",
    "source_target_guard",
    "flow_penalty",
    "negation_penalty",
    "cre_isi",
    "arithmetic_penalty",
    "reference_penalty",
    "r3_1_guard",
    "r3_2_topological",
    "r3_3_drift",
    "r3_4_entropy",
    "r3_5_kolmogorov",
    "r3_6_surprisal",
]


# ══════════════════════════════════════════════════════════════════════════════
# DATASET LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_pairs(suite: str, limit: Optional[int] = None) -> List[Tuple[str, str, str]]:
    """Load (id, source, hallucination) triples from a dataset suite.

    Returns list of (pair_id, source_text, hallucination_text).
    """
    suite_dir = CORPUS_ROOT / suite
    if not suite_dir.exists():
        raise FileNotFoundError(f"Dataset not found: {suite_dir}")

    a_files = sorted(suite_dir.glob("*_A_clean.txt"))
    if limit:
        a_files = a_files[:limit]

    pairs: List[Tuple[str, str, str]] = []
    for a_path in a_files:
        pair_id = a_path.name.replace("_A_clean.txt", "")
        b_path = suite_dir / f"{pair_id}_B_hallucination.txt"
        if not b_path.exists():
            continue
        try:
            source = a_path.read_text(encoding="utf-8", errors="replace").strip()
            halluc = b_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if source and halluc:
            pairs.append((pair_id, source, halluc))

    return pairs


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_suite(
    tribunal: TribunalMultimetrico,
    suite: str,
    limit: Optional[int] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Evaluate the tribunal over one dataset suite.

    For each pair we evaluate two conditions:
      - CONTROL:     (source, source)      → should be COHERENTE (A)
      - HALLUCINATION: (source, hallucination) → should be F-S or B

    Detection rule: isi_final < KAPPA_D → detected as hallucination.
    """
    pairs = load_pairs(suite, limit)
    if not pairs:
        return {"suite": suite, "error": "no pairs loaded"}

    print(f"\n{'='*70}")
    print(f"  {SUITES.get(suite, suite)} — {len(pairs)} pairs")
    print(f"{'='*70}")

    # Confusion matrix counters
    tp = fp = fn = tn = 0

    # Per-module firing counters
    module_fires_halluc: Counter = Counter()
    module_fires_control: Counter = Counter()

    # ISI distributions
    isi_halluc: List[float] = []
    isi_control: List[float] = []

    # Zone distributions
    zones_halluc: Counter = Counter()
    zones_control: Counter = Counter()

    # Latency
    latencies: List[float] = []

    # Per-pair records (compact)
    records: List[Dict[str, Any]] = []

    t_start = time.perf_counter()

    for i, (pair_id, source, halluc) in enumerate(pairs):
        # ── CONTROL: source vs source ────────────────────────────────────
        t0 = time.perf_counter()
        v_ctrl = tribunal.evaluar(source, source)
        latencies.append((time.perf_counter() - t0) * 1000)

        isi_control.append(v_ctrl.isi_final)
        zones_control[v_ctrl.codigo_zona] += 1
        for m in v_ctrl.modulos_disparados:
            module_fires_control[m.nombre] += 1

        # Control detected as hallucination = FALSE POSITIVE
        if v_ctrl.isi_final < KAPPA_D:
            fp += 1
        else:
            tn += 1

        # ── HALLUCINATION: source vs hallucination ───────────────────────
        t0 = time.perf_counter()
        v_hall = tribunal.evaluar(source, halluc)
        latencies.append((time.perf_counter() - t0) * 1000)

        isi_halluc.append(v_hall.isi_final)
        zones_halluc[v_hall.codigo_zona] += 1
        for m in v_hall.modulos_disparados:
            module_fires_halluc[m.nombre] += 1

        # Hallucination detected = TRUE POSITIVE
        if v_hall.isi_final < KAPPA_D:
            tp += 1
        else:
            fn += 1

        # Record per-pair detail
        records.append({
            "pair_id": pair_id,
            "isi_control": round(v_ctrl.isi_final, 6),
            "isi_halluc": round(v_hall.isi_final, 6),
            "zona_control": v_ctrl.codigo_zona,
            "zona_halluc": v_hall.codigo_zona,
            "fired_control": [m.nombre for m in v_ctrl.modulos_disparados],
            "fired_halluc": [m.nombre for m in v_hall.modulos_disparados],
            "r3_3_drift": round(v_hall.r3_3_drift, 6),
            "r3_4_entropy": round(v_hall.r3_4_entropy, 6),
            "r3_5_kolmogorov": round(v_hall.r3_5_kolmogorov, 6),
            "r3_6_surprisal": round(v_hall.r3_6_surprisal, 6),
        })

        if verbose and (i + 1) % 100 == 0:
            print(f"    ... {i+1}/{len(pairs)} pairs processed")

    elapsed = time.perf_counter() - t_start

    # ── Metrics ──────────────────────────────────────────────────────────
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0

    # ── Per-module statistics ────────────────────────────────────────────
    n_pairs = len(pairs)
    module_stats = {}
    for mod in MODULE_NAMES:
        h = module_fires_halluc.get(mod, 0)
        c = module_fires_control.get(mod, 0)
        module_stats[mod] = {
            "fires_hallucination": h,
            "fires_control": c,
            "rate_hallucination": round(h / n_pairs, 4) if n_pairs else 0.0,
            "rate_control": round(c / n_pairs, 4) if n_pairs else 0.0,
            "discriminative_power": round((h - c) / n_pairs, 4) if n_pairs else 0.0,
        }

    result = {
        "suite": suite,
        "suite_label": SUITES.get(suite, suite),
        "n_pairs": n_pairs,
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        },
        "isi_distribution": {
            "hallucination": {
                "mean": round(statistics.mean(isi_halluc), 4) if isi_halluc else 0.0,
                "median": round(statistics.median(isi_halluc), 4) if isi_halluc else 0.0,
                "min": round(min(isi_halluc), 4) if isi_halluc else 0.0,
                "max": round(max(isi_halluc), 4) if isi_halluc else 0.0,
            },
            "control": {
                "mean": round(statistics.mean(isi_control), 4) if isi_control else 0.0,
                "median": round(statistics.median(isi_control), 4) if isi_control else 0.0,
                "min": round(min(isi_control), 4) if isi_control else 0.0,
                "max": round(max(isi_control), 4) if isi_control else 0.0,
            },
            "separation": round(
                (statistics.mean(isi_control) - statistics.mean(isi_halluc)), 4
            ) if isi_control and isi_halluc else 0.0,
        },
        "zones": {
            "hallucination": dict(zones_halluc),
            "control": dict(zones_control),
        },
        "module_stats": module_stats,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "median": round(statistics.median(latencies), 2) if latencies else 0.0,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if latencies else 0.0,
        },
        "elapsed_seconds": round(elapsed, 2),
        "records": records,
    }

    # ── Print summary ────────────────────────────────────────────────────
    print(f"\n  Metrics:")
    print(f"    Precision : {precision:.4f}")
    print(f"    Recall    : {recall:.4f}")
    print(f"    F1        : {f1:.4f}")
    print(f"    Accuracy  : {accuracy:.4f}")
    print(f"    TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"\n  ISI separation: {result['isi_distribution']['separation']:.4f}")
    print(f"    Hallucination mean ISI: {result['isi_distribution']['hallucination']['mean']:.4f}")
    print(f"    Control mean ISI      : {result['isi_distribution']['control']['mean']:.4f}")
    print(f"\n  Zones (hallucination): {dict(zones_halluc)}")
    print(f"  Zones (control)      : {dict(zones_control)}")
    print(f"\n  Module firing rates (hallucination / control / discriminative):")
    for mod in MODULE_NAMES:
        s = module_stats[mod]
        print(
            f"    {mod:24s} {s['rate_hallucination']:6.2%} / "
            f"{s['rate_control']:6.2%} / {s['discriminative_power']:+7.2%}"
        )
    print(f"\n  Latency: mean={result['latency_ms']['mean']:.2f}ms  "
          f"median={result['latency_ms']['median']:.2f}ms  "
          f"p95={result['latency_ms']['p95']:.2f}ms")
    print(f"  Elapsed: {elapsed:.1f}s")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate SAS Multimetric Tribunal v1.3.0 (13 modules)"
    )
    parser.add_argument("--suite", choices=list(SUITES.keys()), help="Single suite to evaluate")
    parser.add_argument("--all", action="store_true", help="Evaluate all suites")
    parser.add_argument("--limit", type=int, default=None, help="Max pairs per suite")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    parser.add_argument("--verbose", action="store_true", help="Progress output")
    parser.add_argument("--no-records", action="store_true", help="Omit per-pair records")
    args = parser.parse_args()

    if not args.suite and not args.all:
        parser.error("Specify --suite <name> or --all")

    suites = list(SUITES.keys()) if args.all else [args.suite]

    print("=" * 70)
    print("  SAS MULTIMETRIC TRIBUNAL v1.3.0 — 13-MODULE EVALUATION")
    print("=" * 70)
    print(f"  Suites  : {', '.join(suites)}")
    print(f"  Limit   : {args.limit or 'all pairs'}")
    print(f"  Corpus  : {CORPUS_ROOT}")
    print(f"  κD      : {KAPPA_D}  |  κR: {KAPPA_R}")

    tribunal = TribunalMultimetrico()

    results = []
    for suite in suites:
        try:
            r = evaluate_suite(tribunal, suite, args.limit, args.verbose)
            if not args.no_records:
                pass  # records already included
            else:
                r.pop("records", None)
            results.append(r)
        except Exception as exc:
            print(f"\n  ERROR evaluating {suite}: {exc}")
            results.append({"suite": suite, "error": str(exc)})

    # ── Aggregate ────────────────────────────────────────────────────────
    valid = [r for r in results if "error" not in r]
    if valid:
        total_tp = sum(r["metrics"]["confusion_matrix"]["tp"] for r in valid)
        total_fp = sum(r["metrics"]["confusion_matrix"]["fp"] for r in valid)
        total_fn = sum(r["metrics"]["confusion_matrix"]["fn"] for r in valid)
        total_tn = sum(r["metrics"]["confusion_matrix"]["tn"] for r in valid)

        agg_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
        agg_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
        agg_f1 = (
            2 * agg_precision * agg_recall / (agg_precision + agg_recall)
            if (agg_precision + agg_recall) else 0.0
        )
        agg_accuracy = (
            (total_tp + total_tn) / (total_tp + total_fp + total_fn + total_tn)
            if (total_tp + total_fp + total_fn + total_tn) else 0.0
        )

        print("\n" + "=" * 70)
        print("  AGGREGATE (all suites)")
        print("=" * 70)
        print(f"  Precision : {agg_precision:.4f}")
        print(f"  Recall    : {agg_recall:.4f}")
        print(f"  F1        : {agg_f1:.4f}")
        print(f"  Accuracy  : {agg_accuracy:.4f}")
        print(f"  TP={total_tp}  FP={total_fp}  FN={total_fn}  TN={total_tn}")

        aggregate = {
            "precision": round(agg_precision, 4),
            "recall": round(agg_recall, 4),
            "f1": round(agg_f1, 4),
            "accuracy": round(agg_accuracy, 4),
            "confusion_matrix": {
                "tp": total_tp, "fp": total_fp, "fn": total_fn, "tn": total_tn,
            },
        }
    else:
        aggregate = {}

    # ── Write report ─────────────────────────────────────────────────────
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tribunal_version": "1.3.0",
        "modules": MODULE_NAMES,
        "n_modules": len(MODULE_NAMES),
        "kappa_d": KAPPA_D,
        "kappa_r": KAPPA_R,
        "limit_per_suite": args.limit,
        "aggregate": aggregate,
        "suites": results,
    }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Report written to: {out_path}")
    else:
        default_out = REPO_DIR / "reports" / "eval_13_modules.json"
        default_out.parent.mkdir(parents=True, exist_ok=True)
        default_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Report written to: {default_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())