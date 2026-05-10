from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


def build_forecast_chart(
    history: pd.DataFrame,
    forecast: pd.DataFrame,
    title: str,
) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=history["date"],
            y=history["close"],
            name="Close",
            line=dict(color="#1f77b4", width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=forecast["date"],
            y=forecast["forecast"],
            name="Forecast",
            line=dict(color="#ff7f0e", width=2, dash="dash"),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=forecast["date"],
            y=forecast["upper"],
            name="Upper",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast["date"],
            y=forecast["lower"],
            name="Confidence",
            fill="tonexty",
            fillcolor="rgba(255, 127, 14, 0.2)",
            line=dict(width=0),
        )
    )

    if not history.empty:
        last_date = history["date"].iloc[-1]
        fig.add_vline(
            x=last_date,
            line_width=1,
            line_dash="dot",
            line_color="gray",
        )

    fig.update_layout(
        title=title,
        template="plotly_white",
        xaxis_title="Date",
        yaxis_title="Price",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        height=500,
    )

    return fig


def save_chart(
    fig: go.Figure,
    output_path: Path,
    nav_url: str = "index.html",
    report_label: str = "",
    dashboard_url: str = "/dashboard",
    reports_url: str = "/reports",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig_html = pio.to_html(fig, include_plotlyjs="cdn", full_html=False)
    breadcrumb_report = report_label or "Report"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{output_path.stem} Forecast</title>
  <style>
    :root {{
      --accent: #0c7c7b;
      --border: #d9e2ec;
      --muted: #5c6c7a;
    }}
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f7f7fb; }}
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
    .topbar {{
      position: sticky;
      top: 46px;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: white;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
    }}
    .crumbs {{
      display: flex;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 13px;
      flex-wrap: wrap;
    }}
    .crumbs a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    .page {{
      padding: 24px;
    }}
  </style>
</head>
<body>
  <div class="app-nav">
    <div class="app-brand">Stocks AI</div>
    <div class="app-links">
      <a href="/dashboard">Dashboard</a>
      <a href="/live">Live</a>
      <a href="/trades">Trades</a>
      <a href="/models">Models</a>
      <a href="/settings/engine">Engine</a>
      <a href="/settings/security">Security</a>
      <a href="/reports">Reports</a>
      <a href="/logout">Logout</a>
    </div>
  </div>
  <div class="topbar">
    <div class="crumbs">
      <a href="{dashboard_url}">Home</a>
      <span>›</span>
      <a href="{reports_url}">Reports</a>
      <span>›</span>
      <a href="{nav_url}">{breadcrumb_report}</a>
      <span>›</span>
      <span>{output_path.stem}</span>
    </div>

  </div>
  <div class="page">
    {fig_html}
  </div>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")
