#!/usr/bin/env python3
"""
eval_medhallu.py — SAS Multimetric Tribunal v1.3.0 on MedHallu (4-condition protocol)
═══════════════════════════════════════════════════════════════════════════════

Evaluates the 13-module tribunal over the MedHallu medical corpus using the
same 4-condition protocol as the N1 control (n1_control.py):

  A_A    : A vs A            [identity]        → must be ISI 1.0000
  A_Ap   : A vs A'           [correct answer]  → clean negative, should be COHERENTE
  A_B    : A vs B            [hallucination]   → positive, should be detected
  A_App  : A vs A''          [context + B]     → format-controlled positive

The decisive comparison is A→A'' vs A→A': identical format, only content
differs. Any ISI gap between them is attributable to content, not format.

Input:  reports/pairs_medico_medhallu_10k.jsonl  (10,000 records, 4 variants each)
Output: reports/eval_medhallu_FULL.json

Usage:
    python scripts/eval_medhallu.py --limit 500
    python scripts/eval_medhallu.py --all
    python scripts/eval_medhallu.py --all --output reports/eval_medhallu_FULL.json

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
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
KAPPA_D = 0.56
KAPPA_R = 0.15

DEFAULT_INPUT = Path(r"C:\Users\conno\Downloads\SAS-Semántico\reports\pairs_medico_medhallu_10k.jsonl")

CONDITIONS = ["A_A", "A_Ap", "A_B", "A_App"]

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
# LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_records(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load MedHallu records (JSONL)."""
    if not path.exists():
        raise FileNotFoundError(f"MedHallu JSONL not found: {path}")

    records: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not all(r.get(k) for k in ("A", "A_prime", "B", "A_pp")):
                continue
            records.append(r)
            if limit and len(records) >= limit:
                break
    return records


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def evaluate(
    tribunal: TribunalMultimetrico,
    records: List[Dict[str, Any]],
    verbose: bool = False,
) -> Dict[str, Any]:
    """Evaluate the 4 conditions over all records."""

    n = len(records)
    print(f"\n{'='*72}")
    print(f"  MedHallu — {n} records × 4 conditions = {n*4} evaluations")
    print(f"{'='*72}")

    # Per-condition accumulators
    isi: Dict[str, List[float]] = {c: [] for c in CONDITIONS}
    zones: Dict[str, Counter] = {c: Counter() for c in CONDITIONS}
    fires: Dict[str, Counter] = {c: Counter() for c in CONDITIONS}
    latencies: List[float] = []

    # Per-pair records
    pair_records: List[Dict[str, Any]] = []

    # Identity check
    identity_failures: List[str] = []

    t_start = time.perf_counter()

    for i, rec in enumerate(records):
        pid = rec.get("id", f"idx{i}")
        a = rec["A"]
        a_prime = rec["A_prime"]
        b = rec["B"]
        a_pp = rec["A_pp"]

        texts = {
            "A_A": (a, a),
            "A_Ap": (a, a_prime),
            "A_B": (a, b),
            "A_App": (a, a_pp),
        }

        row: Dict[str, Any] = {
            "id": pid,
            "split": rec.get("split"),
            "difficulty": rec.get("difficulty"),
            "category": rec.get("category"),
        }

        for cond in CONDITIONS:
            src, rsp = texts[cond]
            t0 = time.perf_counter()
            v = tribunal.evaluar(src, rsp, request_id=f"{pid}-{cond}")
            latencies.append((time.perf_counter() - t0) * 1000)

            isi[cond].append(v.isi_final)
            zones[cond][v.codigo_zona] += 1
            for m in v.modulos_disparados:
                fires[cond][m.nombre] += 1

            row[f"isi_{cond}"] = round(v.isi_final, 6)
            row[f"zona_{cond}"] = v.codigo_zona
            row[f"fired_{cond}"] = [m.nombre for m in v.modulos_disparados]

            if cond == "A_A" and abs(v.isi_final - 1.0) > 1e-6:
                identity_failures.append(f"{pid}: ISI={v.isi_final:.6f}")

        # R3 raw values from the A_App condition (the format-controlled positive)
        row["r3_3_drift"] = round(v.r3_3_drift, 6)
        row["r3_4_entropy"] = round(v.r3_4_entropy, 6)
        row["r3_5_kolmogorov"] = round(v.r3_5_kolmogorov, 6)
        row["r3_6_surprisal"] = round(v.r3_6_surprisal, 6)

        pair_records.append(row)

        if verbose and (i + 1) % 250 == 0:
            print(f"    ... {i+1}/{n} records")

    elapsed = time.perf_counter() - t_start

    # ── Detection metrics ────────────────────────────────────────────────
    #
    # METHODOLOGICAL NOTE — why A→A' is NOT used as the negative class:
    #
    # In MedHallu, A' (the ground-truth answer alone) is a strict substring of
    # A in 100% of records and measures only ~15% of A's length. The lexical
    # baseline is Jaccard, which divides by the union of token sets, so any
    # short-vs-long comparison scores low regardless of content. Flagging
    # A→A' therefore measures length asymmetry, not hallucination.
    #
    # This is a documented property of the corpus, not a tribunal defect: the
    # N1 control (n1_control.py) reports the same effect (87.2% of A→A' pairs
    # flagged) and the paper reports it in tab:cre-by-condition.
    #
    # The valid format-controlled comparison is A→A'' vs A→A:
    #   A    = Question + Knowledge + Ground Truth      (correct, full format)
    #   A''  = Question + Knowledge + Hallucinated      (hallucinated, full format)
    # Both are ~equal length (A''/A = 0.97), so any ISI gap is attributable to
    # content. A→A is the identity control (must be 1.0000).
    #
    # We therefore report three separate quantities:
    #   1. identity_control      : A→A flag rate (must be 0%)
    #   2. format_controlled     : A→A'' detection rate (the headline number)
    #   3. length_artifact       : A→A' flag rate (documented limitation)
    #   4. short_hallucination   : A→B detection rate (B is also short)

    def rate(vals: List[float], threshold: float = KAPPA_D) -> Dict[str, Any]:
        flagged = sum(1 for x in vals if x < threshold)
        return {
            "flagged": flagged,
            "total": len(vals),
            "rate": round(flagged / len(vals), 4) if vals else 0.0,
        }

    metrics = {
        "identity_control_A_A": rate(isi["A_A"]),
        "format_controlled_A_App": rate(isi["A_App"]),
        "length_artifact_A_Ap": rate(isi["A_Ap"]),
        "short_hallucination_A_B": rate(isi["A_B"]),
        # Format-controlled contrast: same length, different content.
        # This is the decisive measurement for MedHallu.
        "format_controlled_contrast": {
            "isi_A_App_mean": round(statistics.mean(isi["A_App"]), 4) if isi["A_App"] else 0.0,
            "isi_A_A_mean": round(statistics.mean(isi["A_A"]), 4) if isi["A_A"] else 0.0,
            "gap": round(
                (statistics.mean(isi["A_A"]) - statistics.mean(isi["A_App"])), 4
            ) if isi["A_A"] and isi["A_App"] else 0.0,
        },
    }

    # ── ISI distributions ────────────────────────────────────────────────
    def dist(vals: List[float]) -> Dict[str, float]:
        if not vals:
            return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0,
                    "p05": 0.0, "p25": 0.0, "p75": 0.0, "p95": 0.0}
        s = sorted(vals)
        def pct(p: float) -> float:
            return round(s[min(len(s) - 1, int(len(s) * p))], 4)
        return {
            "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "p05": pct(0.05),
            "p25": pct(0.25),
            "p75": pct(0.75),
            "p95": pct(0.95),
        }

    isi_dist = {c: dist(isi[c]) for c in CONDITIONS}

    # ── Per-module firing ────────────────────────────────────────────────
    module_stats: Dict[str, Dict[str, Any]] = {}
    for mod in MODULE_NAMES:
        entry: Dict[str, Any] = {}
        for c in CONDITIONS:
            cnt = fires[c].get(mod, 0)
            entry[f"fires_{c}"] = cnt
            entry[f"rate_{c}"] = round(cnt / n, 4) if n else 0.0
        # Discriminative power: A_App (format-controlled positive) minus A_Ap (negative)
        entry["discriminative_A_App_vs_A_Ap"] = round(
            (fires["A_App"].get(mod, 0) - fires["A_Ap"].get(mod, 0)) / n, 4
        ) if n else 0.0
        module_stats[mod] = entry

    # ── Latency ──────────────────────────────────────────────────────────
    lat_sorted = sorted(latencies)
    latency = {
        "mean": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "median": round(statistics.median(latencies), 2) if latencies else 0.0,
        "p95": round(lat_sorted[int(len(lat_sorted) * 0.95)], 2) if latencies else 0.0,
        "p99": round(lat_sorted[int(len(lat_sorted) * 0.99)], 2) if latencies else 0.0,
    }

    result = {
        "dataset": "medico_medhallu",
        "n_records": n,
        "n_evaluations": n * 4,
        "conditions": CONDITIONS,
        "kappa_d": KAPPA_D,
        "kappa_r": KAPPA_R,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": metrics,
        "isi_distribution": isi_dist,
        "zones": {c: dict(zones[c]) for c in CONDITIONS},
        "module_stats": module_stats,
        "latency_ms": latency,
        "elapsed_seconds": round(elapsed, 2),
        "identity_failures": identity_failures[:20],
        "identity_failure_count": len(identity_failures),
        "records": pair_records,
    }

    # ── Print summary ────────────────────────────────────────────────────
    print(f"\n  Identity check (A→A must be ISI 1.0000):")
    if identity_failures:
        print(f"    FAILED: {len(identity_failures)} pairs")
        for f in identity_failures[:5]:
            print(f"      {f}")
    else:
        print(f"    OK: {n}/{n} pairs at ISI 1.0000")

    print(f"\n  ISI distribution by condition:")
    for c in CONDITIONS:
        d = isi_dist[c]
        print(f"    {c:6s} mean={d['mean']:.4f}  median={d['median']:.4f}  "
              f"p05={d['p05']:.4f}  p95={d['p95']:.4f}  min={d['min']:.4f}")

    print(f"\n  Zones by condition:")
    for c in CONDITIONS:
        print(f"    {c:6s} {dict(zones[c])}")

    print(f"\n  Detection metrics:")
    print(f"    Identity control   A→A   : {metrics['identity_control_A_A']['flagged']}/"
          f"{metrics['identity_control_A_A']['total']} flagged "
          f"({metrics['identity_control_A_A']['rate']:.2%})  [must be 0%]")
    print(f"    Format-controlled  A→A'' : {metrics['format_controlled_A_App']['flagged']}/"
          f"{metrics['format_controlled_A_App']['total']} detected "
          f"({metrics['format_controlled_A_App']['rate']:.2%})  [HEADLINE]")
    print(f"    Short halluc.      A→B   : {metrics['short_hallucination_A_B']['flagged']}/"
          f"{metrics['short_hallucination_A_B']['total']} detected "
          f"({metrics['short_hallucination_A_B']['rate']:.2%})")
    print(f"    Length artifact    A→A'  : {metrics['length_artifact_A_Ap']['flagged']}/"
          f"{metrics['length_artifact_A_Ap']['total']} flagged "
          f"({metrics['length_artifact_A_Ap']['rate']:.2%})  [documented limitation]")
    fc = metrics["format_controlled_contrast"]
    print(f"\n    Format-controlled contrast: ISI(A→A)={fc['isi_A_A_mean']:.4f} vs "
          f"ISI(A→A'')={fc['isi_A_App_mean']:.4f}  gap={fc['gap']:+.4f}")

    print(f"\n  Module firing rates (A_A / A_Ap / A_B / A_App):")
    for mod in MODULE_NAMES:
        s = module_stats[mod]
        print(f"    {mod:24s} {s['rate_A_A']:6.2%} / {s['rate_A_Ap']:6.2%} / "
              f"{s['rate_A_B']:6.2%} / {s['rate_A_App']:6.2%}  "
              f"(disc {s['discriminative_A_App_vs_A_Ap']:+7.2%})")

    print(f"\n  Latency: mean={latency['mean']:.2f}ms  median={latency['median']:.2f}ms  "
          f"p95={latency['p95']:.2f}ms  p99={latency['p99']:.2f}ms")
    print(f"  Elapsed: {elapsed:.1f}s")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate SAS Tribunal v1.3.0 on MedHallu (4-condition protocol)"
    )
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT),
                        help="MedHallu JSONL path")
    parser.add_argument("--limit", type=int, default=None, help="Max records")
    parser.add_argument("--all", action="store_true", help="All 10,000 records")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    parser.add_argument("--no-records", action="store_true", help="Omit per-pair records")
    parser.add_argument("--verbose", action="store_true", help="Progress output")
    args = parser.parse_args()

    limit = None if args.all else (args.limit or 500)

    print("=" * 72)
    print("  SAS MULTIMETRIC TRIBUNAL v1.3.0 — MEDHALLU EVALUATION")
    print("=" * 72)
    print(f"  Input   : {args.input}")
    print(f"  Limit   : {limit or 'all records'}")
    print(f"  κD      : {KAPPA_D}  |  κR: {KAPPA_R}")
    print(f"  Protocol: 4 conditions (A_A, A_Ap, A_B, A_App)")

    records = load_records(Path(args.input), limit)
    print(f"  Loaded  : {len(records)} records")

    tribunal = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)
    result = evaluate(tribunal, records, verbose=args.verbose)

    if args.no_records:
        result.pop("records", None)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n  Report written: {out}  ({out.stat().st_size:,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
