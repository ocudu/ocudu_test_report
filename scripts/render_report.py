#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Render features.yaml into a self-contained HTML report."""

import argparse
import json
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
    "Functional": "#34d399",
    "Performance": "#f59e0b",
    "Security": "#f87171",
    "O-Cloud": "#38bdf8",
    "Management": "#a78bfa",
}

_MS_ACTIONS = (
    '<div class="ms-actions">'
    '<button type="button" class="ms-action-btn" data-action="all">All</button>'
    '<button type="button" class="ms-action-btn" data-action="none">None</button>'
    "</div>"
)

# Plain string — {} inside are JS syntax, not f-string expressions.
_FILTER_JS = r"""
(function () {
  function renderBarChart(containerId, counts, colors, defaultColor, total) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var entries = Object.keys(counts).map(function(k) { return [k, counts[k]]; });
    entries.sort(function(a, b) { return b[1] - a[1]; });
    if (entries.length === 0 || total === 0) { container.innerHTML = ''; return; }
    var g = 'display:grid;grid-template-columns:minmax(min-content,40%) 1fr auto;align-items:center;gap:6px 10px';
    var html = '<div style="' + g + '">';
    entries.forEach(function(e) {
      var label = e[0], count = e[1];
      var pct = (count / total * 100).toFixed(1);
      var color = (colors && colors[label]) || defaultColor || '#64748b';
      html += '<div style="font-size:0.85rem;color:#cbd5e1;word-break:break-word">' + label.replace(/\//g, ' / ') + '</div>';
      html += '<div style="background:#0f172a;border-radius:4px;height:18px;overflow:hidden">'
            + '<div style="width:' + pct + '%;background:' + color + ';height:100%;border-radius:4px"></div></div>';
      html += '<div style="font-size:0.85rem;color:#94a3b8;white-space:nowrap">' + count + '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function recount() {
    var sources = {}, types = {}, scopes = {}, releases = {}, testTypes = {};
    var total = 0;
    document.querySelectorAll('#feat-table tbody .feat-row').forEach(function(row) {
      if (row.classList.contains('hidden-row')) return;
      total++;
      var src = row.dataset.source;    if (src) sources[src]  = (sources[src]  || 0) + 1;
      var typ = row.dataset.type;      if (typ) types[typ]    = (types[typ]    || 0) + 1;
      var sc  = row.dataset.scope;     if (sc)  scopes[sc]    = (scopes[sc]    || 0) + 1;
      var rel = row.dataset.release;   if (rel) releases[rel] = (releases[rel] || 0) + 1;
      var tts = row.dataset.testtypes;
      if (tts) tts.split(',').forEach(function(t) { if (t) testTypes[t] = (testTypes[t] || 0) + 1; });
    });

    var el;
    el = document.getElementById('sum-features');  if (el) el.textContent = total;
    el = document.getElementById('sum-releases');  if (el) el.textContent = Object.keys(releases).length;
    el = document.getElementById('sum-scopes');    if (el) el.textContent = Object.keys(scopes).length;
    el = document.getElementById('sum-sources');   if (el) el.textContent = Object.keys(sources).length;
    var ttTotal = Object.keys(testTypes).reduce(function(s, k) { return s + testTypes[k]; }, 0);
    el = document.getElementById('sum-testtypes'); if (el) el.textContent = ttTotal;

    var TC = window.FR_TYPE_COLORS, SC = window.FR_SCOPE_COLORS, TTC = window.FR_TEST_TYPE_COLORS;
    renderBarChart('chart-type',     types,     TC,   '#64748b', total);
    renderBarChart('chart-scope',    scopes,    SC,   '#64748b', total);
    renderBarChart('chart-release',  releases,  null, '#38bdf8', total);
    renderBarChart('chart-testtype', testTypes, TTC,  '#64748b', ttTotal);
  }

  function msGetSelected(wrapId) {
    var boxes = Array.from(document.querySelectorAll('#' + wrapId + ' .ms-panel input'));
    var checked = boxes.filter(function(b) { return b.checked; }).map(function(b) { return b.value; });
    if (checked.length === boxes.length) return null;
    var s = {};
    checked.forEach(function(v) { s[v] = true; });
    return s;
  }

  function msUpdateLabel(wrapId) {
    var boxes = Array.from(document.querySelectorAll('#' + wrapId + ' .ms-panel input'));
    var checked = boxes.filter(function(b) { return b.checked; });
    var label = document.querySelector('#' + wrapId + ' .ms-label');
    if (!label) return;
    if (checked.length === 0 || checked.length === boxes.length) { label.textContent = 'All'; }
    else if (checked.length === 1) { label.textContent = checked[0].value; }
    else { label.textContent = checked.length + ' selected'; }
  }

  function applyFilters() {
    var sf  = msGetSelected('ms-source');
    var tf  = msGetSelected('ms-type');
    var rf  = msGetSelected('ms-release');
    var scf = msGetSelected('ms-scope');
    document.querySelectorAll('#feat-table tbody .feat-row').forEach(function(row) {
      var ok = (!sf  || sf[row.dataset.source])
             && (!tf  || tf[row.dataset.type])
             && (!rf  || rf[row.dataset.release])
             && (!scf || scf[row.dataset.scope]);
      row.classList.toggle('hidden-row', !ok);
    });
    recount();
  }

  document.addEventListener('DOMContentLoaded', function () {
    ['ms-source', 'ms-type', 'ms-release', 'ms-scope'].forEach(function(id) {
      var wrap = document.getElementById(id);
      if (!wrap) return;
      var btn   = wrap.querySelector('.ms-btn');
      var panel = wrap.querySelector('.ms-panel');

      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var isOpen = !panel.hidden;
        document.querySelectorAll('.ms-panel').forEach(function(p) { p.hidden = true; });
        document.querySelectorAll('.ms-wrap').forEach(function(w) { w.classList.remove('open'); });
        if (!isOpen) { panel.hidden = false; wrap.classList.add('open'); }
      });

      panel.addEventListener('click', function(e) { e.stopPropagation(); });

      wrap.querySelectorAll('.ms-action-btn').forEach(function(ab) {
        ab.addEventListener('click', function() {
          var all = ab.dataset.action === 'all';
          wrap.querySelectorAll('input[type=checkbox]').forEach(function(cb) { cb.checked = all; });
          msUpdateLabel(id);
          applyFilters();
        });
      });

      wrap.querySelectorAll('input[type=checkbox]').forEach(function(cb) {
        cb.addEventListener('change', function() { msUpdateLabel(id); applyFilters(); });
      });
    });

    document.addEventListener('click', function() {
      document.querySelectorAll('.ms-panel').forEach(function(p) { p.hidden = true; });
      document.querySelectorAll('.ms-wrap').forEach(function(w) { w.classList.remove('open'); });
    });

    applyFilters();
  });
})();
"""


