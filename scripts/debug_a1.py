#!/usr/bin/env python3
"""Debug A1: why doesn't source_target_guard detect 25->250mg?"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.tribunal_multimetrico import TribunalMultimetrico

src = "El paciente fue tratado con captopril 25 mg cada 8 horas durante 6 semanas. La glucosa en ayunas se mantuvo en 140 mg/dL."
rsp = "El paciente fue tratado con captopril 250 mg cada 8 horas durante 6 semanas. La glucosa en ayunas se mantuvo en 140 mg/dL."

# Debug: check quantity extraction
quantity_pattern = re.compile(
    r'\b(\d+)\s*(?:million|billion|thousand|mg|kg|km|%)?\b',
    re.IGNORECASE
)
print("=== QUANTITY EXTRACTION ===")
print(f"Source quantities: {quantity_pattern.findall(src)}")
print(f"Response quantities: {quantity_pattern.findall(rsp)}")

qa = set(quantity_pattern.findall(src))
qb = set(quantity_pattern.findall(rsp))
print(f"Source set: {qa}")
print(f"Response set: {qb}")

nums_a = {int(q[0]) for q in qa if q[0].isdigit()}
nums_b = {int(q[0]) for q in qb if q[0].isdigit()}
print(f"Source nums: {nums_a}")
print(f"Response nums: {nums_b}")
print(f"nums_mutados: {nums_a - nums_b}")
print(f"nums_nuevos: {nums_b - nums_a}")

# Now run tribunal
t = TribunalMultimetrico(kappa_d=0.56, kappa_r=0.15)
v = t.evaluar(src, rsp)
print(f"\n=== TRIBUNAL VERDICT ===")
print(f"ISI={v.isi_final:.4f} Zona={v.zona}")
print(f"Modules fired: {[m.nombre for m in v.modulos_disparados]}")
print(f"STG value: {v.source_target_guard:.4f}")

# Check if STG fired by looking at all evidence
for m in v.todas_las_evidencias:
    if "source_target" in m.nombre:
        print(f"STG: valor={m.valor:.4f} disparo={m.disparo} desc={m.descripcion}")