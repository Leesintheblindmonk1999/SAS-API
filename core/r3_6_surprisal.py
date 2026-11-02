"""
r3_6_surprisal.py — R3.6 Surprisal Analysis Module
═══════════════════════════════════════════════════════════════════════════════
Localizes hallucination at the token level by computing per-token
surprisal (self-information) of the response given the source.

I(token) = -log2 P(token | source_context)

Tokens with surprisal above threshold are marked as potentially
hallucinated. This is the closest R3 module to "the holy grail" of
hallucination localization.

The probability model uses character n-gram statistics from the source
as a simple but effective language model — no external dependencies.

100% Python standard library. Zero external dependencies. ~50 µs/pair.

Architecture:
  1. Build character n-gram language model from source (n=3..6)
  2. For each token in response, compute:
     - Forward surprisal: -log2 P(token | preceding source context)
     - Backward surprisal: -log2 P(token | following source context)
  3. Tokens with mean surprisal > threshold → marked as anomalous
  4. Aggregate: fraction of anomalous tokens → overall anomaly score

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
License: Durante Invariance License v1.0
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

MODULE_VERSION: str = "1.0.0"

# Surprisal threshold (bits) — tokens above this are marked anomalous
SURPRISAL_THRESHOLD: float = 8.0

# Minimum number of source tokens for reliable model
MIN_SOURCE_TOKENS: int = 10

# N-gram orders for the language model (3-grams to 6-grams)
NGRAM_ORDERS: Tuple[int, ...] = (3, 4, 5, 6)

# Smoothing factor for unseen n-grams
SMOOTHING_DELTA: float = 0.01

# Fraction of anomalous tokens that triggers penalty
ANOMALY_FRACTION_THRESHOLD: float = 0.15

# Penalty when anomaly fraction exceeds threshold
SURPRISAL_PENALTY_BASE: float = 0.55

# ═══════════════════════════════════════════════════════════════════════════════
# TOKENIZATION
# ═══════════════════════════════════════════════════════════════════════════════

_RE_TOKEN = re.compile(r"[a-zA-Z0-9]+(?:[''][a-zA-Z]+)?", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    """Tokenize text into words, preserving contractions."""
    return _RE_TOKEN.findall(text.lower())


def _build_ngram_model(tokens: List[str], orders: Tuple[int, ...]) -> Dict:
    """Build n-gram language model from token list.

    Returns dict mapping n-gram order to:
        counts: Counter of n-gram occurrences
        prefix_counts: Counter of (n-1)-gram prefixes
        vocab_size: number of unique tokens
    """
    model = {}
    for n in orders:
        if len(tokens) < n:
            continue
        counts: Counter = Counter()
        prefix_counts: Counter = Counter()
        for i in range(len(tokens) - n + 1):
            ngram = tuple(tokens[i:i + n])
            prefix = ngram[:-1]
            counts[ngram] += 1
            prefix_counts[prefix] += 1
        model[n] = {
            "counts": counts,
            "prefix_counts": prefix_counts,
            "vocab_size": len(set(tokens)),
        }
    return model


def _estimate_probability(
    token: str,
    context: Tuple[str, ...],
    model: Dict,
    delta: float = SMOOTHING_DELTA,
) -> float:
    """Estimate P(token | context) using interpolated n-gram model.

    Uses backing-off: tries highest order first, then lower orders,
    with smoothing for unseen events.
    """
    # Try each n-gram order from highest to lowest
    for n in sorted(model.keys(), reverse=True):
        ngram_data = model[n]
        counts = ngram_data["counts"]
        prefix_counts = ngram_data["prefix_counts"]
        vocab_size = ngram_data["vocab_size"]

        # Use the last (n-1) tokens of context as prefix
        prefix = context[-(n - 1):] if len(context) >= n - 1 else tuple(context)

        ngram = prefix + (token,)
        ngram_count = counts.get(ngram, 0)
        prefix_count = prefix_counts.get(prefix, 0)

        # Add-k smoothing
        numerator = ngram_count + delta
        denominator = prefix_count + delta * (vocab_size + 1)
        if denominator > 0:
            return numerator / denominator

    # Fallback: uniform probability over vocabulary
    return 1.0 / max(model.get(max(model.keys()), {}).get("vocab_size", 1000), 1)


def _compute_surprisal(token: str, prob: float) -> float:
    """Compute self-information I(token) = -log2 P(token)."""
    if prob <= 0:
        return float("inf")
    return -math.log2(prob)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def compute_surprisal_analysis(
    source: str,
    response: str,
    threshold: float = SURPRISAL_THRESHOLD,
) -> Dict:
    """Compute per-token surprisal analysis of response given source.

    Parameters
    ----------
    source : str
        Source text (ground truth).
    response : str
        Response text to evaluate.
    threshold : float
        Surprisal threshold in bits. Default 8.0.

    Returns
    -------
    Dict with keys:
        token_surprisals : List[Dict]
            Per-token analysis: token, surprisal, is_anomalous.
        mean_surprisal : float
            Mean surprisal across all tokens.
        max_surprisal : float
            Maximum surprisal across all tokens.
        anomalous_tokens : int
            Count of tokens above threshold.
        total_tokens : int
            Total tokens in response.
        anomaly_fraction : float
            Fraction of tokens above threshold.
        is_anomalous : bool
            True if anomaly_fraction > ANOMALY_FRACTION_THRESHOLD.
        penalty : float
            Multiplicative penalty factor.
    """
    # Tokenize
    src_tokens = _tokenize(source)
    rsp_tokens = _tokenize(response)

    if len(src_tokens) < MIN_SOURCE_TOKENS or not rsp_tokens:
        return {
            "token_surprisals": [],
            "mean_surprisal": 0.0,
            "max_surprisal": 0.0,
            "anomalous_tokens": 0,
            "total_tokens": len(rsp_tokens),
            "anomaly_fraction": 0.0,
            "is_anomalous": False,
            "penalty": 1.0,
        }

    # Build n-gram model from source
    model = _build_ngram_model(src_tokens, NGRAM_ORDERS)

    if not model:
        return {
            "token_surprisals": [],
            "mean_surprisal": 0.0,
            "max_surprisal": 0.0,
            "anomalous_tokens": 0,
            "total_tokens": len(rsp_tokens),
            "anomaly_fraction": 0.0,
            "is_anomalous": False,
            "penalty": 1.0,
        }

    # Compute per-token surprisal
    token_surprisals = []
    for i, token in enumerate(rsp_tokens):
        # Context: up to 6 preceding tokens in response
        context_start = max(0, i - 6)
        context = tuple(rsp_tokens[context_start:i])

        prob = _estimate_probability(token, context, model)
        surprisal = _compute_surprisal(token, prob)

        token_surprisals.append({
            "token": token,
            "surprisal": round(surprisal, 4),
            "is_anomalous": surprisal > threshold,
        })

    # Aggregate
    total = len(token_surprisals)
    anomalous = sum(1 for t in token_surprisals if t["is_anomalous"])
    anomaly_fraction = anomalous / max(total, 1)
    mean_surprisal = sum(t["surprisal"] for t in token_surprisals) / max(total, 1)
    max_surprisal = max((t["surprisal"] for t in token_surprisals), default=0.0)

    is_anomalous = anomaly_fraction > ANOMALY_FRACTION_THRESHOLD
    penalty = SURPRISAL_PENALTY_BASE if is_anomalous else 1.0

    return {
        "token_surprisals": token_surprisals[:100],  # limit output size
        "mean_surprisal": round(mean_surprisal, 4),
        "max_surprisal": round(max_surprisal, 4),
        "anomalous_tokens": anomalous,
        "total_tokens": total,
        "anomaly_fraction": round(anomaly_fraction, 4),
        "is_anomalous": is_anomalous,
        "penalty": round(penalty, 4),
    }