def _load_features(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["features"]  # type: ignore


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:12px;font-size:0.78rem;font-weight:600;white-space:nowrap">{text}</span>'
    )


def _ms_dropdown(wrap_id: str, label: str, values: list[str]) -> str:
    items = "".join(
        f'<label class="ms-item"><input type="checkbox" value="{v}" checked>' f"<span>{v}</span></label>"
        for v in values
    )
    return (
        f'<div class="ms-wrap" id="{wrap_id}">'
        f'<button type="button" class="ms-btn">{label}: <span class="ms-label">All</span></button>'
        f'<div class="ms-panel" hidden>{_MS_ACTIONS}{items}</div>'
        f"</div>"
    )


# pylint: disable=too-many-locals
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

    all_sources = sorted(source_counts.keys())
    all_types = sorted(type_counts.keys())
    all_releases = sorted(release_counts.keys())
    all_scopes = sorted(scope_counts.keys())

    # ── summary cards ────────────────────────────────────────────────────────
    def card(value_id: str, value: str, label: str) -> str:
        return f"""
        <div style="background:#1e293b;border-radius:10px;padding:20px 28px;
                    text-align:center;min-width:120px">
          <div id="{value_id}" style="font-size:2rem;font-weight:700;color:#f1f5f9">{value}</div>
          <div style="font-size:0.8rem;color:#94a3b8;margin-top:4px">{label}</div>
        </div>"""

    cards = (
        card("sum-features", str(total), "Features")
        + card("sum-releases", str(len(release_counts)), "Releases")
        + card("sum-scopes", str(len(scope_counts)), "Scopes")
        + card("sum-sources", str(len(source_counts)), "Sources")
        + card("sum-testtypes", str(sum(test_type_counts.values())), "Test type refs")
    )

    # ── distribution charts (containers filled by JS) ─────────────────────────
    def chart_section(title: str, chart_id: str) -> str:
        return f"""
        <div style="background:#1e293b;border-radius:10px;padding:20px 24px;flex:1;min-width:260px">
          <h3 style="margin:0 0 14px;font-size:0.95rem;color:#94a3b8;
                     text-transform:uppercase;letter-spacing:.06em">{title}</h3>
          <div id="{chart_id}"></div>
        </div>"""

    charts = (
        chart_section("By type", "chart-type")
        + chart_section("By test type", "chart-testtype")
        + chart_section("By scope", "chart-scope")
        + chart_section("By release", "chart-release")
    )

    # ── feature rows ─────────────────────────────────────────────────────────
    rows = ""
    for f in features:
        test_types = f.get("primary_test_type", [])
        test_badges = " ".join(_badge(t, TEST_TYPE_COLORS.get(t, "#64748b")) for t in test_types)
        feat_type = f.get("type", "")
        type_color = TYPE_COLORS.get(feat_type, "#64748b")
        source = f.get("source", "")
        release = f.get("release", "")
        scope = f.get("scope", "")
        testtypes_attr = ",".join(test_types)
        rows += (
            f'\n        <tr class="feat-row"'
            f' data-source="{source}"'
            f' data-type="{feat_type}"'
            f' data-release="{release}"'
            f' data-scope="{scope}"'
            f' data-testtypes="{testtypes_attr}">'
            f'<td style="font-family:monospace;font-size:0.82rem;color:#93c5fd;white-space:nowrap">{f["id"]}</td>'
            f'<td style="white-space:nowrap">{_badge(source, "#475569")}</td>'
            f'<td style="white-space:nowrap">{_badge(feat_type, type_color)}</td>'
            f'<td style="width:160px;font-size:0.82rem;color:#94a3b8">{scope.replace("/", " / ")}</td>'
            f'<td style="width:100%;color:#e2e8f0;font-size:0.88rem">{f.get("description","")}</td>'
            f'<td style="white-space:nowrap">{_badge(release, "#0284c7")}</td>'
            f'<td style="white-space:nowrap">{test_badges}</td>'
            f'<td style="color:#94a3b8;font-size:0.82rem">{f.get("comment","")}</td>'
            f"</tr>"
        )

    # ── filter controls ───────────────────────────────────────────────────────
    controls = (
        '<div class="fr-controls">'
        + _ms_dropdown("ms-source", "Source", all_sources)
        + _ms_dropdown("ms-type", "Type", all_types)
        + _ms_dropdown("ms-release", "Release", all_releases)
        + _ms_dropdown("ms-scope", "Scope", all_scopes)
        + "</div>"
    )

    # ── color maps for JS bar chart renderer ──────────────────────────────────
    color_script = (
        f"<script>window.FR_TYPE_COLORS={json.dumps(TYPE_COLORS)};"
        f"window.FR_TEST_TYPE_COLORS={json.dumps(TEST_TYPE_COLORS)};"
        f"window.FR_SCOPE_COLORS={json.dumps(SCOPE_COLORS)};</script>"
    )

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
    tbody tr:nth-child(odd)  td {{ background: #1e293b; }}
    tbody tr:nth-child(even) td {{ background: #263448; }}
    tr:hover td {{ background: #2d3f58 !important; }}
    tr.hidden-row {{ display: none; }}

    .fr-controls {{
      display: flex; gap: 12px; align-items: center; margin-bottom: 10px; flex-wrap: wrap;
    }}
    .ms-wrap {{ position: relative; display: inline-block; }}
    .ms-btn {{
      background: #1e293b; color: #94a3b8; border: 1px solid #334155;
      border-radius: 4px; padding: 4px 10px; font-size: 0.83em;
      font-family: inherit; font-weight: 500; cursor: pointer; outline: none;
      display: flex; align-items: center; gap: 4px; white-space: nowrap;
      transition: border-color 0.1s;
    }}
    .ms-btn::after {{ content: '▾'; font-size: 0.8em; margin-left: 2px; transition: transform 0.15s; }}
    .ms-btn:hover {{ border-color: #38bdf8; }}
    .ms-wrap.open .ms-btn {{ border-color: #38bdf8; }}
    .ms-wrap.open .ms-btn::after {{ transform: rotate(180deg); }}
    .ms-label {{ color: #38bdf8; font-weight: 500; }}
    .ms-panel {{
      position: absolute; top: calc(100% + 4px); left: 0; z-index: 100;
      background: #1e293b; border: 1px solid #334155; border-radius: 6px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.5); min-width: 160px; padding: 4px 0;
    }}
    .ms-item {{
      display: flex; align-items: center; gap: 8px; padding: 6px 12px;
      cursor: pointer; font-size: 0.85em; color: #cbd5e1;
      transition: background 0.08s; user-select: none;
    }}
    .ms-item:hover {{ background: #263448; }}
    .ms-item input[type=checkbox] {{
      accent-color: #38bdf8; width: 14px; height: 14px; cursor: pointer; flex-shrink: 0;
    }}
    .ms-actions {{
      display: flex; gap: 6px; padding: 6px 12px; border-bottom: 1px solid #1e293b;
    }}
    .ms-action-btn {{
      background: none; border: 1px solid #334155; border-radius: 4px;
      color: #94a3b8; font-size: 0.75em; font-family: inherit;
      padding: 2px 8px; cursor: pointer; transition: color 0.1s, border-color 0.1s;
    }}
    .ms-action-btn:hover {{ color: #38bdf8; border-color: #38bdf8; }}
  </style>
</head>
<body>

  <h1>OCUDU Feature Overview</h1>
  <p style="color:#64748b;font-size:0.85rem;margin-top:4px">
    Auto-generated from <code style="color:#94a3b8">features.yaml</code>
  </p>

  <h2>Summary</h2>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    {cards}
  </div>

  <h2>Distribution</h2>
  <div style="display:flex;flex-wrap:wrap;gap:16px">
    {charts}
  </div>

  <h2>Feature Details</h2>
  {controls}
  <div style="overflow-x:auto">
    <table id="feat-table">
      <thead>
        <tr>
          <th>ID</th><th>Source</th><th>Type</th><th>Scope</th><th>Description</th>
          <th>Release</th><th>Test types</th><th>Comment</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

{color_script}
<script>{_FILTER_JS}</script>
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
