from pathlib import Path

from src.config import load_config, update_config_payload


def test_load_config_allows_empty_tickers(tmp_path: Path) -> None:
    config_path = tmp_path / "portfolio.json"
    config_path.write_text(
        """
{
  "portfolio_name": "Test",
  "tickers": []
}
""".strip(),
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.tickers == []


def test_update_config_payload_merges_nested_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "portfolio.json"
    config_path.write_text(
        """
{
  "portfolio_name": "Test",
  "tickers": ["AAPL"],
  "recommendation_defaults": {
    "min_return_pct": 2.0,
    "max_drop_pct": 2.0
  },
  "sentiment_enabled": true
}
""".strip(),
        encoding="utf-8",
    )

    merged = update_config_payload(
        config_path,
        {
            "sentiment_enabled": False,
            "recommendation_defaults": {"min_return_pct": 3.5},
        },
    )
    assert merged["sentiment_enabled"] is False
    assert merged["recommendation_defaults"]["min_return_pct"] == 3.5
    assert merged["recommendation_defaults"]["max_drop_pct"] == 2.0

    config = load_config(config_path)
    assert config.sentiment_enabled is False
    assert config.recommendation_defaults.min_return_pct == 3.5
    assert config.recommendation_defaults.max_drop_pct == 2.0
