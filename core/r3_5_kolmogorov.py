"""
r3_5_kolmogorov.py — R3.5 Kolmogorov Complexity Ratio Module
═══════════════════════════════════════════════════════════════════════════════
Approximates Kolmogorov complexity via LZ77 compression (zlib) to detect
abnormal complexity patterns. A hallucination may be either:

  - Overly complex (introducing novel information not in source)
  - Overly simple (generic/evasive text with low information density)

The ratio C(source) / C(response) reveals these asymmetries. If the ratio
is extreme in either direction, it signals potential hallucination.

Key insight: compression ratio is independent of lexical overlap — it
complements R3.2 (topological) and R3.4 (entropy) by measuring a
fundamentally different property.

100% Python standard library. Zero external dependencies. ~5 µs/pair.

Architecture:
  1. Compress source and response separately with zlib (LZ77)
  2. C(source) = len(zlib.compress(source))
  3. C(response) = len(zlib.compress(response))
  4. ratio = C(source) / C(response)
  5. If ratio < MIN_RATIO or ratio > MAX_RATIO → anomaly signal

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
License: Durante Invariance License v1.0
"""

from __future__ import annotations

import zlib
from typing import Dict

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

MODULE_VERSION: str = "1.0.0"

# Ratio thresholds for anomaly detection
# ratio = C(source) / C(response)
# ratio < MIN_RATIO → response much more complex than source (hallucination)
# ratio > MAX_RATIO → response much simpler than source (generic/evasive)
MIN_RATIO: float = 0.50
MAX_RATIO: float = 2.00

# Penalty when anomaly detected
KOLMOGOROV_PENALTY_BASE: float = 0.65

# Minimum compressed size for reliable ratio estimation
MIN_COMPRESSED_SIZE: int = 10

# Compression level (1-9, 1=fastest, 9=best compression)
ZLIB_LEVEL: int = 6


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def compute_kolmogorov_ratio(
    source: str,
    response: str,
    min_ratio: float = MIN_RATIO,
    max_ratio: float = MAX_RATIO,
) -> Dict:
    """Compute Kolmogorov complexity ratio between source and response.

    Parameters
    ----------
    source : str
        Source text (ground truth).
    response : str
        Response text to evaluate.
    min_ratio : float
        Minimum acceptable ratio. Default 0.50.
    max_ratio : float
        Maximum acceptable ratio. Default 2.00.

    Returns
    -------
    Dict with keys:
        compressed_source : int
            Compressed size of source in bytes.
        compressed_response : int
            Compressed size of response in bytes.
        ratio : float
            C(source) / C(response).
        is_anomalous : bool
            True if ratio outside [min_ratio, max_ratio].
        direction : str
            "RESPONSE_MORE_COMPLEX" if ratio < min_ratio,
            "RESPONSE_SIMPLER" if ratio > max_ratio,
            "NORMAL" otherwise.
        penalty : float
            Multiplicative penalty factor (1.0 if normal, < 1.0 if anomalous).
    """
    # Handle empty or very short texts
    if not source or not response:
        return {
            "compressed_source": 0,
            "compressed_response": 0,
            "ratio": 1.0,
            "is_anomalous": False,
            "direction": "INSUFFICIENT_TEXT",
            "penalty": 1.0,
        }

    # Compress both texts
    src_bytes = source.encode("utf-8", errors="replace")
    rsp_bytes = response.encode("utf-8", errors="replace")

    c_source = len(zlib.compress(src_bytes, ZLIB_LEVEL))
    c_response = len(zlib.compress(rsp_bytes, ZLIB_LEVEL))

    # Guard against degenerate cases
    if c_response < MIN_COMPRESSED_SIZE or c_source < MIN_COMPRESSED_SIZE:
        return {
            "compressed_source": c_source,
            "compressed_response": c_response,
            "ratio": round(c_source / max(c_response, 1), 4),
            "is_anomalous": False,
            "direction": "INSUFFICIENT_COMPRESSED_SIZE",
            "penalty": 1.0,
        }

    ratio = c_source / c_response

    # Determine direction
    if ratio < min_ratio:
        direction = "RESPONSE_MORE_COMPLEX"
        is_anomalous = True
    elif ratio > max_ratio:
        direction = "RESPONSE_SIMPLER"
        is_anomalous = True
    else:
        direction = "NORMAL"
        is_anomalous = False

    penalty = KOLMOGOROV_PENALTY_BASE if is_anomalous else 1.0

    return {
        "compressed_source": c_source,
        "compressed_response": c_response,
        "ratio": round(ratio, 4),
        "is_anomalous": is_anomalous,
        "direction": direction,
        "penalty": round(penalty, 4),
    }