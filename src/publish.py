from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from .config import load_config
from .site import build_site_index_html, collect_reports


def _latest_report_dir(reports_dir: Path) -> Path | None:
    if not reports_dir.exists():
        return None

    candidates = [p for p in reports_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None

    return sorted(candidates, key=lambda p: p.name)[-1]


def _copy_reports(reports_dir: Path, publish_dir: Path) -> None:
    if not reports_dir.exists():
        return

    publish_dir.mkdir(parents=True, exist_ok=True)

    for report_dir in reports_dir.iterdir():
        if not report_dir.is_dir():
            continue
        target_dir = publish_dir / report_dir.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(report_dir, target_dir)


def publish_latest(config_path: Path) -> Path:
    config = load_config(config_path)
    latest_dir = _latest_report_dir(config.output_dir)
    publish_dir = config.publish_dir

    _copy_reports(config.output_dir, publish_dir)

    reports = collect_reports(config.output_dir, config.top_n)
    index_html = build_site_index_html(config.portfolio_name, reports)
    index_path = publish_dir / "index.html"
    publish_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(index_html, encoding="utf-8")

    if latest_dir is None:
        return publish_dir

    return publish_dir / latest_dir.name


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish latest report to docs")
    parser.add_argument(
        "--config",
        default="config/portfolio.json",
        help="Path to portfolio config",
    )
    args = parser.parse_args()
    publish_latest(Path(args.config))


if __name__ == "__main__":
    main()
