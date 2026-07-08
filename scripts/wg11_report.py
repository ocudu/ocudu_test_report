#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Render wg11_tests.yaml into a self-contained HTML report."""

import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

DEFAULT_DATA_FILE = str(Path(__file__).parent.parent / "oran_wg11_test_plan" / "wg11_tests.yaml")
DEFAULT_OUTPUT_FILE = "wg11_report.html"

SCOPE_COLORS = {
    "CU/DU": "#38bdf8",
    "Entire RAN/platform/deployment/auxiliary component": "#a78bfa",
}

CATEGORY_PALETTE = [
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


def _load_tests(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: list[dict] = data["tests"]
    return result


def _category_colors(categories: list[str]) -> dict[str, str]:
    return {cat: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)] for i, cat in enumerate(sorted(categories))}


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


def _build_scope_cards(scope_counts: Counter) -> str:
    html = ""
    for label, count in sorted(scope_counts.items(), key=lambda x: -x[1]):
        color = SCOPE_COLORS.get(label, "#64748b")
        html += f"""
        <div style="background:#1e293b;border-radius:10px;padding:16px 20px;
                    min-width:140px;border-left:4px solid {color}">
          <div style="font-size:1.6rem;font-weight:700;color:#f1f5f9">{count}</div>
          <div style="font-size:0.8rem;color:#94a3b8;margin-top:4px">{label}</div>
        </div>"""
    return html


def _sort_key(test_id: str) -> list[tuple[int, int | str]]:
    return [(0, int(part)) if part.isdigit() else (1, part) for part in test_id.split(".")]


def _build_rows(tests: list[dict], category_colors: dict[str, str]) -> str:
    html = ""
    for t in sorted(tests, key=lambda t: _sort_key(t["test_id"])):
        scope = t.get("scope", "")
        scope_color = SCOPE_COLORS.get(scope, "#64748b")
        category = t.get("category", "")
        category_color = category_colors.get(category, "#64748b")
        comment = t.get("comment") or ""
        comment_html = comment if comment else '<span style="color:#475569;font-size:0.8rem">—</span>'
        html += f"""
        <tr>
          <td style="font-family:monospace;font-size:0.85rem;color:#93c5fd;
                     white-space:nowrap;font-weight:600">{t['test_id']}</td>
          <td style="color:#e2e8f0;font-size:0.88rem">{t.get('description', '')}</td>
          <td>{_badge(category, category_color, small=True)}</td>
          <td style="white-space:nowrap">{_badge(scope, scope_color)}</td>
          <td style="color:#cbd5e1;font-size:0.85rem">{comment_html}</td>
        </tr>"""
    return html


def _render(tests: list[dict]) -> str:
    total = len(tests)
    scope_counts = Counter(t["scope"] for t in tests)
    category_counts = Counter(t["category"] for t in tests)
    category_colors = _category_colors(list(category_counts))

    cards = (
        _summary_card(str(total), "Test Cases")
        + _summary_card(str(len(category_counts)), "Categories")
        + _summary_card(str(len(scope_counts)), "Scopes")
    )
    scope_cards = _build_scope_cards(scope_counts)
    scope_chart_bars = _bar_chart(scope_counts, total, SCOPE_COLORS)
    category_chart_bars = _bar_chart(category_counts, total, category_colors)
    scope_chart = f"""
    <div style="background:#1e293b;border-radius:10px;padding:20px 24px;max-width:700px">
      <h3 style="margin:0 0 14px;font-size:0.95rem;color:#94a3b8;
                 text-transform:uppercase;letter-spacing:.06em">By scope</h3>
      {scope_chart_bars}
    </div>"""
    category_chart = f"""
    <div style="background:#1e293b;border-radius:10px;padding:20px 24px;max-width:700px">
      <h3 style="margin:0 0 14px;font-size:0.95rem;color:#94a3b8;
                 text-transform:uppercase;letter-spacing:.06em">By category</h3>
      {category_chart_bars}
    </div>"""
    rows = _build_rows(tests, category_colors)

    # ── full page ─────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>O-RAN WG11 Security Test Plan Report</title>
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

  <h1>O-RAN WG11 Security Test Plan Report</h1>
  <p style="color:#64748b;font-size:0.85rem;margin-top:4px">
    Auto-generated from
    <code style="color:#94a3b8">wg11_tests.yaml</code> &mdash;
    O-RAN.WG11.Security-Test-Specifications.0-R004-v08.00, O-CU/O-DU related test cases only.
  </p>

  <h2>Summary</h2>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    {cards}
  </div>

  <h2>By Scope</h2>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    {scope_cards}
  </div>

  <h2>Distribution</h2>
  <div style="display:flex;flex-wrap:wrap;gap:20px">
    {scope_chart}
    {category_chart}
  </div>

  <h2>Test Cases</h2>
  <div style="margin-bottom:14px">
    <input id="search" type="search" placeholder="Filter by test ID, description, category, scope or comment&hellip;">
  </div>
  <div style="overflow-x:auto">
    <table id="wg11-table">
      <thead>
        <tr>
          <th>Test ID</th>
          <th>Description</th>
          <th>Category</th>
          <th>Scope</th>
          <th>Comment</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p id="no-results" style="display:none;color:#64748b;margin-top:12px">No matching test cases.</p>

  <script>
    const input = document.getElementById('search');
    const tbody = document.querySelector('#wg11-table tbody');
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
    parser = argparse.ArgumentParser(description="Render wg11_tests.yaml to an HTML report.")
    parser.add_argument("--data", default=DEFAULT_DATA_FILE, help=f"Input YAML file (default: {DEFAULT_DATA_FILE})")
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT_FILE, help=f"Output HTML file (default: {DEFAULT_OUTPUT_FILE})"
    )
    args = parser.parse_args()

    try:
        tests = _load_tests(args.data)
    except FileNotFoundError:
        print(f"ERROR: file not found: {args.data}", file=sys.stderr)
        sys.exit(2)
    except KeyError:
        print(f"ERROR: expected top-level 'tests' key in {args.data}", file=sys.stderr)
        sys.exit(2)

    html = _render(tests)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"Report written to {args.output}  ({len(tests)} test cases)")


if __name__ == "__main__":
    main()
