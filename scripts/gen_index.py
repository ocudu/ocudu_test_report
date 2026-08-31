#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Generate index.html for the test report.

Usage:
    python3 gen_index.py [-o index.html] [--historic 26.04 26.03 ...]

With no --historic arguments, produces a page with only the "Latest" version tab.
Each --historic value adds a version pill and links to historic_<version>/ sub-reports.
"""

import argparse
import json
import sys
from pathlib import Path


def _safe(version: str) -> str:
    return version.replace(" ", "_")


def _generate(historic: list[str]) -> str:
    versions = ["latest"] + [v.strip() for v in historic if v.strip()]

    version_pages: dict[str, dict[str, str]] = {}
    for v in versions:
        if v == "latest":
            version_pages[v] = {"report": "report.html", "all": "all.html"}
        else:
            d = _safe(v)
            version_pages[v] = {
                "report": f"historic_{d}/report.html",
                "all": f"historic_{d}/all.html",
            }

    nav_version_tabs = "\n".join(
        f'      <a class="tab" data-version="{v}" href="#">{"Latest" if v == "latest" else v}</a>' for v in versions
    )
    third_party_tab_html = '      <a class="tab" data-fixed="third_party" href="#">Third Party</a>'

    versions_js = json.dumps(versions)
    version_pages_js = json.dumps(version_pages)

    return f"""\
<!--
SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
SPDX-License-Identifier: BSD-3-Clause-Open-MPI
-->

<!DOCTYPE html>
<html lang="en">

