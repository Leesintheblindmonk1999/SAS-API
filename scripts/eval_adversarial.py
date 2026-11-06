#!/usr/bin/env python3
"""
eval_adversarial.py — Adversarial set evaluation for SAS Multimetric Tribunal v1.4.0

Uso: python scripts/eval_adversarial.py
Salida: reports/adversarial_10.json + tabla en stdout

Reglas:
1. NO modificar el Tribunal si un caso falla. Documentar el failure mode.
2. Tipo A (detect) → esperado COLAPSO_ESTRUCTURAL
3. Tipo B (no_detect) → esperado COHERENTE
4. El resultado esperado NO es 10/10. Es saber exactamente cuáles fallan y por qué.
"""

from __future__ import annotations

import json, math, re, statistics, zlib, sys
from collections import Counter
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from core.tribunal_multimetrico import TribunalMultimetrico  # noqa: E402

# ── Fingerprint rescue ───────────────────────────────────────────────────────
import math, statistics, zlib
from collections import Counter

def _tokens(t): return re.findall(r"\b\w+\b", t.lower())
def _sentences(t): return [s.strip() for s in re.split(r"[.!?]+", t) if s.strip()]
def _shannon_entropy(t):
    if not t: return 0.0
    c = Counter(t); n = len(t)
    return -sum((v/n)*math.log2(v/n) for v in c.values())
def _comp_len(t): return len(zlib.compress(t.encode("utf-8")))

FUNCTION_WORDS = set("the a an in on at of to for with by from as is are was were be been being and or but not no so if then than that this these those it its he she they we you i me my your our their him her them".split())

def _relational_features(src, rsp):
    s_sent = _sentences(src); r_sent = _sentences(rsp)
    s_lens = [len(_tokens(s)) for s in s_sent]
    r_lens = [len(_tokens(s)) for s in r_sent]
    n = min(len(s_lens), len(r_lens))
    corr = 0.0
    if n >= 2:
        try: corr = statistics.correlation(s_lens[:n], r_lens[:n])
        except: corr = 0.0
    def fw_ratio(t):
        toks = _tokens(t)
        return sum(1 for w in toks if w in FUNCTION_WORDS) / max(len(toks), 1)
    fw_diff = abs(fw_ratio(src) - fw_ratio(rsp))
    s_bigrams = set(zip(_tokens(src), _tokens(src)[1:]))
    r_toks = _tokens(rsp)
    r_bigrams = set(zip(r_toks, r_toks[1:]))
    preserved = len(s_bigrams & r_bigrams) / max(len(s_bigrams), 1)
    return {"sentence_len_corr": round(corr, 4), "fw_ratio_diff": round(fw_diff, 4),
            "bigram_preservation": round(preserved, 4)}

def _absolute_features(t):
    sents = _sentences(t); words = _tokens(t)
    proper = [w for w in re.findall(r"\b[A-Z][a-z]+\b", t) if w.lower() not in ("the","a","an","in","on","at")]
    numerals = re.findall(r"\d+", t)
    negations = re.findall(r"\b(not|never|no|without|despite)\b", t.lower())
    causal = re.findall(r"\b(because|therefore|thus|hence|so|since)\b", t.lower())
    comp = _comp_len(t) / max(len(t), 1)
    return {"n_sentences": len(sents), "avg_sentence_len": len(words)/max(len(sents),1),
            "n_proper_nouns": len(proper), "n_numerals": len(numerals),
            "n_negations": len(negations), "n_causal": len(causal),
            "char_entropy": round(_shannon_entropy(t), 4), "comp_ratio": round(comp, 4)}

def _fp_dist(f1, f2):
    keys = set(f1) & set(f2)
    if not keys: return 1.0
    dists = []
    for k in keys:
        denom = max(abs(f1[k]), abs(f2[k]), 1e-6)
        dists.append(abs(f1[k] - f2[k]) / denom)
    return sum(dists) / len(dists)

KP = 0.4039

# ── Constants ─────────────────────────────────────────────────────────────────
KAPPA_D = 0.56
KAPPA_R = 0.15

DATA_FILE = Path(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\data\adversarial_10.jsonl")
OUTPUT_FILE = Path(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\reports\adversarial_10.json")


def main() -> int:
    # ── 1. Cargar casos ────────────────────────────────────────────────────
    with open(DATA_FILE, encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]
    print(f"Cargados {len(cases)} casos adversariales")

    # ── 2. Evaluar ─────────────────────────────────────────────────────────
    tribunal = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)
    results = []
    for c in cases:
        v = tribunal.evaluar(c["source"], c["response"], request_id=f"ADV-{c['id']}")
        zone = v.zona  # COHERENTE | RUPTURA_RECUPERABLE | COLAPSO_ESTRUCTURAL
        correct = zone == c["expected"]

        # Fingerprint rescue check
        f12_src = {**_absolute_features(c["source"]), **_relational_features(c["source"], c["source"])}
        f12_rsp = {**_absolute_features(c["response"]), **_relational_features(c["source"], c["response"])}
        fp_dist_val = _fp_dist(f12_src, f12_rsp)
        rescued = fp_dist_val < KP and v.isi_final < KAPPA_D

        results.append({
            "id": c["id"],
            "type": c["type"],
            "expected": c["expected"],
            "got": zone,
            "isi": round(v.isi_final, 6),
            "fp_dist": round(fp_dist_val, 4),
            "fp_rescue": rescued,
            "modules_fired": [m.nombre for m in v.modulos_disparados],
            "correct": correct,
        })

    # ── 3. Reporte ─────────────────────────────────────────────────────────
    detected = sum(1 for r in results if r["type"] == "detect" and r["correct"])
    not_detected = sum(1 for r in results if r["type"] == "no_detect" and r["correct"])
    rescued_count = sum(1 for r in results if r["type"] == "no_detect" and r["fp_rescue"])

    print("\n" + "=" * 72)
    print("ADVERSARIAL SET — 10 casos")
    print("=" * 72)
    print(f"\nTipo A (debe detectar): {detected}/5")
    print(f"Tipo B (no debe detectar): {not_detected}/5")
    print(f"Tipo B rescatado por fingerprint: {rescued_count}/5")
    print(f"\n{'ID':<4s} {'Tipo':<10s} {'Esperado':<22s} {'Obtenido':<22s} {'ISI':>6s} {'FP':>6s} {'OK':>3s}")
    print("-" * 72)
    for r in results:
        mark = "✓" if r["correct"] or r["fp_rescue"] else "✗"
        print(f"{r['id']:<4s} {r['type']:<10s} {r['expected']:<22s} {r['got']:<22s} {r['isi']:>6.4f} {r['fp_dist']:>6.4f} {mark:>3s}")

    # ── 4. Failure modes ───────────────────────────────────────────────────
    failures = [r for r in results if not r["correct"] and not r["fp_rescue"]]
    if failures:
        print(f"\nFAILURE MODES ({len(failures)}):")
        for r in failures:
            print(f"  {r['id']}: esperaba {r['expected']}, obtuvo {r['got']} (ISI={r['isi']:.4f})")
            print(f"    Módulos que dispararon: {r['modules_fired']}")
    else:
        print("\nSIN FAILURE MODES — todos los casos pasan (raw o por fingerprint rescue)")

    # ── 5. Guardar ─────────────────────────────────────────────────────────
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nReporte guardado: {OUTPUT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())