"""
r3_3_drift.py — R3.3 Semantic Drift Trajectory Module
═══════════════════════════════════════════════════════════════════════════════
Detects the point where a model "turns the curve" in long texts by measuring
ISI sentence by sentence against the source. Each sentence of the response
is evaluated independently, producing a drift trajectory that reveals:

  - Where the model started hallucinating (the "break point")
  - Whether the drift is sudden (one bad sentence) or gradual
  - Which specific sentence(s) caused the collapse

Key insight: in a coherent response, ISI remains stable across sentences.
In a hallucinated response, ISI drops sharply at the point of invention.

100% Python standard library. Zero external dependencies. ~200 µs/pair.

Architecture:
  1. Split response into sentences (regex-based)
  2. For each sentence, compute ISI against the full source
  3. Track cumulative ISI trajectory
  4. Detect break point: sentence where ISI drops below κR
  5. Classify drift type: SUDDEN, GRADUAL, RECOVERED, STABLE

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
License: Durante Invariance License v1.0
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

MODULE_VERSION: str = "1.0.0"

KAPPA_D: float = 0.56
KAPPA_R: float = 0.15

# Minimum number of sentences for drift analysis
MIN_SENTENCES: int = 3

# Drift classification thresholds
SUDDEN_DROP_THRESHOLD: float = 0.30  # ΔISI between consecutive sentences
RECOVERY_THRESHOLD: float = 0.10     # ΔISI up after a drop

# Penalty when drift is detected
DRIFT_PENALTY_BASE: float = 0.50

# ═══════════════════════════════════════════════════════════════════════════════
# SENTENCE SPLITTING
# ═══════════════════════════════════════════════════════════════════════════════

_RE_SENTENCE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z\"\'\(])",
    re.UNICODE,
)

# Fallback: split on sentence-ending punctuation
_RE_SENTENCE_FALLBACK = re.compile(r"(?<=[.!?])\s+", re.UNICODE)


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    sentences = _RE_SENTENCE.split(text)
    if len(sentences) <= 1:
        sentences = _RE_SENTENCE_FALLBACK.split(text)
    return [s.strip() for s in sentences if s.strip()]


# ═══════════════════════════════════════════════════════════════════════════════
# ISI COMPUTATION (lightweight lexical baseline)
# ═══════════════════════════════════════════════════════════════════════════════

_RE_TOKEN = re.compile(r"\b\w+\b", re.UNICODE)

_STOPWORDS: set = {
    "the", "a", "an", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "can", "could", "shall", "should",
    "may", "might", "must", "to", "of", "in", "for", "on", "with", "at",
    "by", "from", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all",
    "each", "every", "both", "little", "much", "many", "some", "any",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
}


def _token_set(text: str) -> set:
    """Extract content word set from text."""
    tokens = _RE_TOKEN.findall(text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


def _lexical_isi(source_set: set, response_set: set) -> float:
    """Compute coverage-based ISI: fraction of response content words found in source.

    IMPORTANT: This uses RECALL (coverage) of the response against the source,
    NOT Jaccard. Jaccard penalizes the source for containing words absent from
    a short sentence, which produces false positives on identical text.

    Example: sentence "Correct answer: Arthur's Magazine" against a long source
    → Jaccard ≈ 0.17 (wrong), coverage = 1.0 (correct, all words are in source).
    """
    if not response_set:
        return 0.0
    intersection = source_set & response_set
    return len(intersection) / len(response_set)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def compute_drift_trajectory(
    source: str,
    response: str,
    kappa_d: float = KAPPA_D,
    kappa_r: float = KAPPA_R,
) -> Dict:
    """Compute semantic drift trajectory across response sentences.

    Parameters
    ----------
    source : str
        Source text (ground truth).
    response : str
        Response text to evaluate.
    kappa_d : float
        Coherence threshold. Default 0.56.
    kappa_r : float
        Collapse threshold. Default 0.15.

    Returns
    -------
    Dict with keys:
        sentences : List[str]
            Individual sentences of the response.
        sentence_count : int
            Number of sentences.
        trajectory : List[Dict]
            Per-sentence ISI values and metadata.
        break_point : Optional[int]
            Index of sentence where ISI first drops below κR (0-indexed).
        break_sentence : Optional[str]
            The sentence at the break point.
        drift_type : str
            "STABLE" — all sentences above κD
            "SUDDEN" — sharp drop at break point
            "GRADUAL" — progressive decline
            "RECOVERED" — dropped but recovered
            "COLLAPSED" — dropped and stayed down
            "INSUFFICIENT_SENTENCES" — too few sentences
        mean_isi : float
            Mean ISI across all sentences.
        min_isi : float
            Minimum ISI across all sentences.
        is_anomalous : bool
            True if drift type is SUDDEN, GRADUAL, or COLLAPSED.
        penalty : float
            Multiplicative penalty factor.
    """
    # Split response into sentences
    sentences = _split_sentences(response)

    if len(sentences) < MIN_SENTENCES:
        return {
            "sentences": sentences,
            "sentence_count": len(sentences),
            "trajectory": [],
            "break_point": None,
            "break_sentence": None,
            "drift_type": "INSUFFICIENT_SENTENCES",
            "mean_isi": 0.0,
            "min_isi": 0.0,
            "is_anomalous": False,
            "penalty": 1.0,
        }

    # Compute source token set once
    source_set = _token_set(source)

    # Compute ISI for each sentence
    trajectory = []
    for i, sentence in enumerate(sentences):
        sent_set = _token_set(sentence)
        isi = _lexical_isi(source_set, sent_set)

        trajectory.append({
            "sentence_index": i,
            "sentence": sentence[:100],  # truncate for output
            "isi": round(isi, 4),
            "is_coherent": isi >= kappa_d,
            "is_collapsed": isi < kappa_r,
        })

    # Find break point: first sentence where ISI < κR
    break_point = None
    break_sentence = None
    for i, t in enumerate(trajectory):
        if t["is_collapsed"]:
            break_point = i
            break_sentence = sentences[i]
            break

    # Classify drift type
    isis = [t["isi"] for t in trajectory]
    mean_isi = sum(isis) / max(len(isis), 1)
    min_isi = min(isis)

    if break_point is None:
        # No collapse detected
        if all(t["is_coherent"] for t in trajectory):
            drift_type = "STABLE"
        else:
            # Some sentences below κD but none below κR
            drift_type = "GRADUAL"
    else:
        # Collapse detected — check if it recovered
        recovered = any(
            t["isi"] > kappa_r + RECOVERY_THRESHOLD
            for t in trajectory[break_point + 1:]
        )
        if recovered:
            drift_type = "RECOVERED"
        else:
            # Check if drop was sudden or gradual
            if break_point > 0:
                prev_isi = trajectory[break_point - 1]["isi"]
                curr_isi = trajectory[break_point]["isi"]
                delta = prev_isi - curr_isi
                if delta >= SUDDEN_DROP_THRESHOLD:
                    drift_type = "SUDDEN"
                else:
                    drift_type = "GRADUAL"
            else:
                drift_type = "SUDDEN"

    is_anomalous = drift_type in ("SUDDEN", "GRADUAL", "COLLAPSED")
    penalty = DRIFT_PENALTY_BASE if is_anomalous else 1.0

    return {
        "sentences": sentences,
        "sentence_count": len(sentences),
        "trajectory": trajectory,
        "break_point": break_point,
        "break_sentence": break_sentence[:200] if break_sentence else None,
        "drift_type": drift_type,
        "mean_isi": round(mean_isi, 4),
        "min_isi": round(min_isi, 4),
        "is_anomalous": is_anomalous,
        "penalty": round(penalty, 4),
    }