<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Test Reports</title>
  <style>
    *,
    *::before,
    *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    html,
    body {{
      height: 100%;
      overflow: hidden;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      display: flex;
      flex-direction: column;
    }}

    nav {{
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 10px 16px;
      background: #1e293b;
      border-bottom: 1px solid #334155;
      flex-shrink: 0;
    }}

    .nav-left {{
      display: flex;
      gap: 6px;
      flex: 1;
      flex-wrap: wrap;
    }}

    .nav-right {{
      display: flex;
      gap: 6px;
      flex-shrink: 0;
    }}

    .subnav {{
      display: flex;
      gap: 6px;
      padding: 6px 16px;
      background: #0f172a;
      border-bottom: 1px solid #1e293b;
      flex-shrink: 0;
    }}

    .subnav.hidden {{
      display: none;
    }}

    .tab {{
      padding: 7px 22px;
      border-radius: 20px;
      font-size: .85em;
      font-weight: 600;
      text-decoration: none;
      color: #94a3b8;
      background: #0f172a;
      border: 1px solid #334155;
      transition: color .12s, border-color .12s, background .12s;
      cursor: pointer;
    }}

    .tab:hover {{
      color: #e2e8f0;
      border-color: #94a3b8;
    }}

    .tab.active {{
      color: #38bdf8;
      border-color: #38bdf8;
      background: rgba(56, 189, 248, .08);
    }}

    .subtab {{
      padding: 4px 16px;
      border-radius: 20px;
      font-size: .80em;
      font-weight: 600;
      text-decoration: none;
      color: #94a3b8;
      background: transparent;
      border: 1px solid #334155;
      transition: color .12s, border-color .12s, background .12s;
      cursor: pointer;
    }}

    .subtab:hover {{
      color: #e2e8f0;
      border-color: #94a3b8;
    }}

    .subtab.active {{
      color: #38bdf8;
      border-color: #38bdf8;
      background: rgba(56, 189, 248, .08);
    }}

    iframe {{
      flex: 1;
      width: 100%;
      border: none;
      display: block;
    }}

    .run-selector {{
      position: relative;
    }}

    .run-selector .tab {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}

    .run-selector .tab::after {{
      content: '\\25BE';
      font-size: 0.7em;
    }}

    .run-panel {{
      display: none;
      position: absolute;
      top: calc(100% + 8px);
      right: 0;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px 0;
      min-width: 320px;
      max-height: 400px;
      overflow-y: auto;
      z-index: 100;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }}

    .run-panel.open {{
      display: block;
    }}

    .run-panel-title {{
      padding: 6px 14px;
      font-size: .75em;
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .run-item {{
      display: block;
      padding: 8px 14px;
      text-decoration: none;
      color: #e2e8f0;
      font-size: .82em;
      border-bottom: 1px solid #1e293b;
      transition: background .1s;
    }}

    .run-item:hover {{
      background: #334155;
    }}

    .run-item-date {{
      font-weight: 600;
    }}

    .run-item-stats {{
      color: #94a3b8;
      font-size: .9em;
      margin-top: 2px;
    }}

    .run-item-stats .pass {{ color: #4ade80; }}
    .run-item-stats .fail {{ color: #f87171; }}

    .run-panel-empty {{
      padding: 12px 14px;
      color: #64748b;
      font-size: .82em;
    }}
  </style>
</head>

<body>
  <nav>
    <div class="nav-left">
{nav_version_tabs}
{third_party_tab_html}
    </div>
    <div class="nav-right">
      <div class="run-selector">
        <a class="tab" id="run-selector-btn" href="#">Run History</a>
        <div class="run-panel" id="run-panel">
          <div class="run-panel-title">Archived Runs</div>
          <div id="run-list"><div class="run-panel-empty">Loading...</div></div>
        </div>
      </div>
      <a class="tab" data-fixed="features" href="#">Features</a>
      <a class="tab" data-fixed="tifg" href="#">TIFG Test Plan</a>
      <a class="tab" data-fixed="wg11" href="#">WG11 Test Plan</a>
      <a class="tab" data-fixed="comparison" href="#">Comparison</a>
    </div>
  </nav>
  <div class="subnav hidden" id="subnav">
    <a class="subtab" data-sub="report" href="#">Test Report</a>
    <a class="subtab" data-sub="all" href="#">All Tests</a>
  </div>
  <iframe id="frame"></iframe>
  <script>
    (function () {{
      var VERSIONS = {versions_js};
      var VERSION_PAGES = {version_pages_js};
      var FIXED_PAGES = {{
        features: 'feature_list.html',
        tifg: 'tifg_report.html',
        wg11: 'wg11_report.html',
        third_party: 'third_party.html',
        comparison: 'comparison.html'
      }};

      var frame   = document.getElementById('frame');
      var subnav  = document.getElementById('subnav');
      var vTabs   = document.querySelectorAll('[data-version]');
      var fTabs   = document.querySelectorAll('[data-fixed]');
      var sTabs   = document.querySelectorAll('[data-sub]');

      function parseHash(hash) {{
        var h = (hash || '').replace(/^#/, '');
        if (!h) return {{ type: 'version', version: 'latest', sub: 'report' }};
        if (FIXED_PAGES[h]) return {{ type: 'fixed', key: h }};
        var parts   = h.split('/');
        var version = parts[0];
        var sub     = parts[1] === 'all' ? 'all' : 'report';
        if (VERSION_PAGES[version]) return {{ type: 'version', version: version, sub: sub }};
        return {{ type: 'version', version: 'latest', sub: 'report' }};
      }}

      function activate(state) {{
        if (state.type === 'fixed') {{
          subnav.classList.add('hidden');
          vTabs.forEach(function (t) {{ t.classList.remove('active'); }});
          fTabs.forEach(function (t) {{ t.classList.toggle('active', t.dataset.fixed === state.key); }});
          sTabs.forEach(function (t) {{ t.classList.remove('active'); }});
          frame.src = FIXED_PAGES[state.key];
        }} else {{
          subnav.classList.remove('hidden');
          vTabs.forEach(function (t) {{ t.classList.toggle('active', t.dataset.version === state.version); }});
          fTabs.forEach(function (t) {{ t.classList.remove('active'); }});
          sTabs.forEach(function (t) {{ t.classList.toggle('active', t.dataset.sub === state.sub); }});
          frame.src = VERSION_PAGES[state.version][state.sub];
        }}
      }}

      vTabs.forEach(function (tab) {{
        tab.addEventListener('click', function (e) {{
          e.preventDefault();
          var version = tab.dataset.version;
          var cur = parseHash(location.hash);
          var sub = cur.type === 'version' ? cur.sub : 'report';
          var h = '#' + version + '/' + sub;
          if (location.hash !== h) location.hash = h; else activate({{ type: 'version', version: version, sub: sub }});
        }});
      }});

      fTabs.forEach(function (tab) {{
        tab.addEventListener('click', function (e) {{
          e.preventDefault();
          var key = tab.dataset.fixed;
          var h = '#' + key;
          if (location.hash !== h) location.hash = h; else activate({{ type: 'fixed', key: key }});
        }});
      }});

      sTabs.forEach(function (tab) {{
        tab.addEventListener('click', function (e) {{
          e.preventDefault();
          var sub = tab.dataset.sub;
          var cur = parseHash(location.hash);
          var version = cur.type === 'version' ? cur.version : 'latest';
          var h = '#' + version + '/' + sub;
          if (location.hash !== h) location.hash = h; else activate({{ type: 'version', version: version, sub: sub }});
        }});
      }});

      window.addEventListener('hashchange', function () {{ activate(parseHash(location.hash)); }});

      activate(parseHash(location.hash));
    }}());
  </script>
  <script>
    (function () {{
      var btn = document.getElementById('run-selector-btn');
      var panel = document.getElementById('run-panel');
      var list = document.getElementById('run-list');
      var loaded = false;

      btn.addEventListener('click', function (e) {{
        e.preventDefault();
        panel.classList.toggle('open');
        if (!loaded) {{
          loaded = true;
          fetch('runs.json')
            .then(function (r) {{ if (!r.ok) throw new Error(r.status); return r.json(); }})
            .then(function (data) {{
              if (!data.runs || data.runs.length === 0) {{
                list.innerHTML = '<div class="run-panel-empty">No archived runs found.</div>';
                return;
              }}
              var frame = document.getElementById('frame');
              list.innerHTML = data.runs.map(function (run) {{
                var date = run.generated_at
                  ? new Date(run.generated_at).toLocaleDateString('en-GB', {{
                      day: '2-digit', month: 'short', year: 'numeric',
                      hour: '2-digit', minute: '2-digit'
                    }})
                  : 'Unknown date';
                var t = run.totals || {{}};
                var stats = t.tests
                  ? '<span class="pass">' + (t.passed || 0) + ' passed</span>, '
                    + '<span class="fail">' + (t.failed || 0) + ' failed</span>, '
                    + (t.skipped || 0) + ' skipped / ' + t.tests + ' total'
                  : '';
                var pid = run.pipeline_id || run.package_version || '?';
                var runUrl = 'runs/' + pid + '/report.html';
                return '<a class="run-item" href="' + runUrl + '" data-run-url="' + runUrl + '">'
                  + '<div class="run-item-date">Pipeline ' + pid + ' &mdash; ' + date + '</div>'
                  + (stats ? '<div class="run-item-stats">' + stats + '</div>' : '')
                  + '</a>';
              }}).join('');
              list.querySelectorAll('.run-item').forEach(function (item) {{
                item.addEventListener('click', function (e) {{
                  e.preventDefault();
                  frame.src = item.dataset.runUrl;
                  panel.classList.remove('open');
                  document.querySelectorAll('.tab').forEach(function (t) {{ t.classList.remove('active'); }});
                  document.getElementById('subnav').classList.add('hidden');
                }});
              }});
            }})
            .catch(function () {{
              list.innerHTML = '<div class="run-panel-empty">Could not load run history.</div>';
            }});
        }}
      }});

      document.addEventListener('click', function (e) {{
        if (!btn.contains(e.target) && !panel.contains(e.target)) {{
          panel.classList.remove('open');
        }}
      }});
    }}());
  </script>
</body>

</html>
"""


def _main() -> None:
    parser = argparse.ArgumentParser(description="Generate test-report index.html")
    parser.add_argument(
        "--historic",
        nargs="*",
        default=[],
        metavar="VERSION",
        help="Historic version labels to include (e.g. 26.04 26.03)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    html = _generate(args.historic or [])

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html, encoding="utf-8")
    else:
        sys.stdout.write(html)


if __name__ == "__main__":
    _main()
