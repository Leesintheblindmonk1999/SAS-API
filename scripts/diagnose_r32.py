#!/usr/bin/env python3
"""Diagnose R3.2: count verdicts per condition on MedHallu."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.r3_2_topological import evaluate_r3_2

records = []
with open(r"C:\Users\conno\Downloads\SAS-Semántico\reports\pairs_medico_medhallu_10k.jsonl", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= 1000:
            break
        records.append(json.loads(line))

counts = {"A_A": {}, "A_Ap": {}, "A_B": {}, "A_App": {}}
for rec in records:
    a = rec["A"]; ap = rec["A_prime"]; b = rec["B"]; app = rec["A_pp"]
    for cond, src, rsp in [("A_A", a, a), ("A_Ap", a, ap), ("A_B", a, b), ("A_App", a, app)]:
        r = evaluate_r3_2(src, rsp)
        v = r["verdict"]
        counts[cond][v] = counts[cond].get(v, 0) + 1

print("R3.2 VERDICT DISTRIBUTION (1,000 MedHallu records)")
print(f"{'Condition':<12s} {'INACTIVE':>10s} {'RESCUE':>10s} {'VETO':>10s}")
print("-" * 44)
for cond in ["A_A", "A_Ap", "A_B", "A_App"]:
    c = counts[cond]
    print(f"{cond:<12s} {c.get('INACTIVE',0):>10d} {c.get('PARAPHRASE_RESCUE',0):>10d} {c.get('CONTRADICTION_VETO',0):>10d}")

# Also check: how many RESCUEs on A_B have fp_dist < kP?
print("\nChecking fingerprint gate on A_B RESCUEs...")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.reproduce import _absolute_features, _relational_features, _fp_dist

KP = 0.4039
rescued_ab = 0
total_ab = 0
for rec in records[:1000]:
    a = rec["A"]; b = rec["B"]
    r = evaluate_r3_2(a, b)
    if r["verdict"] == "PARAPHRASE_RESCUE":
        total_ab += 1
        f12_src = {**_absolute_features(a), **_relational_features(a, a)}
        f12_rsp = {**_absolute_features(b), **_relational_features(a, b)}
        dist = _fp_dist(f12_src, f12_rsp)
        if dist < KP:
            rescued_ab += 1

print(f"  A_B RESCUEs: {total_ab}")
print(f"  Would pass fingerprint gate (fp_dist < {KP}): {rescued_ab}")
print(f"  Would be blocked by fingerprint gate: {total_ab - rescued_ab}")