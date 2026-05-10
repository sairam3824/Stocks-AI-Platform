from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .config import RecommendationDefaults


@dataclass
class SkillProfile:
    symbol: str
    stooq_symbol: Optional[str]
    min_return_pct: float
    max_drop_pct: float
    market: str = ""
    notes: str = ""


def _parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    if len(lines) < 2:
        return {}, text

    front_lines = []
    body_start = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            body_start = idx + 1
            break
        front_lines.append(lines[idx])

    if body_start is None:
        return {}, text

    front_text = "\n".join(front_lines)
    body_text = "\n".join(lines[body_start:])
    data = yaml.safe_load(front_text) or {}
    return data, body_text


def load_skill_profile(
    ticker: str,
    skills_dir: Path,
    defaults: RecommendationDefaults,
) -> SkillProfile:
    path = skills_dir / f"{ticker.upper()}.md"
    if not path.exists():
        return SkillProfile(
            symbol=ticker.upper(),
            stooq_symbol=None,
            min_return_pct=defaults.min_return_pct,
            max_drop_pct=defaults.max_drop_pct,
            notes="",
        )

    text = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(text)

    symbol = str(meta.get("symbol") or ticker).upper()
    stooq_symbol = meta.get("stooq_symbol")
    min_return_pct = float(meta.get("min_return_pct", defaults.min_return_pct))
    max_drop_pct = float(meta.get("max_drop_pct", defaults.max_drop_pct))
    market = str(meta.get("market") or "").strip()
    notes = str(meta.get("notes") or body.strip())

    return SkillProfile(
        symbol=symbol,
        stooq_symbol=stooq_symbol,
        min_return_pct=min_return_pct,
        max_drop_pct=max_drop_pct,
        market=market,
        notes=notes,
    )
