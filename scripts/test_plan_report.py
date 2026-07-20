#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Render a test plan YAML (wg11.yaml, tifg.yaml, ...) into a self-contained HTML report.

Columns and summary cards adapt to whichever optional fields (category_description,
comment, ocudu_features) are actually present in the given data file.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Union

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

CATEGORY_COLORS = {
    "Functional": "#34d399",
    "Performance": "#f59e0b",
    "Service": "#38bdf8",
    "Load and Stress": "#f87171",
    "RIC-enabled": "#a78bfa",
    "Security": "#fb7185",
}

SCOPE_COLORS = {
    "CU/DU": "#38bdf8",
    "Entire RAN/platform/deployment/auxiliary component": "#a78bfa",
}

SUBCATEGORY_PALETTE = [
    "#34d399",
    "#f59e0b",
    "#f87171",
    "#818cf8",
    "#fb923c",
    "#4ade80",
    "#e879f9",
    "#facc15",
    "#22d3ee",
    "#fb7185",
    "#a3e635",
    "#c084fc",
    "#2dd4bf",
    "#f472b6",
    "#60a5fa",
    "#eab308",
    "#84cc16",
    "#f43f5e",
    "#0ea5e9",
    "#d946ef",
    "#10b981",
    "#f97316",
    "#6366f1",
    "#14b8a6",
    "#ec4899",
]

# Per-plan display metadata, keyed by the data file's stem. Unknown stems fall back to
# a generic title and no subtitle — new test plans work out of the box.
TITLES = {
    "wg11": "O-RAN WG11 Security Test Plan Report",
    "tifg": "TIFG Test Plan Report",
}

SOURCE_INFO = {
    "wg11": "O-RAN.WG11.Security-Test-Specifications.0-R004-v08.00, O-CU/O-DU related test cases only.",
    "tifg": "O-RAN.TIFG.TS.E2E-Test.0-R005-v09.00, 5G Standalone applicable test cases",
}


