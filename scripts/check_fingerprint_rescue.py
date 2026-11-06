#!/usr/bin/env python3
"""Check fingerprint rescue on adversarial Type B cases."""
import json, zlib, statistics, re, math, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.tribunal_multimetrico import TribunalMultimetrico

KAPPA_D, KAPPA_R = 0.56, 0.15
KP = 0.4039

def tokens(t): return re.findall(r"\b\w+\b", t.lower())
def sentences(t): return [s.strip() for s in re.split(r"[.!?]+", t) if s.strip()]
def shannon_entropy(t):
    if not t: return 0.0
    c = Counter(t); n = len(t)
    return -sum((v/n)*math.log2(v/n) for v in c.values())
def comp_len(t): return len(zlib.compress(t.encode("utf-8")))

FUNCTION_WORDS = set("the a an in on at of to for with by from as is are was were be been being and or but not no so if then than that this these those it its he she they we you i me my your our their him her them".split())

def relational_features(src, rsp):
    s_sent = sentences(src); r_sent = sentences(rsp)
    s_lens = [len(tokens(s)) for s in s_sent]
    r_lens = [len(tokens(s)) for s in r_sent]
    n = min(len(s_lens), len(r_lens))
    corr = 0.0
    if n >= 2:
        try: corr = statistics.correlation(s_lens[:n], r_lens[:n])
        except: corr = 0.0
    def fw_ratio(t):
        toks = tokens(t)
        return sum(1 for w in toks if w in FUNCTION_WORDS) / max(len(toks), 1)
    fw_diff = abs(fw_ratio(src) - fw_ratio(rsp))
    s_bigrams = set(zip(tokens(src), tokens(src)[1:]))
    r_toks = tokens(rsp)
    r_bigrams = set(zip(r_toks, r_toks[1:]))
    preserved = len(s_bigrams & r_bigrams) / max(len(s_bigrams), 1)
    return {"sentence_len_corr": round(corr, 4), "fw_ratio_diff": round(fw_diff, 4),
            "bigram_preservation": round(preserved, 4)}

def absolute_features(t):
    sents = sentences(t); words = tokens(t)
    proper = [w for w in re.findall(r"\b[A-Z][a-z]+\b", t)
              if w.lower() not in ("the","a","an","in","on","at")]
    numerals = re.findall(r"\d+", t)
    negations = re.findall(r"\b(not|never|no|without|despite)\b", t.lower())
    causal = re.findall(r"\b(because|therefore|thus|hence|so|since)\b", t.lower())
    comp = comp_len(t) / max(len(t), 1)
    return {"n_sentences": len(sents), "avg_sentence_len": len(words)/max(len(sents),1),
            "n_proper_nouns": len(proper), "n_numerals": len(numerals),
            "n_negations": len(negations), "n_causal": len(causal),
            "char_entropy": round(shannon_entropy(t), 4), "comp_ratio": round(comp, 4)}

def fp_dist(f1, f2):
    keys = set(f1) & set(f2)
    if not keys: return 1.0
    dists = []
    for k in keys:
        denom = max(abs(f1[k]), abs(f2[k]), 1e-6)
        dists.append(abs(f1[k] - f2[k]) / denom)
    return sum(dists) / len(dists)

# Load
cases = []
with open(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API\data\adversarial_10.jsonl", encoding="utf-8") as f:
    for line in f:
        if line.strip(): cases.append(json.loads(line))

tribunal = TribunalMultimetrico(kappa_d=KAPPA_D, kappa_r=KAPPA_R)

print("=" * 72)
print("FINGERPRINT RESCUE — Type B (paraphrase, should be COHERENTE)")
print("=" * 72)
print(f"  kP = {KP} (recommended)")
print(f"  If fp_dist < kP -> fingerprint says PARAPHRASE -> rescue")
print()

for c in cases:
    if c["type"] != "no_detect":
        continue
    src, rsp = c["source"], c["response"]
    v = tribunal.evaluar(src, rsp)
    f12_src = {**absolute_features(src), **relational_features(src, src)}
    f12_rsp = {**absolute_features(rsp), **relational_features(src, rsp)}
    dist = fp_dist(f12_src, f12_rsp)
    rescued = dist < KP
    verdict = "RESCUE" if rescued else "NO RESCUE"
    print(f"  {c['id']}: tribunal={v.zona} ISI={v.isi_final:.4f}  fp_dist={dist:.4f}  [{verdict}]")
    if rescued:
        print(f"    -> Would change verdict from {v.zona} to COHERENTE")
    print()

print("=" * 72)
print("FINGERPRINT — Type A (stealth, should be COLAPSO)")
print("=" * 72)
for c in cases:
    if c["type"] != "detect":
        continue
    src, rsp = c["source"], c["response"]
    v = tribunal.evaluar(src, rsp)
    f12_src = {**absolute_features(src), **relational_features(src, src)}
    f12_rsp = {**absolute_features(rsp), **relational_features(src, rsp)}
    dist = fp_dist(f12_src, f12_rsp)
    print(f"  {c['id']}: tribunal={v.zona} ISI={v.isi_final:.4f}  fp_dist={dist:.4f}  (kP={KP})")