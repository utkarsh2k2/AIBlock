import numpy as np

from aiblock.detectors.base import DetectionResult

# Global thresholds for downstream consumers (labeling, UI buckets)
AI_STRICT = 0.8
HUMAN_STRICT = 0.2
GAME_CUTOFF = 0.5


def aggregate(
    results: list[list[DetectionResult]],
    weights: dict[str, float],
    threshold: float = 0.5,
) -> dict:
    """
    Combine per-chunk, per-detector results into a final verdict.

    This implementation follows a confidence‑weighted aggregation:

        ai_score = sum(w_i * c_i * s_i) / sum(w_i * c_i)

    where:
      * s_i is the detector's AI probability (0.0 = human, 1.0 = AI)
      * c_i is the detector's confidence for this clip (0.0–1.0)
      * w_i is the detector's expert weight from the config

    Args:
        results: outer list = chunks, inner list = one result per detector per chunk
        weights: detector name → relative weight (need not sum to 1)
        threshold: score above this → "AI"

    Returns:
        {
            "verdict": "AI" | "Human" | "Unknown",
            "is_ai": bool | None,
            "ai_score": float,          # confidence‑weighted AI probability
            "score": float,             # alias for ai_score (backwards‑compatible)
            "confidence": float,        # distance from 0.5, scaled to [0, 1]
            "chunks": int,
            "detailed_scores": {detector_name: float},  # per‑detector AI scores
        }
    """
    if not results:
        return {
            "verdict": "Unknown",
            "is_ai": None,
            "ai_score": 0.0,
            "score": 0.0,
            "confidence": 0.0,
            "chunks": 0,
            "detailed_scores": {},
        }

    # Flatten all DetectionResult entries
    flat: list[DetectionResult] = [r for chunk in results for r in chunk]

    # Global confidence‑weighted aggregation
    num = 0.0
    den = 0.0

    # Per‑detector breakdowns for detailed_scores
    det_num: dict[str, float] = {}
    det_den: dict[str, float] = {}

    for r in flat:
        w = float(weights.get(r.detector, 1.0))
        c = float(r.confidence) if r.confidence is not None else 1.0
        s = float(r.score)

        wc = w * c
        num += wc * s
        den += wc

        det_num[r.detector] = det_num.get(r.detector, 0.0) + wc * s
        det_den[r.detector] = det_den.get(r.detector, 0.0) + wc

    if den <= 0.0:
        ai_score = 0.5  # fall back to agnostic
    else:
        ai_score = num / den

    # Global confidence is how far we are from the 0.5 decision boundary
    confidence = 2.0 * abs(ai_score - 0.5)
    confidence = float(np.clip(confidence, 0.0, 1.0))

    # Per‑detector scores (still confidence‑weighted)
    detailed_scores: dict[str, float] = {}
    for name, n in det_num.items():
        d = det_den.get(name, 0.0)
        if d > 0.0:
            detailed_scores[name] = round(n / d, 4)

    is_ai: bool | None
    verdict: str
    if den <= 0.0:
        is_ai = None
        verdict = "Unknown"
    else:
        is_ai = ai_score >= threshold
        verdict = "AI" if is_ai else "Human"

    return {
        "verdict": verdict,
        "is_ai": is_ai,
        "ai_score": round(float(ai_score), 4),
        # Keep "score" for backwards‑compatibility with existing clients.
        "score": round(float(ai_score), 4),
        "confidence": round(confidence, 4),
        "chunks": len(results),
        "detailed_scores": detailed_scores,
        "thresholds": {
            "ai_strict": AI_STRICT,
            "human_strict": HUMAN_STRICT,
            "game_cutoff": GAME_CUTOFF,
        },
    }
