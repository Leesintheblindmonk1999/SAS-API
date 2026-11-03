"""Regression test: flow_coherence must not fire on identical text.

Bug (found 2026-11-03 on MedHallu): scan_entropy_spikes compared each
segment's entropy against the document-wide mean instead of the
corresponding segment of A. A long paragraph has higher entropy than a
short one regardless of content, so 406/10,000 A→A pairs scored ISI 0.85
instead of 1.0000.

Run: python tests/test_flow_identity.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.flow_coherence import (
    run_flow_coherence,
    scan_entropy_spikes,
    calculate_local_entropy,
    _split_segments,
)


# Real MedHallu record that triggered the bug (id c3f0d3d640516c1b).
# Segment 1 is a long paragraph with entropy 1.30x the document mean.
HETEROGENEOUS_TEXT = """Question: Do mitochondria play a role in remodelling lace plant leaves during programmed cell death?

Knowledge: Programmed cell death (PCD) is the regulated death of cells within an organism. The lace plant (Aponogeton madagascariensis) produces perforations in its leaves through PCD. The leaves of the lace plant begin as solid structures and develop perforations as they mature. This process is developmentally regulated and involves the coordinated death of specific cell types.

Results depicted mitochondrial dynamics in vivo as PCD progresses within the lace plant, and highlight the correlation of this organelle with other organelles during developmental PCD. To the best of our knowledge, this is the first report of mitochondria and chloroplasts moving on transvacuolar strands during developmental PCD in a plant. Mitochondria were observed to undergo dynamic changes in morphology and distribution throughout the PCD process, including elongation, fragmentation, and movement along transvacuolar strands. These changes correlated temporally with the progression of PCD and with alterations in chloroplast positioning and morphology. The coordinated movement of these organelles suggests a functional relationship during the execution of developmental PCD in the lace plant.

Ground Truth: Mitochondria regulate the formation of perforations in lace plant leaves through the modulation of calcium channels and by activating specific proteases that degrade cellular structures, facilitating the PCD process."""


def test_identical_text_no_spikes():
    """scan_entropy_spikes(A, A) must return zero spikes."""
    spikes, idx = scan_entropy_spikes(HETEROGENEOUS_TEXT, HETEROGENEOUS_TEXT)
    assert spikes == [], f"Expected 0 spikes on identical text, got {len(spikes)}: {idx}"
    assert idx == [], f"Expected empty indices, got {idx}"
    print("PASS: identical text produces 0 entropy spikes")


def test_identical_text_no_penalty():
    """run_flow_coherence(A, A) must return combined_penalty 1.0."""
    res = run_flow_coherence(HETEROGENEOUS_TEXT, HETEROGENEOUS_TEXT)
    assert res.entropy_penalty == 1.0, f"entropy_penalty={res.entropy_penalty}"
    assert res.flow_penalty == 1.0, f"flow_penalty={res.flow_penalty}"
    assert res.combined_penalty == 1.0, f"combined_penalty={res.combined_penalty}"
    assert res.layer4_fired is False, f"layer4_fired={res.layer4_fired}"
    print("PASS: identical text produces no penalty")


def test_heterogeneous_entropy_present():
    """Sanity: the test text must actually have heterogeneous segment entropy.

    If this fails, the regression test is no longer exercising the bug.
    """
    prof = calculate_local_entropy(HETEROGENEOUS_TEXT)
    assert len(prof) >= 2, f"Expected >=2 segments, got {len(prof)}"
    entropies = [s.entropy for s in prof]
    spread = max(entropies) - min(entropies)
    assert spread > 0.5, f"Segment entropy spread too small ({spread:.3f}); test text is not heterogeneous"
    print(f"PASS: test text is heterogeneous (entropy spread {spread:.3f})")


def test_injection_still_detected():
    """The fix must not disable detection: injected vocabulary must still fire."""
    injected = HETEROGENEOUS_TEXT.replace(
        "Ground Truth: Mitochondria regulate the formation of perforations in lace plant leaves through the modulation of calcium channels and by activating specific proteases that degrade cellular structures, facilitating the PCD process.",
        "Ground Truth: Quantum entanglement in superconducting niobium resonators enables topological error correction through anyonic braiding statistics, yielding fault-tolerant computation at millikelvin temperatures."
    )
    assert injected != HETEROGENEOUS_TEXT, "Replacement failed"
    res = run_flow_coherence(HETEROGENEOUS_TEXT, injected)
    assert res.layer4_fired is True, "Injected vocabulary must still trigger layer 4"
    assert res.combined_penalty < 1.0, f"Expected penalty < 1.0, got {res.combined_penalty}"
    print(f"PASS: injection still detected (combined_penalty={res.combined_penalty})")


if __name__ == "__main__":
    test_heterogeneous_entropy_present()
    test_identical_text_no_spikes()
    test_identical_text_no_penalty()
    test_injection_still_detected()
    print("\nAll flow identity regression tests passed.")
