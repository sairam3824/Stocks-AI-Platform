from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class ReportSummary:
    date: str
    link: str
    top_lines: List[str]


def _format_line(item: dict) -> str:
    symbol = item.get("symbol", "")
    signal = item.get("signal", "")
    expected = item.get("expected_return_pct", 0.0)
    return f"{symbol}: {signal} ({expected:.2f}%)"


def collect_reports(reports_dir: Path, top_n: int) -> List[ReportSummary]:
    summaries: List[ReportSummary] = []
    if not reports_dir.exists():
        return summaries

    for report_dir in sorted(reports_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not report_dir.is_dir():
            continue

        summary_path = report_dir / "summary.json"
        if not summary_path.exists():
            continue

        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        sorted_rows = sorted(data, key=lambda r: r.get("score", 0.0), reverse=True)
        top_lines = [_format_line(row) for row in sorted_rows[:top_n]]

        summaries.append(
            ReportSummary(
                date=report_dir.name,
                link=f"{report_dir.name}/index.html",
                top_lines=top_lines,
            )
        )

    return summaries


def build_site_index_html(portfolio_name: str, reports: List[ReportSummary]) -> str:
    cards_html = []
    for report in reports:
        top_html = "".join(f"<li>{line}</li>" for line in report.top_lines) or "<li>No data</li>"
        cards_html.append(
            "\n".join(
                [
                    "<div class=\"card\">",
                    f"  <div class=\"card-date\">{report.date}</div>",
                    f"  <a class=\"card-link\" href=\"{report.link}\">Open report</a>",
                    "  <ul>",
                    f"    {top_html}",
                    "  </ul>",
                    "</div>",
                ]
            )
        )

    cards = "\n".join(cards_html) if cards_html else "<p>No reports yet.</p>"

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{portfolio_name} Reports</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f4f6fb; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 6px 0; }}
    .sub {{ color: #555; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }}
    .card {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .card-date {{ font-weight: bold; margin-bottom: 8px; }}
    .card-link {{ display: inline-block; margin-bottom: 10px; color: #1f77b4; text-decoration: none; }}
    ul {{ margin: 0; padding-left: 18px; }}
  </style>
</head>
<body>
  <header>
    <h1>{portfolio_name} Forecast Reports</h1>
    <div class=\"sub\">Local dashboard of all generated reports.</div>
  </header>
  <section class=\"grid\">
    {cards}
  </section>
</body>
</html>"""
