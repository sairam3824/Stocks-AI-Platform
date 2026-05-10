from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import List

import pandas as pd

from .recommendations import Recommendation


def write_summary(
    recommendations: List[Recommendation],
    output_dir: Path,
    chart_links: dict[str, str] | None = None,
    file_prefix: str = "summary",
) -> pd.DataFrame:
    chart_links = chart_links or {}
    rows = []
    for rec in recommendations:
        row = asdict(rec)
        row["chart_link"] = chart_links.get(rec.symbol, "")
        rows.append(row)
    df = pd.DataFrame(rows)

    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / f"{file_prefix}.csv"
    json_path = output_dir / f"{file_prefix}.json"
    xlsx_path = output_dir / f"{file_prefix}.xlsx"

    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)
    try:
        df.to_excel(xlsx_path, index=False)
    except Exception:
        pass

    return df


def _format_pct(value: float) -> str:
    return f"{value:.2f}%"


def build_index_html(
    portfolio_name: str,
    date_label: str,
    summary_df: pd.DataFrame,
    chart_links: dict[str, str],
    top_symbols: List[str],
    intraday_summary_path: Path | None = None,
    intraday_links: dict[str, str] | None = None,
) -> str:
    intraday_links = intraday_links or {}
    rows_html = []
    if summary_df.empty:
        rows_html.append(
            "\n".join(
                [
                    "<tr>",
                    "  <td colspan=\"11\">No data available. Check data source settings.</td>",
                    "</tr>",
                ]
            )
        )
    else:
        for _, row in summary_df.iterrows():
            symbol = row["symbol"]
            link = chart_links.get(symbol, "#")
            highlight = "highlight" if symbol in top_symbols else ""
            class_attr = f" class=\"{highlight}\"" if highlight else ""
            rows_html.append(
                "\n".join(
                    [
                        f"<tr{class_attr}>",
                        f"  <td><a href=\"{link}\">{symbol}</a></td>",
                        f"  <td>{row.get('model_name', 'N/A')}</td>",
                        f"  <td>{row.get('confidence_pct', 0.0):.1f}%</td>",
                        f"  <td>{_format_pct(row['expected_return_pct'])}</td>",
                        f"  <td>{row['signal']}</td>",
                        f"  <td>{row['score']:.2f}</td>",
                        f"  <td>{row.get('sentiment_label', 'Neutral')}</td>",
                        f"  <td>{row.get('sentiment_score', 0.0):.2f}</td>",
                        f"  <td>{row['last_close']:.2f}</td>",
                        f"  <td>{row['forecast_end']:.2f}</td>",
                        f"  <td>{row.get('reasoning', '')}</td>",
                        f"</tr>",
                    ]
                )
            )

    table_html = "\n".join(rows_html)

    intraday_section = ""
    if intraday_summary_path and intraday_summary_path.exists():
        try:
            intraday_df = pd.read_json(intraday_summary_path)
        except ValueError:
            intraday_df = pd.DataFrame()

        intraday_rows = []
        if intraday_df.empty:
            intraday_rows.append(
                "\n".join(
                [
                    "<tr>",
                    "  <td colspan=\"11\">No intraday data available.</td>",
                    "</tr>",
                ]
            )
            )
        else:
            for _, row in intraday_df.iterrows():
                symbol = row["symbol"]
                link = intraday_links.get(symbol, row.get("chart_link", "#"))
                intraday_rows.append(
                    "\n".join(
                        [
                            "<tr>",
                            f"  <td><a href=\"{link}\">{symbol}</a></td>",
                            f"  <td>{row.get('model_name', 'N/A')}</td>",
                            f"  <td>{row.get('confidence_pct', 0.0):.1f}%</td>",
                            f"  <td>{_format_pct(row['expected_return_pct'])}</td>",
                            f"  <td>{row['signal']}</td>",
                            f"  <td>{row['score']:.2f}</td>",
                            f"  <td>{row.get('sentiment_label', 'Neutral')}</td>",
                            f"  <td>{row.get('sentiment_score', 0.0):.2f}</td>",
                            f"  <td>{row['last_close']:.2f}</td>",
                            f"  <td>{row['forecast_end']:.2f}</td>",
                            f"  <td>{row.get('reasoning', '')}</td>",
                            "</tr>",
                        ]
                    )
                )

        intraday_section = f"""
    <h2 style="margin-top: 32px;">Intraday Forecast</h2>
    <div class="search-container" style="margin-bottom: 12px;">
      <a class="pill" href="summary_intraday.csv">Download CSV</a>
      <a class="pill" href="summary_intraday.xlsx">Download Excel</a>
    </div>
    <table class="sortable-table">
      <thead>
        <tr>
          <th class="sortable" data-type="text">Symbol</th>
          <th class="sortable" data-type="text">Model</th>
          <th class="sortable" data-type="number">Confidence</th>
          <th class="sortable" data-type="number">Expected Return</th>
          <th class="sortable" data-type="text">Signal</th>
          <th class="sortable" data-type="number">Score</th>
          <th class="sortable" data-type="text">Sentiment</th>
          <th class="sortable" data-type="number">Sentiment Score</th>
          <th class="sortable" data-type="number">Last Close</th>
          <th class="sortable" data-type="number">Forecast End</th>
          <th class="sortable" data-type="text">Why</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(intraday_rows)}
      </tbody>
    </table>
"""
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{portfolio_name} Forecast - {date_label}</title>
  <style>
    :root {{
      --accent: #0c7c7b;
      --border: #d9e2ec;
      --muted: #5c6c7a;
    }}
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f7f7fb; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 4px 0; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e6e6ef; text-align: left; }}
    th {{ background: #f0f0f7; }}
    tr.highlight {{ background: #fff8e6; }}
    a {{ color: var(--accent); text-decoration: none; }}
    .meta {{ color: #555; margin-top: 4px; }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: white;
      padding: 12px 16px;
      border: 1px solid var(--border);
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
      position: sticky;
      top: 46px;
      z-index: 10;
    }}
    .app-nav {{
      position: sticky;
      top: 0;
      z-index: 20;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #0f172a;
      color: #e2e8f0;
      padding: 10px 16px;
      border-bottom: 1px solid #1e293b;
    }}
    .app-brand {{
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .app-links {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 14px;
      flex-wrap: wrap;
    }}
    .app-links a {{
      color: #cbd5e1;
      text-decoration: none;
      font-weight: 600;
    }}
    .app-links a:hover {{
      color: white;
    }}
    .back-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
    }}
    .pill {{
      background: #eef2f7;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      color: var(--muted);
    }}
    .crumbs {{
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      flex-wrap: wrap;
    }}
    .crumbs a {{
      color: var(--accent);
      font-weight: 600;
    }}
    .page {{
      padding: 24px;
    }}
    th.sortable {{
      cursor: pointer;
      position: sticky;
      top: 102px; /* Below app nav + topbar */
      background: #f0f0f7;
      z-index: 5;
    }}
    th.sortable:hover {{
      background: #e2e2ec;
    }}
    th.sortable::after {{
      content: '↕';
      font-size: 12px;
      margin-left: 6px;
      color: var(--muted);
      opacity: 0.5;
    }}
    th.sortable.asc::after {{
      content: '↑';
      color: var(--accent);
      opacity: 1;
    }}
    th.sortable.desc::after {{
      content: '↓';
      color: var(--accent);
      opacity: 1;
    }}
    .search-container {{
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .search-input {{
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 14px;
      width: 100%;
      max-width: 300px;
    }}
  </style>
</head>
<body>
  <div class=\"app-nav\">
    <div class=\"app-brand\">Stocks AI</div>
    <div class=\"app-links\">
      <a href=\"/dashboard\">Dashboard</a>
      <a href=\"/live\">Live</a>
      <a href=\"/trades\">Trades</a>
      <a href=\"/models\">Models</a>
      <a href=\"/settings/engine\">Engine</a>
      <a href=\"/settings/security\">Security</a>
      <a href=\"/reports\">Reports</a>
      <a href=\"/logout\">Logout</a>
    </div>
  </div>
  <div class=\"topbar\">
    <div class=\"crumbs\">
      <a href=\"/dashboard\">Home</a>
      <span>›</span>
      <a href=\"/reports\">Reports</a>
      <span>›</span>
      <span>{date_label}</span>
    </div>
    <div class=\"back-link\">
      <a href=\"/dashboard\">Home</a>
      <span>·</span>
      <a href=\"/reports\">All Reports</a>
    </div>
  </div>
  <div class=\"page\">
    <header>
      <h1>{portfolio_name} Forecast</h1>
      <div class=\"meta\">{date_label} · Top picks highlighted</div>
    </header>
    
    <div class=\"search-container\">
      <span>🔍</span>
      <input type=\"text\" id=\"table-search\" class=\"search-input\" placeholder=\"Filter symbols or signals...\" autocomplete=\"off\">
      <select id=\"sort-column\" class=\"search-input\" style=\"max-width: 200px;\">
        <option value=\"0\">Symbol</option>
        <option value=\"1\">Model</option>
        <option value=\"2\">Confidence</option>
        <option value=\"3\">Expected Return</option>
        <option value=\"4\">Signal</option>
        <option value=\"5\">Score</option>
        <option value=\"6\">Sentiment</option>
        <option value=\"7\">Sentiment Score</option>
        <option value=\"8\">Last Close</option>
        <option value=\"9\">Forecast End</option>
      </select>
      <button id=\"sort-asc\" class=\"pill\" type=\"button\">Sort ↑</button>
      <button id=\"sort-desc\" class=\"pill\" type=\"button\">Sort ↓</button>
      <a class=\"pill\" href=\"summary.csv\">Download CSV</a>
      <a class=\"pill\" href=\"summary.xlsx\">Download Excel</a>
    </div>

    <h2>Monthly Forecast</h2>
    <table id=\"report-table\" class=\"sortable-table\">
      <thead>
        <tr>
          <th class=\"sortable\" data-type=\"text\">Symbol</th>
          <th class=\"sortable\" data-type=\"text\">Model</th>
          <th class=\"sortable\" data-type=\"number\">Confidence</th>
          <th class=\"sortable\" data-type=\"number\">Expected Return</th>
          <th class=\"sortable\" data-type=\"text\">Signal</th>
          <th class=\"sortable\" data-type=\"number\">Score</th>
          <th class=\"sortable\" data-type=\"text\">Sentiment</th>
          <th class=\"sortable\" data-type=\"number\">Sentiment Score</th>
          <th class=\"sortable\" data-type=\"number\">Last Close</th>
          <th class=\"sortable\" data-type=\"number\">Forecast End</th>
          <th class=\"sortable\" data-type=\"text\">Why</th>
        </tr>
      </thead>
      <tbody>
{table_html}
      </tbody>
    </table>
    {intraday_section}
  </div>
  <script>
    (function() {{
      const searchInput = document.getElementById('table-search');

      const setupTable = (table) => {{
        if (!table) return;
        const getCellValue = (row, idx) => row.children[idx].innerText.trim();
        const comparer = (idx, type, asc) => (a, b) => {{
          const v1 = getCellValue(asc ? a : b, idx);
          const v2 = getCellValue(asc ? b : a, idx);
          if (type === 'number') {{
            const n1 = parseFloat(v1.replace('%','')) || 0;
            const n2 = parseFloat(v2.replace('%','')) || 0;
            return n1 - n2;
          }}
          return v1.localeCompare(v2);
        }};

        table.querySelectorAll('th.sortable').forEach((th, idx) => {{
          let asc = true;
          th.addEventListener('click', () => {{
            const tbody = table.tBodies[0];
            Array.from(tbody.querySelectorAll('tr'))
              .sort(comparer(idx, th.dataset.type, asc))
              .forEach(tr => tbody.appendChild(tr));

            table.querySelectorAll('th.sortable').forEach(header => {{
              header.classList.remove('asc', 'desc');
            }});
            th.classList.add(asc ? 'asc' : 'desc');
            asc = !asc;
          }});
        }});
      }};

      document.querySelectorAll('table.sortable-table').forEach(setupTable);

      if (searchInput) {{
        searchInput.addEventListener('input', (e) => {{
          const term = e.target.value.toLowerCase();
          document.querySelectorAll('table.sortable-table tbody tr').forEach(row => {{
            const text = row.innerText.toLowerCase();
            row.style.display = text.includes(term) ? '' : 'none';
          }});
          localStorage.setItem('reportSearch', term);
        }});
        const saved = localStorage.getItem('reportSearch');
        if (saved) {{
          searchInput.value = saved;
          const event = new Event('input');
          searchInput.dispatchEvent(event);
        }}
      }}

      const sortColumn = document.getElementById('sort-column');
      const sortAsc = document.getElementById('sort-asc');
      const sortDesc = document.getElementById('sort-desc');
      const reportTable = document.getElementById('report-table');

      function applySort(asc) {{
        if (!reportTable || !sortColumn) return;
        const idx = parseInt(sortColumn.value, 10);
        const th = reportTable.querySelectorAll('th.sortable')[idx];
        if (!th) return;
        const tbody = reportTable.tBodies[0];
        const type = th.dataset.type;
        const getCellValue = (row, idx) => row.children[idx].innerText.trim();
        const comparer = (idx, type, asc) => (a, b) => {{
          const v1 = getCellValue(asc ? a : b, idx);
          const v2 = getCellValue(asc ? b : a, idx);
          if (type === 'number') {{
            const n1 = parseFloat(v1.replace('%','')) || 0;
            const n2 = parseFloat(v2.replace('%','')) || 0;
            return n1 - n2;
          }}
          return v1.localeCompare(v2);
        }};
        Array.from(tbody.querySelectorAll('tr'))
          .sort(comparer(idx, type, asc))
          .forEach(tr => tbody.appendChild(tr));
        localStorage.setItem('reportSortColumn', sortColumn.value);
        localStorage.setItem('reportSortAsc', asc ? '1' : '0');
      }}

      if (sortAsc) sortAsc.addEventListener('click', () => applySort(true));
      if (sortDesc) sortDesc.addEventListener('click', () => applySort(false));

      if (sortColumn) {{
        const savedColumn = localStorage.getItem('reportSortColumn');
        const savedAsc = localStorage.getItem('reportSortAsc');
        if (savedColumn) sortColumn.value = savedColumn;
        if (savedAsc !== null) {{
          applySort(savedAsc === '1');
        }}
      }}
    }})();
  </script>
</body>
</html>"""
