from pathlib import Path

from src.config import RecommendationDefaults
from src.skills import load_skill_profile


def test_load_skill_profile_overrides(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_file = skills_dir / "AAPL.md"
    skill_file.write_text(
        """---
symbol: "AAPL"
min_return_pct: 3.5
max_drop_pct: 1.5
stooq_symbol: "aapl.us"
notes: "Test notes"
---
Body text
""",
        encoding="utf-8",
    )

    defaults = RecommendationDefaults(min_return_pct=2.0, max_drop_pct=2.0)
    profile = load_skill_profile("AAPL", skills_dir, defaults)

    assert profile.symbol == "AAPL"
    assert profile.min_return_pct == 3.5
    assert profile.max_drop_pct == 1.5
    assert profile.stooq_symbol == "aapl.us"
    assert profile.notes == "Test notes"


def test_load_skill_profile_missing_file(tmp_path: Path) -> None:
    defaults = RecommendationDefaults(min_return_pct=2.0, max_drop_pct=2.0)
    profile = load_skill_profile("MSFT", tmp_path, defaults)
    assert profile.symbol == "MSFT"
    assert profile.min_return_pct == 2.0
    assert profile.max_drop_pct == 2.0
