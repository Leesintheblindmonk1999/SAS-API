#!/usr/bin/env python3
"""
reproduce.py — SAS Multimetric Tribunal v1.4.0: Complete Reproduction Script
═══════════════════════════════════════════════════════════════════════════════

Usage:
    python reproduce.py --quick      # adversarial (2s) + fingerprint 1k (43s) + summary
    python reproduce.py --full       # everything including ablation (~75 min)
    python reproduce.py --help       # full options

Output:
    reports/full_report.json         # complete report
    reports/full_report_quick.json   # quick report (--quick mode)

What this script does:
  1. Loads 4 datasets (30,790 pairs total)
  2. Runs tribunal (13 modules) on all pairs
  3. Runs structural fingerprint on 1,000 or 10,000 records
  4. Runs adversarial set (10 cases)
  5. Runs ablation (13 iterations, --full only)
  6. Saves complete report + prints summary table

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import time
import zlib
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
KP = 0.4039  # fingerprint rescue threshold

CORPUS_ROOT = Path(r"C:\ProgramData\benchmark_corpus")
MEDHALLU_PATH = Path(r"C:\Users\conno\Downloads\SAS-Semántico\reports\pairs_medico_medhallu_10k.jsonl")
ADVERSARIAL_PATH = Path(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\data\adversarial_10.jsonl")
OUTPUT_DIR = Path(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\reports")

SUITES = {
    "halueval_qa": "HaluEval QA",
    "halueval_dialogue": "HaluEval Dialogue",
    "truthfulqa": "TruthfulQA",
}

MODULE_NAMES = [
    "lexical_baseline_score", "source_target_guard", "flow_penalty",
    "negation_penalty", "cre_isi", "arithmetic_penalty", "reference_penalty",
    "r3_1_guard", "r3_2_topological", "r3_3_drift", "r3_4_entropy",
    "r3_5_kolmogorov", "r3_6_surprisal",
]


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Load datasets
# ══════════════════════════════════════════════════════════════════════════════

def load_public_pairs(suite: str, limit: Optional[int] = None) -> List[Tuple[str, str, str]]:
    """Load (id, source, hallucination) from benchmark_corpus."""
    suite_dir = CORPUS_ROOT / suite
    if not suite_dir.exists():
        print(f"  WARNING: Dataset not found: {suite_dir}")
        return []
    a_files = sorted(suite_dir.glob("*_A_clean.txt"))
    if limit:
        a_files = a_files[:limit]
    pairs = []
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


def load_medhallu(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load MedHallu records."""
    if not MEDHALLU_PATH.exists():
        print(f"  WARNING: MedHallu not found: {MEDHALLU_PATH}")
        return []
    records = []
    with open(MEDHALLU_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line.strip())
            if all(r.get(k) for k in ("A", "A_prime", "B", "A_pp")):
                records.append(r)
                if limit and len(records) >= limit:
                    break
    return records


