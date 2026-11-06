#!/usr/bin/env python3
"""
extract_breakdown_app.py — Per-module firing breakdown for A→A'' (format-controlled)
═══════════════════════════════════════════════════════════════════════════════

Extracts the per-module firing rates for the A→A'' condition from the existing
MedHallu FULL report. This is the evidence that refutes the "length detector"
critique: if Jaccard does NOT fire on A→A'' (same length) while the system
still detects 85%, the detection is content-driven, not length-driven.

Usage:
    python scripts/extract_breakdown_app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPORT = Path(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\reports\eval_medhallu_FULL_v2.json")

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


def main() -> int:
    if not REPORT.exists():
        print(f"Report not found: {REPORT}")
        return 1

    d = json.loads(REPORT.read_text(encoding="utf-8"))
    ms = d["module_stats"]
    n = d["n_records"]

    print("=" * 78)
    print("PER-MODULE FIRING BREAKDOWN — A→A'' (format-controlled positive)")
    print("=" * 78)
    print(f"Dataset: {d['dataset']}  |  Records: {n}  |  κD={d['kappa_d']}  κR={d['kappa_r']}")
    print()

    # ── Table: firing rates per condition ────────────────────────────────
    print(f"{'Module':<26s} {'A_A':>7s} {'A_Ap':>7s} {'A_B':>7s} {'A_App':>7s}  {'Disc(A_App-A_Ap)':>17s}")
    print("-" * 78)
    for mod in MODULE_NAMES:
        s = ms[mod]
        print(f"{mod:<26s} {s['rate_A_A']:6.2%} {s['rate_A_Ap']:6.2%} {s['rate_A_B']:6.2%} "
              f"{s['rate_A_App']:6.2%}  {s['discriminative_A_App_vs_A_Ap']:+16.2%}")

    # ── Key evidence: which modules fire on A_App ────────────────────────
    print()
    print("=" * 78)
    print("KEY EVIDENCE — modules that fire on A_App (same length as A)")
    print("=" * 78)
    print()
    print("If lexical_baseline (Jaccard) does NOT fire on A_App (because length")
    print("is controlled), then detection on A_App is content-driven, not")
    print("length-driven. This refutes the 'length detector' critique.")
    print()

    lex = ms["lexical_baseline_score"]
    print(f"  lexical_baseline fires on A_App : {lex['rate_A_App']:.2%}")
    print(f"  lexical_baseline fires on A_Ap  : {lex['rate_A_Ap']:.2%}  (length artifact)")
    print(f"  lexical_baseline fires on A_B   : {lex['rate_A_B']:.2%}  (short hallucination)")
    print()

    # ── Modules ranked by firing on A_App ────────────────────────────────
    print("Modules ranked by firing rate on A_App (content signal):")
    ranked = sorted(MODULE_NAMES, key=lambda m: ms[m]["rate_A_App"], reverse=True)
    for i, mod in enumerate(ranked, 1):
        s = ms[mod]
        marker = "  <-- CONTENT SIGNAL" if s["rate_A_App"] > 0.10 and s["rate_A_Ap"] < 0.05 else ""
        print(f"  {i:2d}. {mod:<26s} A_App={s['rate_A_App']:6.2%}  A_Ap={s['rate_A_Ap']:6.2%}{marker}")

    # ── Detection metrics ────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("DETECTION METRICS")
    print("=" * 78)
    m = d["metrics"]
    print(f"  Identity control (A_A)      : {m['identity_control_A_A']['rate']:.2%} flagged  [must be 0%]")
    print(f"  Format-controlled (A_App)   : {m['format_controlled_A_App']['rate']:.2%} detected  [HEADLINE]")
    print(f"  Short hallucination (A→B)   : {m['short_hallucination_A_B']['rate']:.2%} detected")
    print(f"  Length artifact (A→A')      : {m['length_artifact_A_Ap']['rate']:.2%} flagged  [documented]")
    fc = m["format_controlled_contrast"]
    print(f"  Contrast: ISI(A→A)={fc['isi_A_A_mean']:.4f} vs ISI(A→A'')={fc['isi_A_App_mean']:.4f}  gap={fc['gap']:+.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())