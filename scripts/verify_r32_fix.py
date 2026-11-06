#!/usr/bin/env python3
"""Verify R3.2 fingerprint gate fix works end-to-end."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.tribunal_multimetrico import TribunalMultimetrico

t = TribunalMultimetrico(kappa_d=0.56, kappa_r=0.15)

# Test: hallucination that was being rescued before
src = "El paciente fue tratado con captopril 25 mg cada 8 horas durante 6 semanas."
rsp = "El paciente fue tratado con captopril 250 mg cada 8 horas durante 6 semanas."

v = t.evaluar(src, rsp)
print(f"ISI={v.isi_final:.4f} Zona={v.zona} ({v.codigo_zona})")
for m in v.modulos_disparados:
    if "r3_2" in m.nombre:
        print(f"  R3.2: {m.descripcion}")
r32_fired = any("r3_2" in m.nombre for m in v.modulos_disparados)
print(f"  R3.2 fired: {r32_fired}")
print()

# Quick ablation: count R3.2 RESCUEs on 100 MedHallu A_B pairs
records = []
with open(r"C:\Users\conno\Downloads\SAS-Semántico\reports\pairs_medico_medhallu_10k.jsonl", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= 100: break
        records.append(json.loads(line))

rescues_before = 0
rescues_after = 0
for rec in records:
    a, b = rec["A"], rec["B"]
    v = t.evaluar(a, b)
    for m in v.modulos_disparados:
        if "r3_2" in m.nombre and "RESCUE" in m.descripcion:
            rescues_after += 1

print(f"R3.2 RESCUEs on 100 A_B pairs (with fingerprint gate): {rescues_after}")
print("Expected: 0 (all hallucination rescues blocked by fingerprint gate)")
print("PASS" if rescues_after == 0 else "FAIL - some rescues still getting through")