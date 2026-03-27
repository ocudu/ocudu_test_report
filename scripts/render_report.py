#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Render features.yaml into a self-contained HTML report."""

import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

DEFAULT_DATA_FILE = "features.yaml"
DEFAULT_OUTPUT_FILE = "features_report.html"

TEST_TYPE_COLORS = {
    "unit": "#4e9af1",
    "integration": "#f1a94e",
    "e2e": "#6bcb77",
}
SCOPE_COLORS = {
    "CU/DU": "#a78bfa",
    "Unspecified": "#94a3b8",
    "Entire RAN Product": "#38bdf8",
    "Platform/deployment/auxiliary component": "#fb923c",
}
TYPE_COLORS = {
    "Architecture": "#818cf8",
    "Functional":   "#34d399",
    "Performance":  "#f59e0b",
    "Security":     "#f87171",
    "O-Cloud":      "#38bdf8",
    "Management":   "#a78bfa",
}


def _load_features(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["features"]  # type: ignore


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f"border-radius:12px;font-size:0.78rem;font-weight:600;"
        f'white-space:nowrap">{text}</span>'
    )


def _bar_chart(counts: dict[str, int], colors: dict[str, str], total: int) -> str:
    if total == 0:
        return ""
    rows = ""
    for label, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        color = colors.get(label, "#64748b")
        rows += f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <div style="width:200px;font-size:0.85rem;color:#cbd5e1;text-align:right">{label}</div>
          <div style="flex:1;background:#1e293b;border-radius:4px;height:18px;overflow:hidden">
            <div style="width:{pct:.1f}%;background:{color};height:100%;border-radius:4px;
                        transition:width 0.3s"></div>
          </div>
          <div style="width:30px;font-size:0.85rem;color:#94a3b8">{count}</div>
        </div>"""
    return rows


def _render(features: list[dict]) -> str:
    total = len(features)
    release_counts = Counter(f["release"] for f in features)
    scope_counts = Counter(f["scope"] for f in features)
    source_counts = Counter(f["source"] for f in features)
    type_counts = Counter(f.get("type", "") for f in features if f.get("type"))
    test_type_counts: Counter = Counter()
    for f in features:
        for t in f.get("primary_test_type", []):
            test_type_counts[t] += 1

    # ── summary cards ────────────────────────────────────────────────────────
    def card(value: str, label: str) -> str:
        return f"""
        <div style="background:#1e293b;border-radius:10px;padding:20px 28px;
                    text-align:center;min-width:120px">
          <div style="font-size:2rem;font-weight:700;color:#f1f5f9">{value}</div>
          <div style="font-size:0.8rem;color:#94a3b8;margin-top:4px">{label}</div>
        </div>"""

    def type_card(label: str, count: int) -> str:
        color = TYPE_COLORS.get(label, "#64748b")
        return f"""
        <div style="background:#1e293b;border-radius:10px;padding:16px 20px;
                    min-width:140px;border-left:4px solid {color}">
          <div style="font-size:1.6rem;font-weight:700;color:#f1f5f9">{count}</div>
          <div style="font-size:0.8rem;color:#94a3b8;margin-top:4px">{label}</div>
        </div>"""

    cards = (
        card(str(total), "Features")
        + card(str(len(release_counts)), "Releases")
        + card(str(len(scope_counts)), "Scopes")
        + card(str(len(source_counts)), "Sources")
        + card(str(sum(test_type_counts.values())), "Test type refs")
    )

    type_cards = "".join(
        type_card(label, count)
        for label, count in sorted(type_counts.items(), key=lambda x: -x[1])
    )

    # ── charts ───────────────────────────────────────────────────────────────
    def chart_section(title: str, bars: str) -> str:
        return f"""
        <div style="background:#1e293b;border-radius:10px;padding:20px 24px;flex:1;min-width:260px">
          <h3 style="margin:0 0 14px;font-size:0.95rem;color:#94a3b8;
                     text-transform:uppercase;letter-spacing:.06em">{title}</h3>
          {bars}
        </div>"""

    charts = (
        chart_section("By type", _bar_chart(type_counts, TYPE_COLORS, total))
        + chart_section("By test type", _bar_chart(test_type_counts, TEST_TYPE_COLORS, sum(test_type_counts.values())))
        + chart_section("By scope", _bar_chart(scope_counts, SCOPE_COLORS, total))
        + chart_section("By release", _bar_chart(release_counts, {r: "#38bdf8" for r in release_counts}, total))
    )

    # ── feature rows ─────────────────────────────────────────────────────────
    rows = ""
    for f in features:
        test_badges = " ".join(_badge(t, TEST_TYPE_COLORS.get(t, "#64748b")) for t in f.get("primary_test_type", []))
        scope_color = SCOPE_COLORS.get(f.get("scope", ""), "#64748b")
        feat_type = f.get("type", "")
        type_color = TYPE_COLORS.get(feat_type, "#64748b")
        rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:0.82rem;color:#93c5fd;
                     white-space:nowrap">{f['id']}</td>
          <td>{_badge(f.get('source',''), '#475569')}</td>
          <td style="white-space:nowrap">{_badge(feat_type, type_color)}</td>
          <td>{_badge(f.get('scope',''), scope_color)}</td>
          <td style="color:#e2e8f0;font-size:0.88rem">{f.get('description','')}</td>
          <td style="white-space:nowrap">{_badge(f.get('release',''), '#0284c7')}</td>
          <td style="white-space:nowrap">{test_badges}</td>
          <td style="color:#94a3b8;font-size:0.82rem">{f.get('comment','')}</td>
        </tr>"""

    # ── full page ─────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Features Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a; color: #e2e8f0; padding: 32px 24px;
    }}
    h1 {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }}
    h2 {{ font-size: 1.05rem; font-weight: 600; color: #cbd5e1;
          text-transform: uppercase; letter-spacing: .06em; margin: 32px 0 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    th {{
      text-align: left; padding: 10px 12px;
      background: #1e293b; color: #94a3b8;
      font-size: 0.78rem; text-transform: uppercase; letter-spacing: .05em;
      border-bottom: 1px solid #334155;
    }}
    td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; vertical-align: top; }}
    tr:hover td {{ background: #1e293b55; }}
  </style>
</head>
<body>

  <h1>Features Report</h1>
  <p style="color:#64748b;font-size:0.85rem;margin-top:4px">
    Auto-generated from <code style="color:#94a3b8">features.yaml</code>
  </p>

  <h2>Summary</h2>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    {cards}
  </div>

  <h2>By Type</h2>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    {type_cards}
  </div>

  <h2>Distribution</h2>
  <div style="display:flex;flex-wrap:wrap;gap:16px">
    {charts}
  </div>

  <h2>Feature Details</h2>
  <div style="overflow-x:auto">
    <table>
      <thead>
        <tr>
          <th>ID</th><th>Source</th><th>Type</th><th>Scope</th><th>Description</th>
          <th>Release</th><th>Test types</th><th>Comment</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

</body>
</html>"""


def main() -> None:
    """Entrypoint"""
    parser = argparse.ArgumentParser(description="Render features.yaml to HTML.")
    parser.add_argument("--data", default=DEFAULT_DATA_FILE, help="Input YAML file")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Output HTML file")
    args = parser.parse_args()

    try:
        features = _load_features(args.data)
    except FileNotFoundError:
        print(f"ERROR: file not found: {args.data}", file=sys.stderr)
        sys.exit(2)

    html = _render(features)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
