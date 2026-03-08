import numpy as np

from aiblock.detectors.base import DetectionResult


def aggregate(
    results: list[list[DetectionResult]],
    weights: dict[str, float],
    threshold: float = 0.5,
) -> dict:
    """
    Combine per-chunk, per-detector results into a final verdict.

    Args:
        results: outer list = chunks, inner list = one result per detector per chunk
        weights: detector name → relative weight (need not sum to 1)
        threshold: score above this → "AI"

    Returns:
        {
            "verdict": "AI" | "Human",
            "score": float,        # weighted average AI probability
            "confidence": float,   # mean detector confidence
            "chunks": int,
        }
    """
    if not results:
        return {"verdict": "Unknown", "score": 0.0, "confidence": 0.0, "chunks": 0}

    total_weight = sum(weights.get(r.detector, 1.0) for chunk in results for r in chunk)
    if total_weight == 0:
        total_weight = 1.0

    chunk_scores = []
    for chunk in results:
        weighted_score = sum(
            r.score * weights.get(r.detector, 1.0) for r in chunk
        )
        chunk_weight = sum(weights.get(r.detector, 1.0) for r in chunk)
        chunk_scores.append(weighted_score / chunk_weight if chunk_weight else 0.0)

    score = float(np.median(chunk_scores))

    all_confidences = [r.confidence for chunk in results for r in chunk]
    confidence = float(np.mean(all_confidences)) if all_confidences else 0.0

    return {
        "verdict": "AI" if score >= threshold else "Human",
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "chunks": len(results),
    }
