from __future__ import annotations

from collections import Counter
from typing import Iterable


def normalize_theme_rows(rows) -> list[dict]:
    """Normalize Kiwoom ka90001 theme rows into a compact stable shape."""
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("thema_grp_cd") or row.get("theme_code") or "").strip()
        name = str(row.get("thema_nm") or row.get("theme_name") or "").strip()
        key = code or name
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            change_pct = float(str(row.get("flu_rt") or row.get("change_pct") or "0").replace(",", "").replace("%", ""))
        except (TypeError, ValueError):
            change_pct = 0.0
        try:
            rising = int(float(str(row.get("rising_stk_num") or row.get("rising") or "0").replace(",", "")))
        except (TypeError, ValueError):
            rising = 0
        try:
            total = int(float(str(row.get("stk_num") or row.get("total") or "0").replace(",", "")))
        except (TypeError, ValueError):
            total = 0
        out.append({
            "code": code,
            "name": name,
            "change_pct": change_pct,
            "rising": rising,
            "total": total,
        })
    return out


def apply_theme_strength(candidates: Iterable[dict]) -> list[dict]:
    """Attach same-theme co-strength bonus without replacing the core PUMA score.

    Only candidates that are already strong enough by the normal intraday filters
    contribute to a theme cluster.  Therefore theme strength is a tie-break/bonus,
    never an independent buy signal.
    """
    rows = [dict(x) for x in candidates]
    counts: Counter[str] = Counter()

    def strong(row: dict) -> bool:
        live = row.get("live_puma_score")
        if live is not None:
            try:
                return int(live) >= 3
            except (TypeError, ValueError):
                return False
        try:
            return int(row.get("danta_score", 0) or 0) >= 70
        except (TypeError, ValueError):
            return False

    for row in rows:
        if not strong(row):
            continue
        keys = {
            str(t.get("code") or t.get("name") or "").strip()
            for t in row.get("themes", []) or []
            if isinstance(t, dict) and str(t.get("code") or t.get("name") or "").strip()
        }
        counts.update(keys)

    for row in rows:
        best_count = 0
        best_name = ""
        best_external = 0.0
        for theme in row.get("themes", []) or []:
            if not isinstance(theme, dict):
                continue
            key = str(theme.get("code") or theme.get("name") or "").strip()
            if not key:
                continue
            count = int(counts.get(key, 0))
            try:
                change_pct = float(theme.get("change_pct", 0) or 0)
            except (TypeError, ValueError):
                change_pct = 0.0
            if count > best_count or (count == best_count and change_pct > best_external):
                best_count = count
                best_name = str(theme.get("name") or key)
                best_external = change_pct

        # 2종목 동반부터 가점. 3종목 이상이면 더 높이되 과도한 테마 편향은 제한한다.
        peer_bonus = max(0, min(15, (best_count - 1) * 5))
        market_bonus = 0
        if best_count >= 2 and best_external > 0:
            market_bonus = min(5, max(1, int(best_external // 2) + 1))

        row["theme_peer_count"] = best_count
        row["theme_bonus"] = peer_bonus + market_bonus
        row["theme_name"] = best_name
        row["theme_change_pct"] = best_external

    return rows
