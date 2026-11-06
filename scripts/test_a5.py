#!/usr/bin/env python3
"""Test A5: causal inversion detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.tribunal_multimetrico import TribunalMultimetrico

t = TribunalMultimetrico(kappa_d=0.56, kappa_r=0.15)

# A5: causal inversion
src = "La hiperglucemia crónica causó la neuropatía periférica del paciente, que requirió amputación del dedo."
rsp = "La neuropatía periférica del paciente causó la hiperglucemia crónica, que requirió amputación del dedo."

v = t.evaluar(src, rsp)
print(f"A5: ISI={v.isi_final:.4f} Zona={v.zona}")
for m in v.modulos_disparados:
    if "source_target" in m.nombre:
        print(f"  STG: {m.descripcion}")
print(f"  Fired: {[m.nombre for m in v.modulos_disparados]}")
print(f"  PASS: {v.zona == 'COLAPSO_ESTRUCTURAL'}")

# Also test B1 (reordering) is NOT affected
print()
src_b1 = "El paciente presenta hiperglucemia persistente. Fue tratado con insulina glargina 30 unidades nocturnas. A las 4 semanas la HbA1c descendió de 9.2% a 7.1%."
rsp_b1 = "A las 4 semanas la HbA1c descendió de 9.2% a 7.1%. Fue tratado con insulina glargina 30 unidades nocturnas. El paciente presenta hiperglucemia persistente."
v2 = t.evaluar(src_b1, rsp_b1)
print(f"B1 (reordering): ISI={v2.isi_final:.4f} Zona={v2.zona}")
print(f"  Fired: {[m.nombre for m in v2.modulos_disparados]}")
print(f"  PASS (should NOT be COLAPSO): {v2.zona != 'COLAPSO_ESTRUCTURAL'}")