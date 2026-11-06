#!/usr/bin/env python3
"""Test A3: drug name mutation detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.tribunal_multimetrico import TribunalMultimetrico

t = TribunalMultimetrico(kappa_d=0.56, kappa_r=0.15)

# A3: amlodipino -> losartan
src = "La combinación de enalapril y amlodipino redujo la presión arterial sistólica en 18 mmHg a las 12 semanas."
rsp = "La combinación de enalapril y losartán redujo la presión arterial sistólica en 18 mmHg a las 12 semanas."

v = t.evaluar(src, rsp)
print(f"A3: ISI={v.isi_final:.4f} Zona={v.zona}")
for m in v.modulos_disparados:
    if "source_target" in m.nombre:
        print(f"  STG: {m.descripcion}")
print(f"  Fired: {[m.nombre for m in v.modulos_disparados]}")
print(f"  PASS: {v.zona == 'COLAPSO_ESTRUCTURAL'}")

# Also test that B3 (synonyms) is NOT affected
print()
src_b3 = "El paciente presenta hiperglucemia persistente con valores de glucosa en ayunas de 210 mg/dL."
rsp_b3 = "El paciente presenta niveles elevados de glucosa de forma sostenida, con valores de glucosa en ayunas de 210 mg/dL."
v2 = t.evaluar(src_b3, rsp_b3)
print(f"B3 (synonyms): ISI={v2.isi_final:.4f} Zona={v2.zona}")
print(f"  Fired: {[m.nombre for m in v2.modulos_disparados]}")
print(f"  PASS (should NOT be COLAPSO): {v2.zona != 'COLAPSO_ESTRUCTURAL'}")