def _load_tests(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: list[dict] = data["tests"]
    return result


def _subcategory_colors(subcategories: list[str]) -> dict[str, str]:
    return {cat: SUBCATEGORY_PALETTE[i % len(SUBCATEGORY_PALETTE)] for i, cat in enumerate(sorted(subcategories))}


def _badge(text: str, color: str, small: bool = False) -> str:
    size = "0.72rem" if small else "0.78rem"
    return (
        f'<span style="background:{color};color:#fff;padding:2px 7px;'
        f"border-radius:12px;font-size:{size};font-weight:600;"
        f'white-space:nowrap;display:inline-block;margin:1px 2px">{text}</span>'
    )


def _bar_chart(counts: dict[str, int], total: int, colors: dict[str, str]) -> str:
    if total == 0:
        return ""
    rows = ""
    for label, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        color = colors.get(label, "#64748b")
        rows += f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <div style="width:340px;font-size:0.85rem;color:#cbd5e1;text-align:right">{label}</div>
          <div style="flex:1;background:#1e293b;border-radius:4px;height:18px;overflow:hidden">
            <div style="width:{pct:.1f}%;background:{color};height:100%;border-radius:4px"></div>
          </div>
          <div style="width:30px;font-size:0.85rem;color:#94a3b8">{count}</div>
        </div>"""
    return rows


def _summary_card(value: str, label: str) -> str:
    return f"""
        <div style="background:#1e293b;border-radius:10px;padding:20px 28px;
                    text-align:center;min-width:120px">
          <div style="font-size:2rem;font-weight:700;color:#f1f5f9">{value}</div>
          <div style="font-size:0.8rem;color:#94a3b8;margin-top:4px">{label}</div>
        </div>"""


def _build_count_cards(counts: Counter, colors: dict[str, str]) -> str:
    html = ""
    for label, count in sorted(counts.items(), key=lambda x: -x[1]):
        color = colors.get(label, "#64748b")
        html += f"""
        <div style="background:#1e293b;border-radius:10px;padding:16px 20px;
                    min-width:140px;border-left:4px solid {color}">
          <div style="font-size:1.6rem;font-weight:700;color:#f1f5f9">{count}</div>
          <div style="font-size:0.8rem;color:#94a3b8;margin-top:4px">{label}</div>
        </div>"""
    return html


def _sort_key(test_id: str) -> list[tuple[int, Union[int, str]]]:
    return [(0, int(part)) if part.isdigit() else (1, part) for part in test_id.split(".")]


# pylint: disable=too-many-locals
def _build_rows(
    tests: list[dict],
    subcategory_colors: dict[str, str],
    show_subcategory: bool,
    show_comment: bool,
    show_features: bool,
) -> str:
    html = ""
    for t in sorted(tests, key=lambda t: _sort_key(t["test_id"])):
        category = t.get("category", "")
        category_color = CATEGORY_COLORS.get(category, "#64748b")
        scope = t.get("scope", "")
        scope_color = SCOPE_COLORS.get(scope, "#64748b")

        cells = [
            f'<td style="font-family:monospace;font-size:0.85rem;color:#93c5fd;'
            f'white-space:nowrap;font-weight:600">{t["test_id"]}</td>',
            f'<td style="color:#e2e8f0;font-size:0.88rem">{t.get("description", "")}</td>',
            f"<td>{_badge(category, category_color, small=True)}</td>",
            f'<td style="white-space:nowrap">{_badge(scope, scope_color)}</td>',
        ]
        if show_subcategory:
            subcategory = t.get("category_description") or ""
            subcategory_color = subcategory_colors.get(subcategory, "#64748b")
            subcategory_html = (
                _badge(subcategory, subcategory_color, small=True)
                if subcategory
                else '<span style="color:#475569;font-size:0.8rem">—</span>'
            )
            cells.append(f"<td>{subcategory_html}</td>")
        if show_comment:
            comment = t.get("comment") or ""
            comment_html = comment if comment else '<span style="color:#475569;font-size:0.8rem">—</span>'
            cells.append(f'<td style="color:#cbd5e1;font-size:0.85rem">{comment_html}</td>')
        if show_features:
            features = t.get("ocudu_features") or []
            feature_chips = "".join(_badge(fid, "#1e40af", small=True) for fid in features)
            if not feature_chips:
                feature_chips = '<span style="color:#475569;font-size:0.8rem">—</span>'
            cells.append(f'<td style="line-height:1.8">{feature_chips}</td>')

        html += f"\n        <tr>{''.join(cells)}</tr>"
    return html


# pylint: disable=too-many-locals
def _render(tests: list[dict], title: str, subtitle: str, source_name: str) -> str:
    total = len(tests)
    category_counts = Counter(t["category"] for t in tests)
    scope_counts = Counter(t["scope"] for t in tests)
    show_subcategory = any(t.get("category_description") for t in tests)
    show_comment = any(t.get("comment") for t in tests)
    show_features = any(t.get("ocudu_features") for t in tests)

    cards = [
        _summary_card(str(total), "Test Cases"),
        _summary_card(str(len(category_counts)), "Categories"),
        _summary_card(str(len(scope_counts)), "Scopes"),
    ]

    subcategory_counts: Counter = Counter()
    subcategory_colors: dict[str, str] = {}
    if show_subcategory:
        subcategory_counts = Counter(t.get("category_description") or t["category"] for t in tests)
        subcategory_colors = _subcategory_colors(list(subcategory_counts))
        cards.append(_summary_card(str(len(subcategory_counts)), "Subcategories"))

    if show_features:
        with_features = sum(1 for t in tests if t.get("ocudu_features"))
        total_feature_refs = sum(len(t.get("ocudu_features") or []) for t in tests)
        cards.append(_summary_card(str(with_features), "With features"))
        cards.append(_summary_card(str(total - with_features), "Without features"))
        cards.append(_summary_card(str(total_feature_refs), "Feature refs"))

    scope_cards = _build_count_cards(scope_counts, SCOPE_COLORS)

    charts = [
        ("By category", _bar_chart(category_counts, total, CATEGORY_COLORS)),
        ("By scope", _bar_chart(scope_counts, total, SCOPE_COLORS)),
    ]
    if show_subcategory:
        charts.append(("By subcategory", _bar_chart(subcategory_counts, total, subcategory_colors)))

    chart_html = "".join(f"""
    <div style="background:#1e293b;border-radius:10px;padding:20px 24px;max-width:700px">
      <h3 style="margin:0 0 14px;font-size:0.95rem;color:#94a3b8;
                 text-transform:uppercase;letter-spacing:.06em">{label}</h3>
      {bars}
    </div>""" for label, bars in charts)

    headers = ["Test ID", "Description", "Category", "Scope"]
    if show_subcategory:
        headers.append("Subcategory")
    if show_comment:
        headers.append("Comment")
    if show_features:
        headers.append("OCUDU Features")
    header_html = "".join(f"<th>{h}</th>" for h in headers)

    rows = _build_rows(tests, subcategory_colors, show_subcategory, show_comment, show_features)

    search_fields = ["test ID", "description", "category", "scope"]
    if show_subcategory:
        search_fields.append("subcategory")
    if show_comment:
        search_fields.append("comment")
    if show_features:
        search_fields.append("feature ID")
    placeholder = "Filter by " + ", ".join(search_fields[:-1]) + f" or {search_fields[-1]}…"

    subtitle_html = f" &mdash;\n    {subtitle}" if subtitle else ""

    # ── full page ─────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
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
      border-bottom: 1px solid #334155; position: sticky; top: 0;
    }}
    td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; vertical-align: top; }}
    tr:hover td {{ background: #1e293b55; }}
    #search {{
      background: #1e293b; border: 1px solid #334155; border-radius: 8px;
      color: #e2e8f0; font-size: 0.9rem; padding: 8px 14px; width: 320px;
      outline: none;
    }}
    #search:focus {{ border-color: #38bdf8; }}
  </style>
</head>
<body>

  <h1>{title}</h1>
  <p style="color:#64748b;font-size:0.85rem;margin-top:4px">
    Auto-generated from
    <code style="color:#94a3b8">{source_name}</code>{subtitle_html}
  </p>

  <h2>Summary</h2>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    {''.join(cards)}
  </div>

  <h2>By Scope</h2>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    {scope_cards}
  </div>

  <h2>Distribution</h2>
  <div style="display:flex;flex-wrap:wrap;gap:20px">
    {chart_html}
  </div>

  <h2>Test Cases</h2>
  <div style="margin-bottom:14px">
    <input id="search" type="search" placeholder="{placeholder}">
  </div>
  <div style="overflow-x:auto">
    <table id="test-plan-table">
      <thead>
        <tr>{header_html}</tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p id="no-results" style="display:none;color:#64748b;margin-top:12px">No matching test cases.</p>

  <script>
    const input = document.getElementById('search');
    const tbody = document.querySelector('#test-plan-table tbody');
    const noResults = document.getElementById('no-results');
    input.addEventListener('input', () => {{
      const q = input.value.toLowerCase();
      let visible = 0;
      for (const row of tbody.rows) {{
        const match = !q || row.textContent.toLowerCase().includes(q);
        row.style.display = match ? '' : 'none';
        if (match) visible++;
      }};
      noResults.style.display = visible === 0 ? '' : 'none';
    }});
  </script>

</body>
</html>"""


def main() -> None:
    """Entrypoint"""
    parser = argparse.ArgumentParser(description="Render a test plan YAML to an HTML report.")
    parser.add_argument("--data", required=True, help="Input test plan YAML file (e.g. testplans/wg11.yaml)")
    parser.add_argument("--output", default=None, help="Output HTML file (default: <stem>_report.html)")
    parser.add_argument("--title", default=None, help="Report title (default: derived from the data file name)")
    args = parser.parse_args()

    stem = Path(args.data).stem
    output = args.output or f"{stem}_report.html"
    title = args.title or TITLES.get(stem, f"{stem.upper()} Test Plan Report")
    subtitle = SOURCE_INFO.get(stem, "")

    try:
        tests = _load_tests(args.data)
    except FileNotFoundError:
        print(f"ERROR: file not found: {args.data}", file=sys.stderr)
        sys.exit(2)
    except KeyError:
        print(f"ERROR: expected top-level 'tests' key in {args.data}", file=sys.stderr)
        sys.exit(2)

    html = _render(tests, title, subtitle, Path(args.data).name)
    Path(output).write_text(html, encoding="utf-8")
    print(f"Report written to {output}  ({len(tests)} test cases)")


if __name__ == "__main__":
    main()
