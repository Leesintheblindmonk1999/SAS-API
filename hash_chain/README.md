# Hash Chain — SAS Multimetric Tribunal v1.2.0
# Date: 2026-10-28
# Last commit: 6c7e71f
# Registry: TAD EX-2026-18792778

======================================================================
WHAT IS THIS?
======================================================================

This is the forensic chain of custody for the entire SAS-API system.
Every `.py` file in the repository has its individual SHA-256 hash,
and the upper levels nest those hashes into a self-referential chain.

Anyone can verify that the system has not been tampered with by
reproducing the same hashes from the source code.

======================================================================
CHAIN STRUCTURE
======================================================================

Level 1 — hashes_individuales.txt
  SHA-256 of every `.py` file in SAS-API (103 files).
  Sorted alphabetically by relative path.

Level 2 — core_modules_concatenated
  SHA-256 of the concatenation of the 8 tribunal modules:
    core/tribunal_multimetrico.py
    core/r3_1_differential.py
    core/r3_2_topological.py
    core/negation_probe.py
    core/flow_coherence.py
    core/ricci_enhanced_cre.py
    core/arithmetic_detector.py
    core/reference_check.py

Level 3 — app/main.py
  SHA-256 of the API entry point.

Level 4 — requirements.txt
  SHA-256 of the system dependencies.

Level 5 — docker-compose.yml
  SHA-256 of the deployment configuration.

Level 6 — chain.txt (self-hash)
  SHA-256 of chain.txt itself, including all previous levels.
  Self-referential: any modification invalidates the hash.

======================================================================
HASHES (2026-10-28, commit 6c7e71f)
======================================================================

  efa44d32030f88a22ef86d0bc363c66aedd7222fc1aa7a3e917c710e67a97aed  hashes_individuales.txt
  16e31da6fbdae95ca186869ecef75814ea63e01a336e734538461adb349b98d8  core_modules_concatenated
  b6290c5b49c35305d39ce8cfd689b6d377e091e85eccecaa385610f9a1ea36ce  app/main.py
  3f0fe473610f461e052876bb46b9f7ae51cd0d3da08b206de07dbc3f5468cf87  requirements.txt
  748ed05910c1a6ccb12b985c1b1b115e9e9077e25b6732439c3c4ce8ceaed478  docker-compose.yml
  d8fe8721039baa38aaedf76ba9a19a5f1ff3d33c6e12a8d097552bb7537019e7  chain.txt (self-hash)

======================================================================
OPEN TIMESTAMPS (Bitcoin-anchored)
======================================================================

  hashes_individuales.txt.ots  — 840 bytes
  chain.txt.ots               — 980 bytes

These `.ots` files prove that the hash chain existed before the
Bitcoin block timestamp. They can be verified with:

  ots verify hashes_individuales.txt.ots
  ots verify chain.txt.ots

No third party, no authority, no platform approval needed.
The proof is in the blockchain.

======================================================================
VERIFICATION
======================================================================

To reproduce the chain from scratch:

  python hash_chain/build_hash_chain.py

The script reproduces all hashes and compares them with chain.txt.
If any file has been modified, the hash will not match.

======================================================================
FILES
======================================================================

  build_hash_chain.py              — Script to reproduce the chain
  hashes_individuales.txt          — SHA-256 of every .py file (103)
  hashes_individuales.txt.ots      — OpenTimestamps proof
  chain.txt                        — Nested chain (6 levels)
  chain.txt.ots                    — OpenTimestamps proof
  README.md                        — This file