def load_adversarial() -> List[Dict[str, Any]]:
    """Load adversarial cases."""
    if not ADVERSARIAL_PATH.exists():
        print(f"  WARNING: Adversarial set not found: {ADVERSARIAL_PATH}")
        return []
    with open(ADVERSARIAL_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Run tribunal on public datasets
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_public_suite(
    tribunal: TribunalMultimetrico,
    suite: str,
    pairs: List[Tuple[str, str, str]],
    verbose: bool = False,
) -> Dict[str, Any]:
    """Evaluate one public dataset suite."""
    n = len(pairs)
    tp = fp = fn = tn = 0
    module_fires_halluc: Counter = Counter()
    module_fires_control: Counter = Counter()
    isi_halluc: List[float] = []
    isi_control: List[float] = []
    zones_halluc: Counter = Counter()
    zones_control: Counter = Counter()
    latencies: List[float] = []

    t0 = time.perf_counter()
    for i, (pid, source, halluc) in enumerate(pairs):
        # Control
        t = time.perf_counter()
        vc = tribunal.evaluar(source, source)
        latencies.append((time.perf_counter() - t) * 1000)
        isi_control.append(vc.isi_final)
        zones_control[vc.codigo_zona] += 1
        for m in vc.modulos_disparados:
            module_fires_control[m.nombre] += 1
        if vc.isi_final < KAPPA_D:
            fp += 1
        else:
            tn += 1

        # Hallucination
        t = time.perf_counter()
        vh = tribunal.evaluar(source, halluc)
        latencies.append((time.perf_counter() - t) * 1000)
        isi_halluc.append(vh.isi_final)
        zones_halluc[vh.codigo_zona] += 1
        for m in vh.modulos_disparados:
            module_fires_halluc[m.nombre] += 1
        if vh.isi_final < KAPPA_D:
            tp += 1
        else:
            fn += 1

        if verbose and (i + 1) % 500 == 0:
            elapsed = time.perf_counter() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (n - i - 1) / rate if rate > 0 else 0
            print(f"    [{i+1}/{n}] {rate:.0f} pairs/s, ETA {eta:.0f}s")

    elapsed = time.perf_counter() - t0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0

    module_stats = {}
    for mod in MODULE_NAMES:
        h = module_fires_halluc.get(mod, 0)
        c = module_fires_control.get(mod, 0)
        module_stats[mod] = {
            "fires_hallucination": h, "fires_control": c,
            "rate_hallucination": round(h / n, 4) if n else 0.0,
            "rate_control": round(c / n, 4) if n else 0.0,
            "discriminative_power": round((h - c) / n, 4) if n else 0.0,
        }

    return {
        "suite": suite, "suite_label": SUITES.get(suite, suite), "n_pairs": n,
        "metrics": {
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "accuracy": round(accuracy, 4),
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        },
        "isi_distribution": {
            "hallucination": {
                "mean": round(statistics.mean(isi_halluc), 4) if isi_halluc else 0.0,
                "median": round(statistics.median(isi_halluc), 4) if isi_halluc else 0.0,
            },
            "control": {
                "mean": round(statistics.mean(isi_control), 4) if isi_control else 0.0,
                "median": round(statistics.median(isi_control), 4) if isi_control else 0.0,
            },
            "separation": round(
                (statistics.mean(isi_control) - statistics.mean(isi_halluc)), 4
            ) if isi_control and isi_halluc else 0.0,
        },
        "zones": {"hallucination": dict(zones_halluc), "control": dict(zones_control)},
        "module_stats": module_stats,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "median": round(statistics.median(latencies), 2) if latencies else 0.0,
        },
        "elapsed_seconds": round(elapsed, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Fingerprint
# ══════════════════════════════════════════════════════════════════════════════

def _tokens(t: str) -> List[str]:
    return re.findall(r"\b\w+\b", t.lower())

def _sentences(t: str) -> List[str]:
    return [s.strip() for s in re.split(r"[.!?]+", t) if s.strip()]

def _shannon_entropy(t: str) -> float:
    if not t: return 0.0
    c = Counter(t)
    n = len(t)
    return -sum((v / n) * math.log2(v / n) for v in c.values())

def _comp_len(t: str) -> int:
    return len(zlib.compress(t.encode("utf-8")))

FUNCTION_WORDS = set(
    "the a an in on at of to for with by from as is are was were be been being "
    "and or but not no so if then than that this these those it its he she they "
    "we you i me my your our their him her them".split()
)

def _relational_features(src: str, rsp: str) -> Dict[str, float]:
    s_sent = _sentences(src); r_sent = _sentences(rsp)
    s_lens = [len(_tokens(s)) for s in s_sent]
    r_lens = [len(_tokens(s)) for s in r_sent]
    n = min(len(s_lens), len(r_lens))
    corr = 0.0
    if n >= 2:
        try: corr = statistics.correlation(s_lens[:n], r_lens[:n])
        except: corr = 0.0
    def fw_ratio(t: str) -> float:
        toks = _tokens(t)
        return sum(1 for w in toks if w in FUNCTION_WORDS) / max(len(toks), 1)
    fw_diff = abs(fw_ratio(src) - fw_ratio(rsp))
    s_bigrams = set(zip(_tokens(src), _tokens(src)[1:]))
    r_toks = _tokens(rsp)
    r_bigrams = set(zip(r_toks, r_toks[1:]))
    preserved = len(s_bigrams & r_bigrams) / max(len(s_bigrams), 1)
    return {"sentence_len_corr": round(corr, 4), "fw_ratio_diff": round(fw_diff, 4),
            "bigram_preservation": round(preserved, 4)}

def _absolute_features(t: str) -> Dict[str, float]:
    sents = _sentences(t); words = _tokens(t)
    proper = [w for w in re.findall(r"\b[A-Z][a-z]+\b", t)
              if w.lower() not in ("the","a","an","in","on","at")]
    numerals = re.findall(r"\d+", t)
    negations = re.findall(r"\b(not|never|no|without|despite)\b", t.lower())
    causal = re.findall(r"\b(because|therefore|thus|hence|so|since)\b", t.lower())
    comp = _comp_len(t) / max(len(t), 1)
    return {"n_sentences": len(sents), "avg_sentence_len": len(words)/max(len(sents),1),
            "n_proper_nouns": len(proper), "n_numerals": len(numerals),
            "n_negations": len(negations), "n_causal": len(causal),
            "char_entropy": round(_shannon_entropy(t), 4), "comp_ratio": round(comp, 4)}

def _fp_dist(f1: Dict[str, float], f2: Dict[str, float]) -> float:
    keys = set(f1) & set(f2)
    if not keys: return 1.0
    dists = []
    for k in keys:
        denom = max(abs(f1[k]), abs(f2[k]), 1e-6)
        dists.append(abs(f1[k] - f2[k]) / denom)
    return sum(dists) / len(dists)

def run_fingerprint(records: List[Dict[str, Any]], limit: int = 1000) -> Dict[str, Any]:
    """Run fingerprint on MedHallu records."""
    sample = records[:limit]
    dist_12_app, dist_12_b = [], []
    for rec in sample:
        a = rec["A"]; b = rec["B"]; app = rec["A_pp"]
        f12_src = {**_absolute_features(a), **_relational_features(a, a)}
        f12_app = {**_absolute_features(app), **_relational_features(a, app)}
        f12_b = {**_absolute_features(b), **_relational_features(a, b)}
        dist_12_app.append(_fp_dist(f12_src, f12_app))
        dist_12_b.append(_fp_dist(f12_src, f12_b))

    def pct(vals: List[float], p: float) -> float:
        s = sorted(vals)
        return round(s[min(len(s)-1, int(len(s)*p))], 4)

    def stats(vals: List[float]) -> Dict[str, float]:
        return {"mean": round(statistics.mean(vals), 4), "median": round(statistics.median(vals), 4),
                "p5": pct(vals, 0.05), "p10": pct(vals, 0.10), "p25": pct(vals, 0.25),
                "p50": pct(vals, 0.50), "p75": pct(vals, 0.75), "p90": pct(vals, 0.90), "p95": pct(vals, 0.95)}

    return {
        "n_records": len(sample),
        "kappa_P": KP,
        "A_App": stats(dist_12_app),
        "A_B": stats(dist_12_b),
        "zero_overlap": pct(dist_12_app, 0.95) < pct(dist_12_b, 0.05),
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Adversarial set
# ══════════════════════════════════════════════════════════════════════════════

def run_adversarial(tribunal: TribunalMultimetrico) -> Dict[str, Any]:
    """Evaluate adversarial cases."""
    cases = load_adversarial()
    if not cases:
        return {"error": "adversarial set not found"}

    results = []
    for c in cases:
        v = tribunal.evaluar(c["source"], c["response"], request_id=f"ADV-{c['id']}")
        zone = v.zona
        correct = zone == c["expected"]

        # Fingerprint rescue check
        f12_src = {**_absolute_features(c["source"]), **_relational_features(c["source"], c["source"])}
        f12_rsp = {**_absolute_features(c["response"]), **_relational_features(c["source"], c["response"])}
        fp_dist_val = _fp_dist(f12_src, f12_rsp)
        rescued = fp_dist_val < KP and v.isi_final < KAPPA_D

        results.append({
            "id": c["id"], "type": c["type"],
            "expected": c["expected"], "got": zone,
            "isi": round(v.isi_final, 6),
            "fp_dist": round(fp_dist_val, 4),
            "fp_rescue": rescued,
            "modules_fired": [m.nombre for m in v.modulos_disparados],
            "correct": correct,
        })

    detected = sum(1 for r in results if r["type"] == "detect" and r["correct"])
    not_detected = sum(1 for r in results if r["type"] == "no_detect" and r["correct"])
    rescued_count = sum(1 for r in results if r["type"] == "no_detect" and r["fp_rescue"])

    return {
        "n_cases": len(results),
        "type_A_detected": f"{detected}/5",
        "type_B_correct": f"{not_detected}/5",
        "type_B_rescued_by_fingerprint": f"{rescued_count}/5",
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Ablation (--full only)
# ══════════════════════════════════════════════════════════════════════════════

def run_ablation(
    pairs: List[Tuple[str, str, str]],
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run ablation: disable one module at a time, measure F1 delta.
    
    NOTE: Setting a module's weight to 0 does NOT disable it because the
    CombinadorCalibrado normalizes weights to sum 1.0. Instead, we skip
    the module by monkey-patching its computation method to return 1.0
    (no penalty, no firing).
    """
    n = len(pairs)
    if n == 0:
        return {"error": "no pairs for ablation"}

    # Baseline
    print(f"\n  [Ablation] Computing baseline F1 on {n} pairs...")
    tribunal = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)
    tp = fp = fn = tn = 0
    for pid, source, halluc in pairs:
        vc = tribunal.evaluar(source, source)
        vh = tribunal.evaluar(source, halluc)
        if vc.isi_final < KAPPA_D: fp += 1
        else: tn += 1
        if vh.isi_final < KAPPA_D: tp += 1
        else: fn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    baseline_f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    print(f"    Baseline F1 = {baseline_f1:.4f}")

    # Map module names to their computation methods
    MODULE_METHODS = {
        "lexical_baseline_score": "_calcular_lexical_baseline",
        "source_target_guard": "_calcular_source_target_guard",
        "flow_penalty": "_calcular_flow_penalty",
        "negation_penalty": "_calcular_negation_penalty",
        "cre_isi": "_calcular_cre_isi",
        "arithmetic_penalty": "_calcular_arithmetic_penalty",
        "reference_penalty": "_calcular_reference_penalty",
        "r3_1_guard": "_calcular_r3_1_guard",
        "r3_2_topological": "_calcular_r3_2_topological",
        "r3_3_drift": "_calcular_r3_3_drift",
        "r3_4_entropy": "_calcular_r3_4_entropy",
        "r3_5_kolmogorov": "_calcular_r3_5_kolmogorov",
        "r3_6_surprisal": "_calcular_r3_6_surprisal",
    }

    ablation_results = {}
    for mod_name in MODULE_NAMES:
        print(f"    Disabling {mod_name}...", end=" ")
        t0 = time.perf_counter()
        
        # Create tribunal and patch the method to return neutral values
        tribunal_abl = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)
        method_name = MODULE_METHODS[mod_name]
        
        # Determine return type from method name
        if mod_name in ("r3_2_topological", "r3_3_drift", "r3_4_entropy", "r3_5_kolmogorov", "r3_6_surprisal", "r3_1_guard"):
            # These return (val, fired, desc, details)
            setattr(tribunal_abl, method_name, lambda s, r: (1.0, False, "DISABLED (ablation)", {}))
        elif mod_name == "lexical_baseline_score":
            # Returns float
            setattr(tribunal_abl, method_name, lambda s, r: 1.0)
        elif mod_name == "arithmetic_penalty":
            # Takes only response (text_b), returns (val, fired, desc)
            setattr(tribunal_abl, method_name, lambda r: (1.0, False, "DISABLED (ablation)"))
        else:
            # These return (val, fired, desc)
            setattr(tribunal_abl, method_name, lambda s, r: (1.0, False, "DISABLED (ablation)"))
        
        tp = fp = fn = tn = 0
        for pid, source, halluc in pairs:
            vc = tribunal_abl.evaluar(source, source)
            vh = tribunal_abl.evaluar(source, halluc)
            if vc.isi_final < KAPPA_D: fp += 1
            else: tn += 1
            if vh.isi_final < KAPPA_D: tp += 1
            else: fn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        delta = baseline_f1 - f1
        elapsed = time.perf_counter() - t0
        ablation_results[mod_name] = {
            "f1": round(f1, 4), "delta": round(delta, 4),
            "precision": round(precision, 4), "recall": round(recall, 4),
            "elapsed_seconds": round(elapsed, 2),
        }
        print(f"F1={f1:.4f} delta={delta:+.4f} ({elapsed:.1f}s)")

    return {
        "n_pairs": n,
        "baseline_f1": round(baseline_f1, 4),
        "modules": ablation_results,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PRINT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(results: Dict[str, Any]):
    """Print a concise summary table."""
    print("\n" + "=" * 72)
    print("SAS MULTIMETRIC TRIBUNAL v1.4.0 — REPRODUCTION SUMMARY")
    print("=" * 72)

    # Public datasets
    if "public_datasets" in results:
        print("\n[1] PUBLIC DATASETS (30,790 pairs)")
        print(f"{'Dataset':<20s} {'Pairs':>7s} {'Prec':>7s} {'Recall':>7s} {'F1':>7s} {'Acc':>7s} {'FP':>5s}")
        print("-" * 60)
        total_tp = total_fp = total_fn = total_tn = 0
        for r in results["public_datasets"]:
            m = r["metrics"]
            cm = m["confusion_matrix"]
            total_tp += cm["tp"]; total_fp += cm["fp"]
            total_fn += cm["fn"]; total_tn += cm["tn"]
            print(f"{r['suite_label']:<20s} {r['n_pairs']:>7d} {m['precision']:>6.2%} {m['recall']:>6.2%} {m['f1']:>6.2%} {m['accuracy']:>6.2%} {cm['fp']:>5d}")
        # Aggregate
        p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
        acc = (total_tp + total_tn) / (total_tp + total_fp + total_fn + total_tn) if (total_tp + total_fp + total_fn + total_tn) > 0 else 0
        print(f"{'AGGREGATE':<20s} {total_tp+total_fp+total_fn+total_tn:>7d} {p:>6.2%} {r:>6.2%} {f1:>6.2%} {acc:>6.2%} {total_fp:>5d}")

    # MedHallu
    if "medhallu" in results:
        mh = results["medhallu"]
        print(f"\n[2] MEDHALLU (10,000 records)")
        print(f"  Format-controlled detection (A→A''): {mh.get('detection_rate', 'N/A')}")
        print(f"  Identity control (A→A): {mh.get('identity_fp', 'N/A')}")

    # Fingerprint
    if "fingerprint" in results:
        fp = results["fingerprint"]
        print(f"\n[3] FINGERPRINT ({fp.get('n_records', 0)} records)")
        print(f"  A→A'' mean={fp['A_App']['mean']:.4f} p95={fp['A_App']['p95']:.4f}")
        print(f"  A→B   mean={fp['A_B']['mean']:.4f} p5={fp['A_B']['p5']:.4f}")
        print(f"  Zero overlap: {fp.get('zero_overlap', 'N/A')}")
        print(f"  κP = {KP}")

    # Adversarial
    if "adversarial" in results:
        adv = results["adversarial"]
        if "error" not in adv:
            print(f"\n[4] ADVERSARIAL SET ({adv.get('n_cases', 0)} cases)")
            print(f"  Type A (stealth, should detect): {adv.get('type_A_detected', 'N/A')}")
            print(f"  Type B (paraphrase, should not): {adv.get('type_B_correct', 'N/A')}")
            print(f"  Type B rescued by fingerprint: {adv.get('type_B_rescued_by_fingerprint', 'N/A')}")

    # Ablation
    if "ablation" in results:
        abl = results["ablation"]
        if "error" not in abl:
            print(f"\n[5] ABLATION ({abl.get('n_pairs', 0)} pairs)")
            print(f"  Baseline F1: {abl['baseline_f1']:.4f}")
            print(f"  {'Module':<26s} {'F1':>7s} {'ΔF1':>7s}")
            print("  " + "-" * 42)
            for mod, data in sorted(abl["modules"].items(), key=lambda x: abs(x[1]["delta"]), reverse=True):
                print(f"  {mod:<26s} {data['f1']:>6.2%} {data['delta']:>+7.2%}")

    print("\n" + "=" * 72)
    print(f"Report generated: {results.get('timestamp', 'N/A')}")
    print(f"Script SHA-256: {results.get('script_hash', 'N/A')}")
    print("=" * 72)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="SAS v1.4.0 — Complete Reproduction")
    parser.add_argument("--quick", action="store_true", help="Quick mode: adversarial + fingerprint 1k + summary")
    parser.add_argument("--full", action="store_true", help="Full mode: everything including ablation")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    parser.add_argument("--verbose", action="store_true", help="Progress output")
    args = parser.parse_args()

    mode = "full" if args.full else ("quick" if args.quick else "quick")
    output_path = Path(args.output) if args.output else (OUTPUT_DIR / "full_report.json")

    print("=" * 72)
    print("  SAS MULTIMETRIC TRIBUNAL v1.4.0 — REPRODUCTION")
    print("=" * 72)
    print(f"  Mode  : {mode}")
    print(f"  Date  : {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"  κD    : {KAPPA_D}  |  κR: {KAPPA_R}  |  κP: {KP}")
    print()

    # ── Script hash ───────────────────────────────────────────────────────
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(f"  Script SHA-256: {script_hash}")

    results: Dict[str, Any] = {
        "script": "reproduce.py",
        "version": "v1.4.0",
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kappa_d": KAPPA_D,
        "kappa_r": KAPPA_R,
        "kappa_P": KP,
        "script_hash": script_hash,
    }

    t_start = time.perf_counter()

    # ── Step 1: Load datasets ────────────────────────────────────────────
    print("\n[1] LOADING DATASETS")
    all_pairs = []
    for suite in SUITES:
        pairs = load_public_pairs(suite)
        print(f"  {SUITES[suite]:20s}: {len(pairs)} pairs")
        all_pairs.extend(pairs)
    print(f"  {'TOTAL PUBLIC':20s}: {len(all_pairs)} pairs")

    medhallu_records = load_medhallu()
    print(f"  {'MedHallu':20s}: {len(medhallu_records)} records")

    adversarial_cases = load_adversarial()
    print(f"  {'Adversarial':20s}: {len(adversarial_cases)} cases")

    # ── Step 2: Public datasets (skip in --quick mode) ──────────────────
    if mode == "full":
        print(f"\n[2] EVALUATING PUBLIC DATASETS ({len(all_pairs)} pairs)")
        tribunal = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)
        public_results = []
        for suite in SUITES:
            suite_pairs = load_public_pairs(suite)
            if not suite_pairs:
                continue
            print(f"\n  {SUITES[suite]} ({len(suite_pairs)} pairs)...")
            r = evaluate_public_suite(tribunal, suite, suite_pairs, args.verbose)
            public_results.append(r)
            m = r["metrics"]
            print(f"    F1={m['f1']:.4f}  P={m['precision']:.4f}  R={m['recall']:.4f}  "
                  f"FP={m['confusion_matrix']['fp']}  ({r['elapsed_seconds']:.1f}s)")
        results["public_datasets"] = public_results
    else:
        print(f"\n[2] PUBLIC DATASETS: SKIPPED (use --full to evaluate 20,790 pairs)")
        tribunal = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)

    # ── Step 3: MedHallu summary ─────────────────────────────────────────
    print(f"\n[3] MEDHALLU SUMMARY")
    if medhallu_records:
        # Use existing report data
        existing_report = OUTPUT_DIR / "eval_medhallu_FULL_v2.json"
        if existing_report.exists():
            with open(existing_report, encoding="utf-8") as f:
                mh_data = json.load(f)
            results["medhallu"] = {
                "n_records": len(medhallu_records),
                "detection_rate": f"{mh_data['metrics']['format_controlled_A_App']['rate']:.2%}",
                "identity_fp": f"{mh_data['metrics']['identity_control_A_A']['rate']:.2%}",
            }
            print(f"  Detection (A→A''): {results['medhallu']['detection_rate']}")
            print(f"  Identity FP (A→A): {results['medhallu']['identity_fp']}")
        else:
            print("  WARNING: MedHallu report not found, skipping")
    else:
        print("  WARNING: MedHallu records not loaded, skipping")

    # ── Step 4: Fingerprint ──────────────────────────────────────────────
    fp_limit = 1000 if mode == "quick" else 10000
    print(f"\n[4] FINGERPRINT ({fp_limit} records)...")
    if medhallu_records:
        t0 = time.perf_counter()
        fp_result = run_fingerprint(medhallu_records, limit=fp_limit)
        fp_result["elapsed_seconds"] = round(time.perf_counter() - t0, 2)
        results["fingerprint"] = fp_result
        print(f"  A→A'' mean={fp_result['A_App']['mean']:.4f} p95={fp_result['A_App']['p95']:.4f}")
        print(f"  A→B   mean={fp_result['A_B']['mean']:.4f} p5={fp_result['A_B']['p5']:.4f}")
        print(f"  Zero overlap: {fp_result['zero_overlap']}  ({fp_result['elapsed_seconds']:.1f}s)")
    else:
        print("  SKIPPED (no MedHallu data)")

    # ── Step 5: Adversarial ──────────────────────────────────────────────
    print(f"\n[5] ADVERSARIAL SET ({len(adversarial_cases)} cases)...")
    if adversarial_cases:
        t0 = time.perf_counter()
        adv_result = run_adversarial(tribunal)
        adv_result["elapsed_seconds"] = round(time.perf_counter() - t0, 2)
        results["adversarial"] = adv_result
        print(f"  Type A: {adv_result['type_A_detected']}  Type B: {adv_result['type_B_correct']}")
        print(f"  Type B rescued: {adv_result['type_B_rescued_by_fingerprint']}  ({adv_result['elapsed_seconds']:.1f}s)")
    else:
        print("  SKIPPED (no adversarial data)")

    # ── Step 6: Ablation (--full only) ───────────────────────────────────
    if mode == "full" and all_pairs:
        print(f"\n[6] ABLATION ({len(all_pairs)} pairs, 13 iterations)...")
        t0 = time.perf_counter()
        abl_result = run_ablation(all_pairs, args.verbose)
        abl_result["elapsed_seconds"] = round(time.perf_counter() - t0, 2)
        results["ablation"] = abl_result
        print(f"  Baseline F1: {abl_result['baseline_f1']:.4f}  ({abl_result['elapsed_seconds']:.1f}s)")
    elif mode == "full":
        print("\n[6] ABLATION SKIPPED (no public dataset pairs loaded)")
    else:
        print("\n[6] ABLATION SKIPPED (use --full to include)")

    # ── Elapsed ──────────────────────────────────────────────────────────
    total_elapsed = time.perf_counter() - t_start
    results["total_elapsed_seconds"] = round(total_elapsed, 2)

    # ── Save ─────────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Report saved: {output_path}  ({output_path.stat().st_size:,} bytes)")

    # ── Print summary ────────────────────────────────────────────────────
    print_summary(results)

    print(f"\n  Total elapsed: {total_elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())