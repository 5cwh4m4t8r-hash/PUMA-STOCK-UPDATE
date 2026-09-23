from __future__ import annotations


def classify_scores(danta_score: int, swing_score: int, bowl_score: int) -> tuple[str, str]:
    """Condition-search display classification only.

    This does not place orders. It summarizes which PUMA analysis family
    currently fits the candidate best.
    """
    d = max(0, min(100, int(danta_score or 0)))
    s = max(0, min(100, int(swing_score or 0)))
    b = max(0, min(100, int(bowl_score or 0)))

    tags: list[str] = []
    if d >= 55:
        tags.append("단타")
    if s >= 55:
        tags.append("스윙")
    if b >= 55:
        tags.append("중장기(밥3)")

    if tags:
        label = "+".join(tags)
    else:
        best = max((d, "단타관찰"), (s, "스윙관찰"), (b, "밥3관찰"), key=lambda x: x[0])
        label = best[1] if best[0] >= 25 else "관찰"

    detail = f"단 {d} · 스 {s} · 밥3 {b}"
    return label, detail


def bucket_scores(scores: dict | None, threshold: int = 55) -> dict[str, int]:
    """Return only strategy buckets that actually pass the PUMA threshold."""
    scores = dict(scores or {})
    out: dict[str, int] = {}
    for key in ("danta", "swing", "bowl"):
        value = max(0, min(100, int(scores.get(key, 0) or 0)))
        if value >= int(threshold):
            out[key] = value
    return out
