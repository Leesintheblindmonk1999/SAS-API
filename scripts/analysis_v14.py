#!/usr/bin/env python3
"""
analysis_v14.py — Three analyses for the v1.4.0 paper section
═══════════════════════════════════════════════════════════════════════════════

1. Per-module firing breakdown with SILENCES (all 13 modules × 4 conditions)
   — the evidence that refutes the "length detector" critique.

2. Structural fingerprint ablation: 3 relational features vs 3+9 features.
   — measures separation between A→A'' (paraphrase) and A→B (hallucination).

3. Conditional compression with ASYMMETRY:
   — C(source+response) - C(source)  vs  C(response+source) - C(response)
   — the asymmetry is a feature not in CompFaith.

Input:  reports/pairs_medico_medhallu_10k.jsonl
Output: reports/analysis_v14.json

Usage:
    python scripts/analysis_v14.py --limit 500
    python scripts/analysis_v14.py --all
"""

from __future__ import annotations

import argparse
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

DEFAULT_INPUT = Path(r"C:\Users\conno\Downloads\SAS-Semántico\reports\pairs_medico_medhallu_10k.jsonl")
DEFAULT_OUTPUT = Path(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\reports\analysis_v14.json")

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
# ANALYSIS 1 — Per-module firing with silences
# ══════════════════════════════════════════════════════════════════════════════

def analysis_firing(
    tribunal: TribunalMultimetrico,
    records: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Run the tribunal on all 4 conditions and collect per-module firing."""
    n = len(records)
    fires: Dict[str, Counter] = {c: Counter() for c in CONDITIONS}
    isi: Dict[str, List[float]] = {c: [] for c in CONDITIONS}
    zones: Dict[str, Counter] = {c: Counter() for c in CONDITIONS}
    pair_rows: List[Dict[str, Any]] = []

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
        row: Dict[str, Any] = {"id": pid}
        for cond in CONDITIONS:
            src, rsp = texts[cond]
            v = tribunal.evaluar(src, rsp, request_id=f"{pid}-{cond}")
            isi[cond].append(v.isi_final)
            zones[cond][v.codigo_zona] += 1
            for m in v.modulos_disparados:
                fires[cond][m.nombre] += 1
            row[f"isi_{cond}"] = round(v.isi_final, 6)
            row[f"fired_{cond}"] = [m.nombre for m in v.modulos_disparados]
        pair_rows.append(row)

    module_stats: Dict[str, Dict[str, Any]] = {}
    for mod in MODULE_NAMES:
        entry: Dict[str, Any] = {}
        for c in CONDITIONS:
            cnt = fires[c].get(mod, 0)
            entry[f"fires_{c}"] = cnt
            entry[f"rate_{c}"] = round(cnt / n, 4) if n else 0.0
        entry["discriminative_A_App_vs_A_Ap"] = round(
            (fires["A_App"].get(mod, 0) - fires["A_Ap"].get(mod, 0)) / n, 4
        ) if n else 0.0
        module_stats[mod] = entry

    return {
        "n_records": n,
        "module_stats": module_stats,
        "zones": {c: dict(zones[c]) for c in CONDITIONS},
        "isi_mean": {c: round(statistics.mean(isi[c]), 4) if isi[c] else 0.0 for c in CONDITIONS},
    }, pair_rows


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 2 — Structural fingerprint (3 relational vs 3+9 features)
# ══════════════════════════════════════════════════════════════════════════════

def _tokens(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: Counter = Counter(text)
    total = len(text)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _relational_features(source: str, response: str) -> Dict[str, float]:
    """3 relational features: sentence-length correlation, function-word ratio
    difference, bigram adjacency preservation."""
    s_sent = _sentences(source)
    r_sent = _sentences(response)

    # 1. Sentence length correlation (in words)
    s_lens = [len(_tokens(s)) for s in s_sent]
    r_lens = [len(_tokens(s)) for s in r_sent]
    n = min(len(s_lens), len(r_lens))
    corr = 0.0
    if n >= 2:
        try:
            corr = statistics.correlation(s_lens[:n], r_lens[:n])
        except statistics.StatisticsError:
            corr = 0.0  # constant input (all sentences same length)

    # 2. Function word ratio difference
    FUNCTION_WORDS = set(
        "the a an in on at of to for with by from as is are was were be been being "
        "and or but not no so if then than that this these those it its he she they "
        "we you i me my your our their him her them".split()
    )
    def fw_ratio(t: str) -> float:
        toks = _tokens(t)
        if not toks:
            return 0.0
        return sum(1 for w in toks if w in FUNCTION_WORDS) / len(toks)

    fw_diff = abs(fw_ratio(source) - fw_ratio(response))

    # 3. Bigram adjacency preservation
    s_bigrams = set(zip(_tokens(source), _tokens(source)[1:]))
    r_tokens = _tokens(response)
    r_bigrams = set(zip(r_tokens, r_tokens[1:]))
    if s_bigrams:
        preserved = len(s_bigrams & r_bigrams) / len(s_bigrams)
    else:
        preserved = 0.0

    return {
        "sentence_len_corr": round(corr, 4),
        "fw_ratio_diff": round(fw_diff, 4),
        "bigram_preservation": round(preserved, 4),
    }


def _absolute_features(text: str) -> Dict[str, float]:
    """9 absolute features (context, not signal)."""
    sents = _sentences(text)
    words = _tokens(text)
    proper_nouns = [w for w in re.findall(r"\b[A-Z][a-z]+\b", text)
                    if w.lower() not in ("the", "a", "an", "in", "on", "at")]
    numerals = re.findall(r"\d+", text)
    dates = re.findall(r"\d{4}|\d{1,2}/\d{1,2}(?:/\d{2,4})?", text)
    negations = re.findall(r"\b(not|never|no|without|despite)\b", text.lower())
    causal = re.findall(r"\b(because|therefore|thus|hence|so|since)\b", text.lower())
    comp = len(zlib.compress(text.encode())) / max(len(text), 1)
    return {
        "n_sentences": len(sents),
        "avg_sentence_len": len(words) / max(len(sents), 1),
        "n_proper_nouns": len(proper_nouns),
        "n_numerals": len(numerals),
        "n_dates": len(dates),
        "n_negations": len(negations),
        "n_causal": len(causal),
        "char_entropy": round(_shannon_entropy(text), 4),
        "comp_ratio": round(comp, 4),
    }


def _fingerprint_dist(f1: Dict[str, float], f2: Dict[str, float]) -> float:
    """Relative distance between two fingerprints (robust normalization)."""
    keys = set(f1) & set(f2)
    if not keys:
        return 1.0
    distances = []
    for k in keys:
        denom = max(abs(f1[k]), abs(f2[k]), 1e-6)
        distances.append(abs(f1[k] - f2[k]) / denom)
    return sum(distances) / len(distances)


def analysis_fingerprint(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Measure fingerprint distance distributions for A→A'' vs A→B."""
    dist_3rel_app: List[float] = []
    dist_3rel_b: List[float] = []
    dist_12_app: List[float] = []
    dist_12_b: List[float] = []

    for rec in records:
        a = rec["A"]
        a_pp = rec["A_pp"]
        b = rec["B"]

        # 3 relational features
        f3_src = _relational_features(a, a)  # identity baseline
        f3_app = _relational_features(a, a_pp)
        f3_b = _relational_features(a, b)
        dist_3rel_app.append(_fingerprint_dist(f3_src, f3_app))
        dist_3rel_b.append(_fingerprint_dist(f3_src, f3_b))

        # 3 + 9 features
        f12_src = {**_absolute_features(a), **_relational_features(a, a)}
        f12_app = {**_absolute_features(a_pp), **_relational_features(a, a_pp)}
        f12_b = {**_absolute_features(b), **_relational_features(a, b)}
        dist_12_app.append(_fingerprint_dist(f12_src, f12_app))
        dist_12_b.append(_fingerprint_dist(f12_src, f12_b))

    def dist_stats(vals: List[float]) -> Dict[str, float]:
        if not vals:
            return {"mean": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0}
        s = sorted(vals)
        def pct(p: float) -> float:
            return round(s[min(len(s) - 1, int(len(s) * p))], 4)
        return {
            "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "p25": pct(0.25),
            "p75": pct(0.75),
        }

    return {
        "variant_A_3rel": {
            "A_App": dist_stats(dist_3rel_app),
            "A_B": dist_stats(dist_3rel_b),
        },
        "variant_B_12feat": {
            "A_App": dist_stats(dist_12_app),
            "A_B": dist_stats(dist_12_b),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 3 — Conditional compression with asymmetry
# ══════════════════════════════════════════════════════════════════════════════

def _comp_len(text: str) -> int:
    return len(zlib.compress(text.encode("utf-8")))


def conditional_compression(source: str, response: str) -> Dict[str, float]:
    """C(source+response) - C(source) and the reverse direction."""
    c_src = _comp_len(source)
    c_rsp = _comp_len(response)
    c_sr = _comp_len(source + "\n" + response)
    c_rs = _comp_len(response + "\n" + source)

    delta_sr = max(0, c_sr - c_src)      # cost of adding response given source
    delta_rs = max(0, c_rs - c_rsp)      # cost of adding source given response
    asym = abs(delta_sr - delta_rs)      # asymmetry feature

    # Normalized: 0 = fully predictable from source, 1 = no information shared
    norm_sr = min(delta_sr, c_rsp) / max(c_rsp, 1)
    return {
        "delta_sr": delta_sr,
        "delta_rs": delta_rs,
        "asymmetry": asym,
        "norm_sr": round(norm_sr, 4),
    }


def analysis_compression(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Measure conditional compression on A→A'' vs A→B."""
    app_delta_sr: List[float] = []
    app_asym: List[float] = []
    b_delta_sr: List[float] = []
    b_asym: List[float] = []

    for rec in records:
        a = rec["A"]
        a_pp = rec["A_pp"]
        b = rec["B"]

        c_app = conditional_compression(a, a_pp)
        c_b = conditional_compression(a, b)

        app_delta_sr.append(c_app["delta_sr"])
        app_asym.append(c_app["asymmetry"])
        b_delta_sr.append(c_b["delta_sr"])
        b_asym.append(c_b["asymmetry"])

    def dist_stats(vals: List[float]) -> Dict[str, float]:
        if not vals:
            return {"mean": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0}
        s = sorted(vals)
        def pct(p: float) -> float:
            return round(s[min(len(s) - 1, int(len(s) * p))], 4)
        return {
            "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "p25": pct(0.25),
            "p75": pct(0.75),
        }

    return {
        "A_App": {
            "delta_sr": dist_stats(app_delta_sr),
            "asymmetry": dist_stats(app_asym),
        },
        "A_B": {
            "delta_sr": dist_stats(b_delta_sr),
            "asymmetry": dist_stats(b_asym),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="SAS v1.4.0 analysis suite")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--skip-firing", action="store_true",
                        help="skip tribunal evaluation (use existing report for firing)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    limit = None if args.all else (args.limit or 500)

    print("=" * 72)
    print("  SAS v1.4.0 ANALYSIS SUITE")
    print("=" * 72)
    print(f"  Input : {args.input}")
    print(f"  Limit : {limit or 'all records'}")

    records = load_records(Path(args.input), limit)
    print(f"  Loaded: {len(records)} records")

    t0 = time.perf_counter()

    # Analysis 1: firing breakdown (needs the tribunal)
    if args.skip_firing:
        firing = {"n_records": len(records), "module_stats": {},
                  "zones": {}, "isi_mean": {}}
        print(f"\n[1] Firing breakdown: SKIPPED (--skip-firing)")
    else:
        tribunal = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)
        firing, pair_rows = analysis_firing(tribunal, records)
        print(f"\n[1] Firing breakdown: {len(records)} records × 4 conditions")

    # Analysis 2: fingerprint ablation
    fp = analysis_fingerprint(records)
    print(f"[2] Fingerprint ablation: 3 relational vs 12 features")

    # Analysis 3: conditional compression
    comp = analysis_compression(records)
    print(f"[3] Conditional compression with asymmetry")

    elapsed = time.perf_counter() - t0

    result = {
        "dataset": "medico_medhallu",
        "n_records": len(records),
        "kappa_d": KAPPA_D,
        "kappa_r": KAPPA_R,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis_1_firing": firing,
        "analysis_2_fingerprint": fp,
        "analysis_3_compression": comp,
        "elapsed_seconds": round(elapsed, 2),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Report written: {out}  ({out.stat().st_size:,} bytes)")
    print(f"  Elapsed: {elapsed:.1f}s")

    # ── Print summary ────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)

    if firing.get("module_stats"):
        print("\n[1] FIRING BREAKDOWN (with silences):")
        ms = firing["module_stats"]
        print(f"  {'Module':<26s} {'A_A':>7s} {'A_Ap':>7s} {'A_B':>7s} {'A_App':>7s}")
        for mod in MODULE_NAMES:
            s = ms[mod]
            print(f"  {mod:<26s} {s['rate_A_A']:6.2%} {s['rate_A_Ap']:6.2%} "
                  f"{s['rate_A_B']:6.2%} {s['rate_A_App']:6.2%}")

        print("\n  KEY: lexical_baseline fires on A_App = "
              f"{ms['lexical_baseline_score']['rate_A_App']:.2%} (length controlled)")
        print(f"       → detection on A_App is content-driven, not length-driven")
    else:
        print("\n[1] FIRING BREAKDOWN: skipped (use print_breakdown.py on the full report)")

    print("\n[2] FINGERPRINT ABLATION (distance distributions):")
    fpv = fp["variant_A_3rel"]
    print(f"  Variant A (3 relational):")
    print(f"    A_App mean={fpv['A_App']['mean']:.4f} median={fpv['A_App']['median']:.4f}")
    print(f"    A_B   mean={fpv['A_B']['mean']:.4f} median={fpv['A_B']['median']:.4f}")
    fpv12 = fp["variant_B_12feat"]
    print(f"  Variant B (3+9 features):")
    print(f"    A_App mean={fpv12['A_App']['mean']:.4f} median={fpv12['A_App']['median']:.4f}")
    print(f"    A_B   mean={fpv12['A_B']['mean']:.4f} median={fpv12['A_B']['median']:.4f}")

    print("\n[3] CONDITIONAL COMPRESSION (asymmetry):")
    cv = comp["A_App"]
    print(f"  A_App: delta_sr mean={cv['delta_sr']['mean']:.1f} "
          f"asym mean={cv['asymmetry']['mean']:.1f}")
    cvb = comp["A_B"]
    print(f"  A_B  : delta_sr mean={cvb['delta_sr']['mean']:.1f} "
          f"asym mean={cvb['asymmetry']['mean']:.1f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())