#!/usr/bin/env python3
"""Verify compression confound (A→A' asymmetry) and fingerprint percentiles for κP calibration."""
import json, zlib, statistics, re, math, sys
from collections import Counter
from pathlib import Path

REPO = Path(r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API")
INPUT = Path(r"C:\Users\conno\Downloads\SAS-Semántico\reports\pairs_medico_medhallu_10k.jsonl")

def tokens(t): return re.findall(r"\b\w+\b", t.lower())
def sentences(t): return [s.strip() for s in re.split(r"[.!?]+", t) if s.strip()]
def shannon_entropy(t):
    if not t: return 0.0
    c = Counter(t); n = len(t)
    return -sum((v/n)*math.log2(v/n) for v in c.values())
def comp_len(t): return len(zlib.compress(t.encode("utf-8")))

# ── Load ──
records = []
with open(INPUT, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line.strip())
        if all(r.get(k) for k in ("A","A_prime","B","A_pp")):
            records.append(r)
print(f"Loaded {len(records)} records")

# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — Conditional compression: all 4 conditions
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 1 — CONDITIONAL COMPRESSION (all 4 conditions, 10k records)")
print("=" * 70)

def compression_stats(records):
    """Return dict of {cond: {delta_sr: [...], asym: [...]}}"""
    result = {}
    for cond, key in [("A_A", "A"), ("A_Ap", "A_prime"), ("A_B", "B"), ("A_App", "A_pp")]:
        ds_list, asym_list = [], []
        for rec in records:
            a = rec["A"]
            rsp = rec[key]
            c_src = comp_len(a)
            c_rsp = comp_len(rsp)
            c_sr = comp_len(a + "\n" + rsp)
            c_rs = comp_len(rsp + "\n" + a)
            delta_sr = max(0, c_sr - c_src)
            delta_rs = max(0, c_rs - c_rsp)
            ds_list.append(delta_sr)
            asym_list.append(abs(delta_sr - delta_rs))
        result[cond] = {"delta_sr": ds_list, "asym": asym_list}
    return result

def print_stats(label, ds, asym):
    def pct(vals, p):
        s = sorted(vals)
        return round(s[min(len(s)-1, int(len(s)*p))], 1)
    print(f"\n  {label}:")
    print(f"    delta_sr: mean={statistics.mean(ds):.1f} median={statistics.median(ds):.1f} "
          f"p25={pct(ds,0.25)} p75={pct(ds,0.75)}")
    print(f"    asym:     mean={statistics.mean(asym):.1f} median={statistics.median(asym):.1f} "
          f"p25={pct(asym,0.25)} p75={pct(asym,0.75)}")

comp = compression_stats(records)
print_stats("A→A   (identity)", comp["A_A"]["delta_sr"], comp["A_A"]["asym"])
print_stats("A→A_pp (paraphrase)", comp["A_App"]["delta_sr"], comp["A_App"]["asym"])
print_stats("A→A_p  (short correct)", comp["A_Ap"]["delta_sr"], comp["A_Ap"]["asym"])
print_stats("A→B    (hallucination)", comp["A_B"]["delta_sr"], comp["A_B"]["asym"])

# Asymmetry ratios
asym_app = statistics.mean(comp["A_App"]["asym"])
asym_ap = statistics.mean(comp["A_Ap"]["asym"])
asym_b = statistics.mean(comp["A_B"]["asym"])
print(f"\n  ASYMMETRY RATIOS:")
print(f"    A→B / A→A_pp = {asym_b/asym_app:.1f}x")
print(f"    A→B / A→A_p  = {asym_b/asym_ap:.1f}x")
print(f"    A→A_p / A→A_pp = {asym_ap/asym_app:.1f}x")
print(f"\n  VERDICT: A→A_p asym={asym_ap:.1f} vs A→B asym={asym_b:.1f}")
if asym_ap < 100:
    print("    → A→A_p is LOW → signal is CONTENT (short correct IS predictable)")
elif asym_ap > 300:
    print("    → A→A_p is HIGH → signal is partially LENGTH artifact")
else:
    print("    → A→A_p is moderate → mixed signal")

# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — Fingerprint percentiles (1,000 records for speed)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 2 — FINGERPRINT PERCENTILES (3+9 features, 1k records)")
print("=" * 70)

FUNCTION_WORDS = set(
    "the a an in on at of to for with by from as is are was were be been being "
    "and or but not no so if then than that this these those it its he she they "
    "we you i me my your our their him her them".split()
)

def relational_features(src, rsp):
    s_sent = sentences(src); r_sent = sentences(rsp)
    s_lens = [len(tokens(s)) for s in s_sent]
    r_lens = [len(tokens(s)) for s in r_sent]
    n = min(len(s_lens), len(r_lens))
    corr = 0.0
    if n >= 2:
        try: corr = statistics.correlation(s_lens[:n], r_lens[:n])
        except statistics.StatisticsError: corr = 0.0
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

dist_12_app, dist_12_b, dist_12_ap = [], [], []
sample = records[:1000]

for rec in sample:
    a = rec["A"]; ap = rec["A_prime"]; b = rec["B"]; app = rec["A_pp"]
    f12_src = {**absolute_features(a), **relational_features(a, a)}
    f12_app = {**absolute_features(app), **relational_features(a, app)}
    f12_b = {**absolute_features(b), **relational_features(a, b)}
    f12_ap = {**absolute_features(ap), **relational_features(a, ap)}
    dist_12_app.append(fp_dist(f12_src, f12_app))
    dist_12_b.append(fp_dist(f12_src, f12_b))
    dist_12_ap.append(fp_dist(f12_src, f12_ap))

def pctiles(vals):
    s = sorted(vals)
    def p(pct): return round(s[min(len(s)-1, int(len(s)*pct))], 4)
    return {"mean": round(statistics.mean(vals), 4), "median": p(0.50),
            "p75": p(0.75), "p90": p(0.90), "p95": p(0.95),
            "p5": p(0.05), "p10": p(0.10), "p25": p(0.25)}

print("\nVariant B (3+9 features) — 1,000 records:")
for label, vals in [("A→A_pp (paraphrase)", dist_12_app),
                     ("A→A_p  (short correct)", dist_12_ap),
                     ("A→B    (hallucination)", dist_12_b)]:
    s = pctiles(vals)
    print(f"  {label}:")
    print(f"    mean={s['mean']} p5={s['p5']} p10={s['p10']} p25={s['p25']} "
          f"p50={s['median']} p75={s['p75']} p90={s['p90']} p95={s['p95']}")

# κP calibration: find threshold where A→A_pp p95 < κP < A→B p5
p95_app = pctiles(dist_12_app)["p95"]
p5_b = pctiles(dist_12_b)["p5"]
print(f"\n  κP CALIBRATION:")
print(f"    A→A_pp p95 = {p95_app}")
print(f"    A→B    p5  = {p5_b}")
if p95_app < p5_b:
    print(f"    → ZERO overlap! Any κP in [{p95_app:.4f}, {p5_b:.4f}] gives perfect separation")
    print(f"    → Recommended κP = {((p95_app + p5_b)/2):.4f} (midpoint)")
else:
    print(f"    → Overlap exists. κP must be tuned via precision-recall")
    print(f"    → Recommended κP = {p95_app:.4f} (A→A_pp p95, max precision)")