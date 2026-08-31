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

# pylint: disable=line-too-long

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
          <div class="run-panel-title" style="margin-top:8px;border-top:1px solid #334155;padding-top:10px;">Compare Runs</div>
          <div style="padding:4px 14px 10px;">
            <select id="cmp-base" style="width:100%;margin-bottom:6px;padding:6px 8px;background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:6px;font-size:.82em;">
              <option value="">Base (older)...</option>
            </select>
            <select id="cmp-head" style="width:100%;margin-bottom:8px;padding:6px 8px;background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:6px;font-size:.82em;">
              <option value="">Head (newer)...</option>
            </select>
            <button id="cmp-go" style="width:100%;padding:7px;background:#38bdf8;color:#0f172a;border:none;border-radius:6px;font-weight:700;font-size:.82em;cursor:pointer;">Compare</button>
          </div>
        </div>
      </div>
      <a class="tab" data-fixed="features" href="#">Features</a>
      <a class="tab" data-fixed="tifg" href="#">TIFG Test Plan</a>
      <a class="tab" data-fixed="wg11" href="#">WG11 Test Plan</a>
      <a class="tab" data-fixed="comparison" href="#">Comparison</a>
      <a class="tab" data-fixed="trends" href="#">Trends</a>
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
        comparison: 'comparison.html',
        trends: 'about:blank'
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
              // Populate compare dropdowns
              var baseSelect = document.getElementById('cmp-base');
              var headSelect = document.getElementById('cmp-head');
              data.runs.forEach(function (run) {{
                var pid = run.pipeline_id || run.package_version || '?';
                var date = run.generated_at ? new Date(run.generated_at).toLocaleDateString('en-GB', {{ day:'2-digit', month:'short' }}) : '';
                var label = 'Pipeline ' + pid + (date ? ' (' + date + ')' : '');
                baseSelect.add(new Option(label, pid));
                headSelect.add(new Option(label, pid));
              }});
              // Store runs data globally for trends
              window._runsData = data.runs;
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
  <script>
    // Compare button: fetch two results.json, diff client-side, render in iframe
    (function () {{
      var FAIL = {{ failed:1, error:1 }};
      document.getElementById('cmp-go').addEventListener('click', function () {{
        var basePid = document.getElementById('cmp-base').value;
        var headPid = document.getElementById('cmp-head').value;
        if (!basePid || !headPid) return alert('Select both a Base and Head run.');
        if (basePid === headPid) return alert('Base and Head must be different runs.');
        var panel = document.getElementById('run-panel');
        panel.classList.remove('open');
        var frame = document.getElementById('frame');
        frame.srcdoc = '<html><body style="background:#0f172a;color:#94a3b8;font-family:sans-serif;padding:40px;text-align:center"><p>Comparing runs...</p></body></html>';
        Promise.all([
          fetch('runs/' + basePid + '/results.json').then(function(r){{ return r.ok ? r.json() : null; }}),
          fetch('runs/' + headPid + '/results.json').then(function(r){{ return r.ok ? r.json() : null; }})
        ]).then(function (pair) {{
          var base = pair[0], head = pair[1];
          if (!base || !head) {{ frame.srcdoc = '<html><body style="background:#0f172a;color:#f87171;font-family:sans-serif;padding:40px;text-align:center"><p>Could not load results.json for one or both runs. Only the 5 most recent extracted runs are available for comparison.</p></body></html>'; return; }}
          // Flatten
          function flat(d) {{ var m={{}}; (d.suites||[]).forEach(function(s){{ (s.tests||[]).forEach(function(t){{ m[t.key]=t; }}); }}); return m; }}
          var bm = flat(base), hm = flat(head);
          var allKeys = {{}};
          Object.keys(bm).forEach(function(k){{ allKeys[k]=1; }});
          Object.keys(hm).forEach(function(k){{ allKeys[k]=1; }});
          var regs=[], fixes=[], newFail=[], newPass=[], removed=[];
          Object.keys(allKeys).sort().forEach(function (k) {{
            var b = bm[k], h = hm[k];
            var sb = b ? b.status : null, sh = h ? h.status : null;
            if (!b && sh in FAIL) newFail.push({{ key:k, head:sh }});
            else if (!b && sh === 'passed') newPass.push({{ key:k, head:sh }});
            else if (!h) removed.push({{ key:k, base:sb }});
            else if (sb === sh) return;
            else if (sh in FAIL && !(sb in FAIL)) regs.push({{ key:k, base:sb, head:sh }});
            else if (sh === 'passed' && sb in FAIL) fixes.push({{ key:k, base:sb, head:sh }});
          }});
          // Render
          function pill(s) {{ var c = s in FAIL ? '#f87171' : s==='passed' ? '#4ade80' : '#fb923c'; return '<span style="color:'+c+';font-weight:600">'+s+'</span>'; }}
          function sect(title, items, color) {{
            if (!items.length) return '';
            var rows = items.map(function(i) {{
              return '<tr style="border-top:1px solid #1e293b"><td style="padding:6px 10px;font-family:monospace;font-size:.85em">' + i.key.replace(/</g,'&lt;') + '</td><td style="padding:6px 10px">' + (i.base ? pill(i.base) + ' &rarr; ' : '') + (i.head ? pill(i.head) : '<span style="color:#64748b">removed</span>') + '</td></tr>';
            }}).join('');
            return '<details open style="margin-bottom:12px;background:#1e293b;border:1px solid #334155;border-radius:8px;overflow:hidden"><summary style="padding:12px 16px;cursor:pointer;font-weight:600;border-left:4px solid '+color+'"><span>'+title+'</span> <span style="background:#0f172a;border-radius:12px;padding:2px 10px;font-size:.82em;margin-left:8px">'+items.length+'</span></summary><table style="width:100%;border-collapse:collapse;font-size:.85em">'+rows+'</table></details>';
          }}
          var html = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:24px}}</style></head><body>'
            + '<h2 style="margin-bottom:4px">Run Comparison</h2>'
            + '<p style="color:#94a3b8;margin-bottom:20px;font-size:.9em">Pipeline ' + basePid + ' &rarr; ' + headPid + '</p>'
            + '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">'
            + '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px 20px;text-align:center"><div style="font-size:2em;font-weight:800;color:' + (regs.length ? '#f87171' : '#64748b') + '">' + regs.length + '</div><div style="font-size:.75em;color:#94a3b8;text-transform:uppercase">Regressions</div></div>'
            + '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px 20px;text-align:center"><div style="font-size:2em;font-weight:800;color:' + (fixes.length ? '#4ade80' : '#64748b') + '">' + fixes.length + '</div><div style="font-size:.75em;color:#94a3b8;text-transform:uppercase">Fixes</div></div>'
            + '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px 20px;text-align:center"><div style="font-size:2em;font-weight:800;color:' + (newFail.length ? '#f87171' : '#64748b') + '">' + newFail.length + '</div><div style="font-size:.75em;color:#94a3b8;text-transform:uppercase">New Failures</div></div>'
            + '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px 20px;text-align:center"><div style="font-size:2em;font-weight:800;color:' + (newPass.length ? '#4ade80' : '#64748b') + '">' + newPass.length + '</div><div style="font-size:.75em;color:#94a3b8;text-transform:uppercase">New Passes</div></div>'
            + '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px 20px;text-align:center"><div style="font-size:2em;font-weight:800;color:' + (removed.length ? '#fb923c' : '#64748b') + '">' + removed.length + '</div><div style="font-size:.75em;color:#94a3b8;text-transform:uppercase">Removed</div></div>'
            + '</div>'
            + sect('Regressions', regs, '#f87171')
            + sect('Fixes', fixes, '#4ade80')
            + sect('New Failures', newFail, '#f87171')
            + sect('New Passes', newPass, '#4ade80')
            + sect('Removed', removed, '#fb923c');
          if (!regs.length && !fixes.length && !newFail.length && !newPass.length && !removed.length) {{
            html += '<div style="text-align:center;padding:60px 20px;color:#94a3b8"><div style="font-size:3em;margin-bottom:12px">&#10003;</div><p>No differences found between these runs.</p></div>';
          }}
          html += '</body></html>';
          frame.srcdoc = html;
          document.querySelectorAll('.tab').forEach(function (t) {{ t.classList.remove('active'); }});
          document.getElementById('subnav').classList.add('hidden');
        }}).catch(function () {{
          frame.srcdoc = '<html><body style="background:#0f172a;color:#f87171;font-family:sans-serif;padding:40px;text-align:center"><p>Comparison failed.</p></body></html>';
        }});
      }});
    }}());
  </script>
  <script>
    // Trends chart: renders pass/fail/skip over time from runs.json into the iframe
    (function () {{
      function renderTrends(runs) {{
        if (!runs || runs.length < 2) return '<html><body style="background:#0f172a;color:#94a3b8;font-family:sans-serif;padding:40px;text-align:center"><p>Not enough runs for a trends chart (need at least 2).</p></body></html>';
        // Reverse so oldest is first (runs.json is newest-first)
        var data = runs.slice().reverse().filter(function(r) {{ return r.totals && r.totals.tests; }});
        if (data.length < 2) return '<html><body style="background:#0f172a;color:#94a3b8;font-family:sans-serif;padding:40px;text-align:center"><p>Not enough runs with data for a trends chart.</p></body></html>';
        var maxTests = Math.max.apply(null, data.map(function(r) {{ return r.totals.tests; }}));
        var W = 800, H = 300, PAD = 50, RIGHT = 20, TOP = 20;
        var chartW = W - PAD - RIGHT, chartH = H - TOP - 40;
        function x(i) {{ return PAD + (i / (data.length - 1)) * chartW; }}
        function y(v) {{ return TOP + chartH - (v / maxTests) * chartH; }}
        function line(vals, color) {{
          var pts = vals.map(function(v, i) {{ return x(i) + ',' + y(v); }}).join(' ');
          return '<polyline points="' + pts + '" fill="none" stroke="' + color + '" stroke-width="2.5" stroke-linejoin="round"/>';
        }}
        function dots(vals, color) {{
          return vals.map(function(v, i) {{ return '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="4" fill="' + color + '"><title>' + v + '</title></circle>'; }}).join('');
        }}
        var passed = data.map(function(r) {{ return r.totals.passed || 0; }});
        var failed = data.map(function(r) {{ return r.totals.failed || 0; }});
        var skipped = data.map(function(r) {{ return r.totals.skipped || 0; }});
        var total = data.map(function(r) {{ return r.totals.tests || 0; }});
        // Y-axis labels
        var yLabels = '';
        for (var t = 0; t <= maxTests; t += Math.max(1, Math.ceil(maxTests / 5))) {{
          yLabels += '<text x="' + (PAD - 8) + '" y="' + (y(t) + 4) + '" text-anchor="end" fill="#64748b" font-size="11">' + t + '</text>';
          yLabels += '<line x1="' + PAD + '" y1="' + y(t) + '" x2="' + (W - RIGHT) + '" y2="' + y(t) + '" stroke="#1e293b" stroke-width="1"/>';
        }}
        // X-axis labels
        var xLabels = data.map(function(r, i) {{
          var d = r.generated_at ? new Date(r.generated_at) : null;
          var label = d ? (d.getDate() + '/' + (d.getMonth()+1)) : ('R' + (i+1));
          return '<text x="' + x(i) + '" y="' + (H - 8) + '" text-anchor="middle" fill="#64748b" font-size="10">' + label + '</text>';
        }}).join('');
        var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:900px;height:auto">'
          + yLabels + xLabels
          + line(total, '#64748b') + line(passed, '#4ade80') + line(failed, '#f87171') + line(skipped, '#fb923c')
          + dots(total, '#64748b') + dots(passed, '#4ade80') + dots(failed, '#f87171') + dots(skipped, '#fb923c')
          + '</svg>';
        // Pass rate table
        var rows = data.map(function(r) {{
          var t = r.totals;
          var rate = t.tests ? ((t.passed / t.tests) * 100).toFixed(1) : '0.0';
          var pid = r.pipeline_id || '?';
          var d = r.generated_at ? new Date(r.generated_at).toLocaleDateString('en-GB', {{ day:'2-digit', month:'short' }}) : '';
          return '<tr style="border-top:1px solid #1e293b"><td style="padding:6px 12px">' + pid + '</td><td style="padding:6px 12px">' + d + '</td><td style="padding:6px 12px;color:#4ade80">' + t.passed + '</td><td style="padding:6px 12px;color:#f87171">' + t.failed + '</td><td style="padding:6px 12px;color:#fb923c">' + t.skipped + '</td><td style="padding:6px 12px">' + t.tests + '</td><td style="padding:6px 12px;font-weight:700;color:' + (parseFloat(rate) >= 95 ? '#4ade80' : parseFloat(rate) >= 80 ? '#fb923c' : '#f87171') + '">' + rate + '%</td></tr>';
        }}).reverse().join('');
        return '<!DOCTYPE html><html><head><meta charset="utf-8"><style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:24px}}</style></head><body>'
          + '<h2 style="margin-bottom:4px">Test Trends</h2>'
          + '<p style="color:#94a3b8;margin-bottom:20px;font-size:.9em">' + data.length + ' runs</p>'
          + '<div style="display:flex;gap:16px;margin-bottom:16px;font-size:.82em;flex-wrap:wrap">'
          + '<span><span style="color:#64748b">&mdash;</span> Total</span>'
          + '<span><span style="color:#4ade80">&mdash;</span> Passed</span>'
          + '<span><span style="color:#f87171">&mdash;</span> Failed</span>'
          + '<span><span style="color:#fb923c">&mdash;</span> Skipped</span>'
          + '</div>'
          + svg
          + '<h3 style="margin:24px 0 12px;font-size:1em">Run History</h3>'
          + '<table style="width:100%;border-collapse:collapse;font-size:.85em;background:#1e293b;border:1px solid #334155;border-radius:8px;overflow:hidden">'
          + '<thead><tr style="background:#0f172a"><th style="padding:8px 12px;text-align:left;color:#94a3b8">Pipeline</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Date</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Pass</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Fail</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Skip</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Total</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Rate</th></tr></thead>'
          + '<tbody>' + rows + '</tbody></table>'
          + '</body></html>';
      }}
      // Hook into the Trends tab activation
      var origActivate = null;
      var fTabs = document.querySelectorAll('[data-fixed]');
      fTabs.forEach(function (tab) {{
        if (tab.dataset.fixed === 'trends') {{
          tab.addEventListener('click', function () {{
            var frame = document.getElementById('frame');
            function show() {{ frame.srcdoc = renderTrends(window._runsData); }}
            if (window._runsData) {{ show(); return; }}
            frame.srcdoc = '<html><body style="background:#0f172a;color:#94a3b8;font-family:sans-serif;padding:40px;text-align:center"><p>Loading trends...</p></body></html>';
            fetch('runs.json').then(function(r){{ return r.json(); }}).then(function(d){{ window._runsData = d.runs; show(); }}).catch(function(){{
              frame.srcdoc = '<html><body style="background:#0f172a;color:#f87171;font-family:sans-serif;padding:40px;text-align:center"><p>Could not load run data.</p></body></html>';
            }});
          }});
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
