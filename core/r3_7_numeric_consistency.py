"""
r3_7_numeric_consistency.py — R3.7 Numeric Consistency Module
═══════════════════════════════════════════════════════════════════════════════
Detects numeric inconsistencies between source (A) and response (B):

  1. Neighbor trap detection: response uses a number that appears in the
     source context but differs from the target number (e.g., source has
     "$696.1M revenue, $684.9M cost", response says "revenue was $684.9M").
  2. Fabricated number detection: response introduces numbers that don't
     appear anywhere in the source.

Methodology:
  1. Split source into context (all lines except last) and target (last line).
  2. Extract all numeric values (currencies, decimals, percentages, integers).
  3. Compare response target numbers against source target and context.
  4. Neighbor trap: response number matches a context number but not target.
  5. Fabricated: response number not found in source at all.

100% Python standard library. Zero external dependencies. ~30 µs/pair.

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
License: Durante Invariance License v1.0
"""

from __future__ import annotations

import re
from typing import List, Tuple, Dict

# ── Constants ──────────────────────────────────────────────────────────────────
R3_7_NUMERIC_PENALTY: float = 0.50


def extract_numbers(text: str) -> List[Tuple[str, float]]:
    """Extract numeric values from text. Handles currencies, decimals, percentages."""
    numbers: List[Tuple[str, float]] = []
    for m in re.finditer(r'[\$£€¥]\s*[\d,]+(?:\.\d+)?%?', text):
        clean = m.group(0).replace('$', '').replace('£', '').replace('€', '').replace('¥', '').replace(',', '').replace('%', '').strip()
        try:
            numbers.append((m.group(0), float(clean)))
        except ValueError:
            pass
    for m in re.finditer(r'\b\d+(?:,\d{3})*(?:\.\d+)?%?\b', text):
        clean = m.group(0).replace(',', '').replace('%', '').strip()
        try:
            numbers.append((m.group(0), float(clean)))
        except ValueError:
            pass
    return numbers


def compute_numeric_consistency(source: str, response: str) -> Dict:
    """Compute numeric consistency between source and response.

    Returns:
        Dict with keys:
            fired (bool): whether inconsistency was detected
            penalty (float): penalty factor (0.50 if fired, 1.0 otherwise)
            n_neighbor_traps (int): count of neighbor trap numbers
            n_fabricated (int): count of fabricated numbers
    """
    src_lines = source.strip().split('\n')
    rsp_lines = response.strip().split('\n')
    src_target = src_lines[-1] if len(src_lines) > 1 else source
    rsp_target = rsp_lines[-1] if len(rsp_lines) > 1 else response
    src_context = '\n'.join(src_lines[:-1]) if len(src_lines) > 1 else ''

    src_tv = set(v for _, v in extract_numbers(src_target))
    rsp_tv = set(v for _, v in extract_numbers(rsp_target))
    src_cv = set(v for _, v in extract_numbers(src_context))
    src_all = src_tv | src_cv

    target_mismatch = bool(src_tv and rsp_tv and src_tv != rsp_tv)
    neighbor_traps = {rv for rv in rsp_tv if rv not in src_tv and rv in src_cv}
    fabricated = rsp_tv - src_all
    fired = (target_mismatch and len(neighbor_traps) > 0) or len(fabricated) > 0

    return {
        "fired": fired,
        "penalty": R3_7_NUMERIC_PENALTY if fired else 1.0,
        "n_neighbor_traps": len(neighbor_traps),
        "n_fabricated": len(fabricated),
    }