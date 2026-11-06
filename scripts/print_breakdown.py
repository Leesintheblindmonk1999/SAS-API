#!/usr/bin/env python3
"""Print firing breakdown from existing MedHallu report."""
import json

d = json.load(open(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\reports\eval_medhallu_FULL_v2.json", encoding="utf-8"))
ms = d["module_stats"]

print("=" * 72)
print("FIRING BREAKDOWN (with silences) — 10,000 records")
print("=" * 72)
print()
print(f"{'Module':<26s} {'A_A':>7s} {'A_Ap':>7s} {'A_B':>7s} {'A_App':>7s}")
print("-" * 60)
for mod in [
    "lexical_baseline_score", "source_target_guard", "flow_penalty",
    "negation_penalty", "cre_isi", "arithmetic_penalty", "reference_penalty",
    "r3_1_guard", "r3_2_topological", "r3_3_drift", "r3_4_entropy",
    "r3_5_kolmogorov", "r3_6_surprisal"
]:
    s = ms[mod]
    print(f"{mod:<26s} {s['rate_A_A']:6.2%} {s['rate_A_Ap']:6.2%} {s['rate_A_B']:6.2%} {s['rate_A_App']:6.2%}")

print()
lex = ms["lexical_baseline_score"]
print(f"KEY: lexical_baseline fires on A_App = {lex['rate_A_App']:.2%}")
print(f"     -> detection on A_App is content-driven, not length-driven")
print()

m = d["metrics"]
print(f"Identity control (A_A)    : {m['identity_control_A_A']['rate']:.2%} flagged")
print(f"Format-controlled (A_App) : {m['format_controlled_A_App']['rate']:.2%} detected")
print(f"Short hallucination (A_B) : {m['short_hallucination_A_B']['rate']:.2%} detected")
print(f"Length artifact (A_Ap)    : {m['length_artifact_A_Ap']['rate']:.2%} flagged")