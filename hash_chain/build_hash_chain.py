"""
build_hash_chain.py — Construye la cadena de hashes anidada del SAS-API
======================================================================
Niveles:
  L1: SHA-256 de cada archivo .py individual
  L2: SHA-256 de la concatenación de los 8 módulos del tribunal
  L3: SHA-256 de app/main.py (entry point)
  L4: SHA-256 de requirements.txt
  L5: SHA-256 de docker-compose.yml
  L6: SHA-256 del propio chain.txt (auto-referencial)

Registry: TAD EX-2026-18792778
"""

import hashlib
import os

BASE = r"C:\Users\conno\Downloads\SAS-Semántico\repo\SAS-API"
OUT = r"C:\Users\conno\Downloads\SAS-Semántico\hash_chain"

os.makedirs(OUT, exist_ok=True)

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

lines = []

# ── Level 1: every .py file ──────────────────────────────────────────
py_files = []
for root, dirs, files in os.walk(BASE):
    # skip __pycache__
    dirs[:] = [d for d in dirs if d != "__pycache__" and d != ".git" and d != ".github" and d != "__pycache__"]
    for f in files:
        if f.endswith(".py"):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, BASE).replace("\\", "/")
            py_files.append((rel, full))

py_files.sort(key=lambda x: x[0])

# Write individual hashes file
indiv_lines = []
for rel, full in py_files:
    h = sha256_file(full)
    indiv_lines.append(f"{h}  {rel}")

indiv_path = os.path.join(OUT, "hashes_individuales.txt")
with open(indiv_path, "w", encoding="utf-8") as f:
    f.write("\n".join(indiv_lines) + "\n")

l1 = sha256_file(indiv_path)
lines.append(f"{l1}  hashes_individuales.txt")
print(f"L1 (all {len(py_files)} .py files): {l1}")

# ── Level 2: core modules concatenated ───────────────────────────────
core_modules = [
    "core/tribunal_multimetrico.py",
    "core/r3_1_differential.py",
    "core/r3_2_topological.py",
    "core/negation_probe.py",
    "core/flow_coherence.py",
    "core/ricci_enhanced_cre.py",
    "core/arithmetic_detector.py",
    "core/reference_check.py",
]

core_concat = b""
for mod in core_modules:
    full = os.path.join(BASE, mod)
    if os.path.exists(full):
        h = sha256_file(full)
        core_concat += h.encode("utf-8")
        print(f"  core module: {mod} -> {h}")
    else:
        print(f"  WARNING: {mod} not found")

l2 = sha256_bytes(core_concat)
lines.append(f"{l2}  core_modules_concatenated")
print(f"L2 (8 core modules): {l2}")

# ── Level 3: app/main.py ────────────────────────────────────────────
main_py = os.path.join(BASE, "app", "main.py")
if os.path.exists(main_py):
    l3 = sha256_file(main_py)
    lines.append(f"{l3}  app/main.py")
    print(f"L3 (app/main.py): {l3}")

# ── Level 4: requirements.txt ───────────────────────────────────────
req_txt = os.path.join(BASE, "requirements.txt")
if os.path.exists(req_txt):
    l4 = sha256_file(req_txt)
    lines.append(f"{l4}  requirements.txt")
    print(f"L4 (requirements.txt): {l4}")

# ── Level 5: docker-compose.yml ─────────────────────────────────────
dc_yml = os.path.join(BASE, "docker-compose.yml")
if os.path.exists(dc_yml):
    l5 = sha256_file(dc_yml)
    lines.append(f"{l5}  docker-compose.yml")
    print(f"L5 (docker-compose.yml): {l5}")

# ── Level 6: self-hash of chain.txt ─────────────────────────────────
chain_path = os.path.join(OUT, "chain.txt")
# Write preliminary chain
with open(chain_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

l6 = sha256_file(chain_path)
lines.append(f"{l6}  chain.txt (self-hash)")

# Rewrite with self-hash included
with open(chain_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"L6 (chain self-hash): {l6}")
print(f"\nChain written to: {chain_path}")
print(f"Total levels: {len(lines)}")

# ── Summary ──────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  HASH CHAIN — SAS-API")
print("=" * 60)
for line in lines:
    print(f"  {line}")
print("=" * 60)