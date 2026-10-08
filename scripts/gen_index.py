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
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ height: 100%; overflow: hidden; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #e2e8f0; display: flex; flex-direction: column; }}
    nav {{ display: flex; align-items: center; gap: 6px; padding: 10px 16px; background: #1e293b; border-bottom: 1px solid #334155; flex-shrink: 0; }}
    .nav-left {{ display: flex; gap: 6px; flex: 1; flex-wrap: wrap; }}
    .nav-right {{ display: flex; gap: 6px; flex-shrink: 0; }}
    .subnav {{ display: flex; gap: 6px; padding: 6px 16px; background: #0f172a; border-bottom: 1px solid #1e293b; flex-shrink: 0; }}
    .subnav.hidden {{ display: none; }}
    .tab {{ padding: 7px 22px; border-radius: 20px; font-size: .85em; font-weight: 600; text-decoration: none; color: #94a3b8; background: #0f172a; border: 1px solid #334155; transition: color .12s, border-color .12s, background .12s; cursor: pointer; }}
    .tab:hover {{ color: #e2e8f0; border-color: #94a3b8; }}
    .tab.active {{ color: #38bdf8; border-color: #38bdf8; background: rgba(56, 189, 248, .08); }}
    .subtab {{ padding: 4px 16px; border-radius: 20px; font-size: .80em; font-weight: 600; text-decoration: none; color: #94a3b8; background: transparent; border: 1px solid #334155; transition: color .12s, border-color .12s, background .12s; cursor: pointer; }}
    .subtab:hover {{ color: #e2e8f0; border-color: #94a3b8; }}
    .subtab.active {{ color: #38bdf8; border-color: #38bdf8; background: rgba(56, 189, 248, .08); }}
    iframe {{ flex: 1; width: 100%; border: none; display: block; }}
  </style>
</head>

<body>
  <nav>
    <div class="nav-left">
{nav_version_tabs}
{third_party_tab_html}
    </div>
    <div class="nav-right">
      <a class="tab" data-fixed="features" href="#">Features</a>
      <a class="tab" data-fixed="tifg" href="#">TIFG Test Plan</a>
      <a class="tab" data-fixed="wg11" href="#">WG11 Test Plan</a>
      <a class="tab" data-fixed="history" href="#">History</a>
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
        history: 'about:blank'
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
        // Clear srcdoc so frame.src works again when leaving History
        frame.removeAttribute('srcdoc');
        if (state.type === 'fixed') {{
          subnav.classList.add('hidden');
          vTabs.forEach(function (t) {{ t.classList.remove('active'); }});
          fTabs.forEach(function (t) {{ t.classList.toggle('active', t.dataset.fixed === state.key); }});
          sTabs.forEach(function (t) {{ t.classList.remove('active'); }});
          if (state.key === 'history') {{
            loadHistory();
          }} else {{
            frame.src = FIXED_PAGES[state.key];
          }}
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

      /* Deep-link bridge: called by the History comparison surfaces to jump to
         a specific test case. Stays inside the index navigator (keeps the top
         nav bar) by switching the frame to the Latest/All Tests view and
         loading all.html#<anchor> in a single assignment, so all.js sees the
         hash at load time and runs focusAnchor (reveal, scroll, highlight). We
         set the tab state directly and keep the top-level hash in sync with
         replaceState, rather than routing through the hash/activate round-trip
         which would reset frame.src without the anchor and race the load. */
      window.ocuduJumpToTest = function (anchor) {{
        if (!anchor) return;
        // Reflect the Latest / All Tests selection in the nav chrome.
        subnav.classList.remove('hidden');
        vTabs.forEach(function (t) {{ t.classList.toggle('active', t.dataset.version === 'latest'); }});
        fTabs.forEach(function (t) {{ t.classList.remove('active'); }});
        sTabs.forEach(function (t) {{ t.classList.toggle('active', t.dataset.sub === 'all'); }});
        frame.removeAttribute('srcdoc');
        var target = VERSION_PAGES['latest']['all'] + '#' + anchor;
        var samePage = false;
        try {{
          samePage = frame.contentWindow &&
            frame.contentWindow.location.pathname.indexOf(VERSION_PAGES['latest']['all']) !== -1;
        }} catch (e) {{ samePage = false; }}
        if (samePage) {{
          // Already on all.html: move the hash (clear first to force a change).
          try {{
            frame.contentWindow.location.hash = '';
            frame.contentWindow.location.hash = anchor;
          }} catch (e) {{ frame.src = target; }}
        }} else {{
          // Single assignment: the hash is present at load so all.js focuses it.
          frame.src = target;
        }}
        // Keep the top-level hash in sync WITHOUT invoking activate (which would
        // reset frame.src to a hash-less all.html and drop the anchor).
        if (location.hash !== '#latest/all') {{
          history.replaceState(null, '', '#latest/all');
        }}
      }};

      /* ── History tab ─────────────────────────────────────── */
      var FAIL = {{ failed:1, error:1 }};
      var CSS = '*{{box-sizing:border-box;margin:0;padding:0}}'
        + 'body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:24px}}'
        + '.card{{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px 20px;text-align:center}}'
        + '.card-val{{font-size:2em;font-weight:800;line-height:1.1}}'
        + '.card-lbl{{font-size:.75em;color:#94a3b8;text-transform:uppercase;margin-top:4px}}'
        + 'select,button{{font-family:inherit}}';

      function loadHistory() {{
        frame.srcdoc = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' + CSS + '</style></head><body><p style="color:#94a3b8;padding:40px;text-align:center">Loading history...</p></body></html>';
        fetch('runs.json')
          .then(function(r) {{ if (!r.ok) throw new Error(r.status); return r.json(); }})
          .then(function(data) {{ renderHistoryPage(data.runs || []); }})
          .catch(function() {{ renderHistoryPage([]); }});
      }}

      function renderHistoryPage(runs) {{
        var html = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' + CSS + '</style></head><body>';
        html += '<h2 style="margin-bottom:20px">History</h2>';

        /* ── Compare picker (top) ────────────────────────── */
        html += '<h3 style="margin-bottom:12px;font-size:1em;color:#94a3b8">Compare Two Runs</h3>';
        html += renderComparePicker(runs);

        /* ── Latest vs Previous comparison ───────────────── */
        html += '<h3 style="margin:24px 0 12px;font-size:1em;color:#94a3b8">Latest vs Previous</h3>';
        html += '<div id="comparison-slot" style="margin-bottom:32px"><p style="color:#64748b;font-size:.9em">Loading comparison...</p></div>';

        /* ── Trends chart ────────────────────────────────── */
        html += '<h3 style="margin:24px 0 12px;font-size:1em;color:#94a3b8">Trends</h3>';
        html += renderTrendsSection(runs);

        /* ── Run History list ────────────────────────────── */
        html += '<h3 style="margin:24px 0 12px;font-size:1em;color:#94a3b8">Archived Runs</h3>';
        html += renderRunList(runs);

        html += '<scr' + 'ipt>' + comparisonLoaderJS() + '</scr' + 'ipt>';
        html += '</body></html>';
        frame.srcdoc = html;

        // Attach compare handler after srcdoc renders
        setTimeout(function() {{
          var inner = frame.contentDocument;
          if (!inner) return;
          var btn = inner.getElementById('cmp-go');
          if (!btn) return;
          btn.addEventListener('click', function() {{
            var bp = inner.getElementById('cmp-base').value;
            var hp = inner.getElementById('cmp-head').value;
            var res = inner.getElementById('cmp-result');
            if (!bp || !hp) {{ alert('Select both runs.'); return; }}
            if (bp === hp) {{ alert('Pick two different runs.'); return; }}
            // Ordering guard: BASE must be the older run and HEAD the newer, or
            // the diff reports fixes as regressions and vice versa. The run ids
            // are pipeline ids that increase over time, so if BASE > HEAD the
            // user picked them backwards. Auto-swap and tell them, so the result
            // is never silently backwards.
            var swapped = false;
            if (parseInt(bp, 10) > parseInt(hp, 10)) {{
              var tmp = bp; bp = hp; hp = tmp; swapped = true;
            }}
            res.innerHTML = '<p style="color:#94a3b8">Comparing...</p>';
            Promise.all([
              fetch('runs/' + bp + '/results.json').then(function(r) {{ return r.ok ? r.json() : null; }}),
              fetch('runs/' + hp + '/results.json').then(function(r) {{ return r.ok ? r.json() : null; }})
            ]).then(function(p) {{
              var base = p[0], head = p[1];
              if (!base || !head) {{ res.innerHTML = '<p style="color:#f87171">Could not load results.json. Only the 5 most recent runs are available.</p>'; return; }}
              function flat(d) {{ var m = {{}}; (d.suites||[]).forEach(function(s) {{ (s.tests||[]).forEach(function(t) {{ m[t.key] = t; }}); }}); return m; }}
              var bm = flat(base), hm = flat(head), ak = {{}};
              Object.keys(bm).forEach(function(k) {{ ak[k] = 1; }});
              Object.keys(hm).forEach(function(k) {{ ak[k] = 1; }});
              var regs=[], fixes=[], nf=[], np=[], rem=[], unchanged=0;
              Object.keys(ak).sort().forEach(function(k) {{
                var b = bm[k], h = hm[k];
                var sb = b ? b.status : null, sh = h ? h.status : null;
                var anchor = (h && h.anchor) || (b && b.anchor) || '';
                if (!b && (sh === 'failed' || sh === 'error')) nf.push({{key:k, head:sh, anchor:anchor}});
                else if (!b && sh === 'passed') np.push({{key:k, head:sh, anchor:anchor}});
                else if (!b) np.push({{key:k, head:sh, anchor:anchor}});
                else if (!h) rem.push({{key:k, base:sb, anchor:''}});
                else if (sb === sh) {{ unchanged++; }}
                else if ((sh === 'failed' || sh === 'error') && sb !== 'failed' && sb !== 'error') regs.push({{key:k, base:sb, head:sh, anchor:anchor}});
                else if (sh === 'passed' && (sb === 'failed' || sb === 'error')) fixes.push({{key:k, base:sb, head:sh, anchor:anchor}});
                else {{ unchanged++; }}
              }});
              function pill(s) {{
                var c = (s === 'failed' || s === 'error') ? '#f87171' : s === 'passed' ? '#4ade80' : '#fb923c';
                return '<span style="color:' + c + ';font-weight:600">' + s + '</span>';
              }}
              // Deep-link a test name to its row in the Latest report. Clicking
              // switches the parent frame to the Latest/report tab and targets
              // the test's anchor (report.js opens + scrolls to it).
              function keyCell(i) {{
                var key = i.key.replace(/</g, '&lt;');
                if (!i.anchor) return '<span style="font-family:monospace;font-size:.85em">' + key + '</span>';
                return '<a href="#" data-anchor="' + i.anchor + '" class="tc-jump" '
                  + 'style="font-family:monospace;font-size:.85em;color:#38bdf8;text-decoration:none">' + key + '</a>';
              }}
              function sect(cls, title, items, color) {{
                if (!items.length) return '';
                var rows = items.map(function(i) {{
                  var detail = (i.base ? pill(i.base) + ' &rarr; ' : '') + (i.head ? pill(i.head) : '<span style="color:#64748b">removed</span>');
                  return '<tr class="cmp-prow" data-key="' + i.key.toLowerCase().replace(/"/g, '') + '" style="border-top:1px solid #1e293b"><td style="padding:6px 10px">' + keyCell(i) + '</td><td style="padding:6px 10px">' + detail + '</td></tr>';
                }}).join('');
                return '<details open class="cmp-sect" data-sect="' + cls + '" style="margin-bottom:12px;background:#1e293b;border:1px solid #334155;border-radius:8px;overflow:hidden">'
                  + '<summary style="padding:12px 16px;cursor:pointer;font-weight:600;border-left:4px solid ' + color + '">' + title
                  + ' <span style="background:#0f172a;border-radius:12px;padding:2px 10px;font-size:.82em;margin-left:8px">' + items.length + '</span>'
                  + '</summary><table style="width:100%;border-collapse:collapse;font-size:.85em">' + rows + '</table></details>';
              }}
              // Clickable filter cards: clicking a card shows only its section.
              function card(cls, count, label, color) {{
                var clickable = count > 0;
                return '<button class="cmp-fcard" data-sect="' + cls + '"'
                  + (clickable ? '' : ' disabled')
                  + ' style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px 20px;text-align:center;font-family:inherit;'
                  + (clickable ? 'cursor:pointer' : 'opacity:.5;cursor:default') + '">'
                  + '<div class="card-val" style="font-size:2em;font-weight:800;line-height:1.1;color:' + (count ? color : '#64748b') + '">' + count + '</div>'
                  + '<div class="card-lbl" style="font-size:.75em;color:#94a3b8;text-transform:uppercase;margin-top:4px">' + label + '</div></button>';
              }}
              var noteHtml = swapped
                ? '<p style="color:#fb923c;font-size:.82em;margin-bottom:10px">Runs were in the wrong order (BASE must be older), so they were swapped automatically.</p>'
                : '';
              var h = noteHtml
                + '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">'
                + card('regs', regs.length, 'Regressions', '#f87171')
                + card('fixes', fixes.length, 'Fixes', '#4ade80')
                + card('nf', nf.length, 'New Failures', '#f87171')
                + card('np', np.length, 'New Passes', '#4ade80')
                + card('rem', rem.length, 'Removed', '#fb923c')
                + '</div>'
                + '<input type="text" id="cmp-prow-search" placeholder="Filter tests..." '
                + 'style="width:100%;max-width:360px;padding:8px 12px;margin-bottom:16px;background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:6px;font-size:.85em">'
                + sect('regs', 'Regressions', regs, '#f87171') + sect('fixes', 'Fixes', fixes, '#4ade80')
                + sect('nf', 'New Failures', nf, '#f87171') + sect('np', 'New Passes', np, '#4ade80')
                + sect('rem', 'Removed', rem, '#fb923c');
              if (!regs.length && !fixes.length && !nf.length && !np.length && !rem.length) {{
                h += '<p style="color:#94a3b8;text-align:center;padding:20px">No differences found. ' + unchanged + ' tests unchanged.</p>';
              }}
              res.innerHTML = '<h4 style="margin-bottom:12px">Pipeline ' + bp + ' &rarr; ' + hp + '</h4>' + h;

              // Wire filter cards.
              var activeSect = null;
              var fcards = res.querySelectorAll('.cmp-fcard[data-sect]:not([disabled])');
              var sects = res.querySelectorAll('.cmp-sect');
              fcards.forEach(function(c) {{
                c.addEventListener('click', function() {{
                  var target = this.getAttribute('data-sect');
                  if (activeSect === target) {{
                    activeSect = null;
                    fcards.forEach(function(x) {{ x.style.outline = ''; }});
                    sects.forEach(function(s) {{ s.style.display = ''; }});
                  }} else {{
                    activeSect = target;
                    fcards.forEach(function(x) {{ x.style.outline = ''; }});
                    this.style.outline = '2px solid #38bdf8';
                    sects.forEach(function(s) {{ s.style.display = (s.getAttribute('data-sect') === target) ? '' : 'none'; }});
                  }}
                }});
              }});

              // Wire search over result rows.
              var search = res.querySelector('#cmp-prow-search');
              if (search) {{
                search.addEventListener('input', function() {{
                  var q = this.value.toLowerCase();
                  res.querySelectorAll('.cmp-prow').forEach(function(row) {{
                    var k = row.getAttribute('data-key') || '';
                    row.style.display = k.indexOf(q) !== -1 ? '' : 'none';
                  }});
                }});
              }}

              // Wire test-name deep-links: jump to the Latest report tab + anchor.
              res.querySelectorAll('.tc-jump[data-anchor]').forEach(function(a) {{
                a.addEventListener('click', function(e) {{
                  e.preventDefault();
                  var anchor = this.getAttribute('data-anchor');
                  if (parent && parent.ocuduJumpToTest) parent.ocuduJumpToTest(anchor);
                }});
              }});
            }}).catch(function() {{ res.innerHTML = '<p style="color:#f87171">Comparison failed.</p>'; }});
          }});
        }}, 100);
      }}

      /* ── Trends ────────────────────────────────────────── */
      function renderTrendsSection(runs) {{
        var data = runs.slice().reverse().filter(function(r) {{ return r.totals && r.totals.tests; }});
        if (data.length < 2) return '<p style="color:#64748b;font-size:.9em;margin-bottom:24px">Not enough runs for a trends chart (need at least 2).</p>';
        var maxTests = Math.max.apply(null, data.map(function(r) {{ return r.totals.tests; }}));
        var W = 800, H = 300, PAD = 50, RIGHT = 20, TOP = 20;
        var chartW = W - PAD - RIGHT, chartH = H - TOP - 40;
        function x(i) {{ return PAD + (i / (data.length - 1)) * chartW; }}
        function y(v) {{ return TOP + chartH - (v / maxTests) * chartH; }}
        function line(vals, color) {{
          return '<polyline points="' + vals.map(function(v,i){{ return x(i)+','+y(v); }}).join(' ') + '" fill="none" stroke="' + color + '" stroke-width="2.5" stroke-linejoin="round"/>';
        }}
        function dots(vals, color) {{
          return vals.map(function(v,i){{ return '<circle cx="'+x(i)+'" cy="'+y(v)+'" r="4" fill="'+color+'"><title>'+v+'</title></circle>'; }}).join('');
        }}
        var passed = data.map(function(r){{ return r.totals.passed||0; }});
        var failed = data.map(function(r){{ return r.totals.failed||0; }});
        var skipped = data.map(function(r){{ return r.totals.skipped||0; }});
        var total = data.map(function(r){{ return r.totals.tests||0; }});
        var yLabels = '', step = Math.max(1, Math.ceil(maxTests/5));
        for (var t = 0; t <= maxTests; t += step) {{
          yLabels += '<text x="'+(PAD-8)+'" y="'+(y(t)+4)+'" text-anchor="end" fill="#64748b" font-size="11">'+t+'</text>';
          yLabels += '<line x1="'+PAD+'" y1="'+y(t)+'" x2="'+(W-RIGHT)+'" y2="'+y(t)+'" stroke="#1e293b"/>';
        }}
        var xLabels = data.map(function(r,i) {{
          var d = r.generated_at ? new Date(r.generated_at) : null;
          var lb = d ? (d.getDate()+'/'+(d.getMonth()+1)) : ('R'+(i+1));
          return '<text x="'+x(i)+'" y="'+(H-8)+'" text-anchor="middle" fill="#64748b" font-size="10">'+lb+'</text>';
        }}).join('');
        var svg = '<svg viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:900px;height:auto">'
          + yLabels + xLabels
          + line(total,'#64748b') + line(passed,'#4ade80') + line(failed,'#f87171') + line(skipped,'#fb923c')
          + dots(total,'#64748b') + dots(passed,'#4ade80') + dots(failed,'#f87171') + dots(skipped,'#fb923c')
          + '</svg>';
        var legend = '<div style="display:flex;gap:16px;margin-bottom:12px;font-size:.82em;flex-wrap:wrap">'
          + '<span><span style="color:#64748b">\\u2014</span> Total</span>'
          + '<span><span style="color:#4ade80">\\u2014</span> Passed</span>'
          + '<span><span style="color:#f87171">\\u2014</span> Failed</span>'
          + '<span><span style="color:#fb923c">\\u2014</span> Skipped</span></div>';
        var rows = data.slice().reverse().map(function(r) {{
          var tt = r.totals, rate = tt.tests ? ((tt.passed/tt.tests)*100).toFixed(1) : '0.0';
          var pid = r.pipeline_id||'?';
          var lbl = r.label ? ' <span style="background:#334155;color:#38bdf8;border-radius:10px;padding:1px 7px;font-size:.85em">'+r.label.replace(/</g,'&lt;')+'</span>' : '';
          var d = r.generated_at ? new Date(r.generated_at).toLocaleDateString('en-GB',{{day:'2-digit',month:'short'}}) : '';
          var rc = parseFloat(rate)>=95 ? '#4ade80' : parseFloat(rate)>=80 ? '#fb923c' : '#f87171';
          return '<tr style="border-top:1px solid #1e293b"><td style="padding:6px 12px">'+pid+lbl+'</td><td style="padding:6px 12px">'+d+'</td><td style="padding:6px 12px;color:#4ade80">'+tt.passed+'</td><td style="padding:6px 12px;color:#f87171">'+tt.failed+'</td><td style="padding:6px 12px;color:#fb923c">'+tt.skipped+'</td><td style="padding:6px 12px">'+tt.tests+'</td><td style="padding:6px 12px;font-weight:700;color:'+rc+'">'+rate+'%</td></tr>';
        }}).join('');
        var table = '<table style="width:100%;border-collapse:collapse;font-size:.85em;background:#1e293b;border:1px solid #334155;border-radius:8px;overflow:hidden;margin-bottom:24px">'
          + '<thead><tr style="background:#0f172a"><th style="padding:8px 12px;text-align:left;color:#94a3b8">Pipeline</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Date</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Pass</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Fail</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Skip</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Total</th><th style="padding:8px 12px;text-align:left;color:#94a3b8">Rate</th></tr></thead>'
          + '<tbody>' + rows + '</tbody></table>';
        return legend + svg + table;
      }}

      /* ── Run list ──────────────────────────────────────── */
      function renderRunList(runs) {{
        if (!runs.length) return '<p style="color:#64748b;font-size:.9em;margin-bottom:24px">No archived runs found.</p>';
        var items = runs.map(function(run) {{
          var pid = run.pipeline_id || run.package_version || '?';
          var date = run.generated_at ? new Date(run.generated_at).toLocaleDateString('en-GB',{{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}}) : 'Unknown date';
          var label = run.label ? '<span style="background:#334155;color:#38bdf8;border-radius:10px;padding:1px 8px;font-size:.82em;margin:0 8px">'+run.label.replace(/</g,'&lt;')+'</span>' : '';
          var t = run.totals || {{}};
          var stats = t.tests ? '<span style="color:#4ade80">'+(t.passed||0)+' passed</span>, <span style="color:#f87171">'+(t.failed||0)+' failed</span>, '+(t.skipped||0)+' skipped / '+t.tests+' total' : '';
          return '<a href="runs/'+pid+'/report.html" target="_blank" style="display:block;padding:10px 14px;text-decoration:none;color:#e2e8f0;font-size:.85em;border-bottom:1px solid #1e293b;transition:background .1s" onmouseover="this.style.background=\\'#334155\\'" onmouseout="this.style.background=\\'\\'"><div style="font-weight:600">'+date+label+'<span style="color:#94a3b8">#'+pid+'</span></div>'+(stats ? '<div style="color:#94a3b8;font-size:.9em;margin-top:2px">'+stats+'</div>' : '')+'</a>';
        }}).join('');
        return '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;overflow:hidden;max-height:300px;overflow-y:auto;margin-bottom:24px">' + items + '</div>';
      }}

      /* ── Compare picker ────────────────────────────────── */
      function renderComparePicker(runs) {{
        if (runs.length < 2) return '<p style="color:#64748b;font-size:.9em">Need at least 2 archived runs to compare.</p>';
        // runs is newest-first. Default HEAD = latest (runs[0]), BASE =
        // previous (runs[1]) so the sensible comparison is pre-selected and the
        // order is correct out of the box.
        var sorted = runs.slice().sort(function(a, b) {{
          return (parseInt(b.pipeline_id||b.package_version||0,10)) - (parseInt(a.pipeline_id||a.package_version||0,10));
        }});
        var headDefault = sorted[0].pipeline_id || sorted[0].package_version;
        var baseDefault = sorted[1].pipeline_id || sorted[1].package_version;
        function optsFor(selectedPid) {{
          return '<option value="">Select a run...</option>' + sorted.map(function(r) {{
            var pid = r.pipeline_id || r.package_version || '?';
            var d = r.generated_at ? new Date(r.generated_at).toLocaleDateString('en-GB',{{day:'2-digit',month:'short'}}) : '';
            var sel = (String(pid) === String(selectedPid)) ? ' selected' : '';
            var lbl = r.label ? ' ' + r.label : '';
            return '<option value="'+pid+'"'+sel+'>'+(d ? d : '')+lbl+' #'+pid+'</option>';
          }}).join('');
        }}
        var sel = 'style="width:100%;max-width:300px;padding:8px 10px;background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:6px;font-size:.85em"';
        return '<div style="display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin-bottom:24px">'
          + '<div><label style="display:block;font-size:.75em;color:#94a3b8;margin-bottom:4px">BASE (older)</label><select id="cmp-base" '+sel+'>'+optsFor(baseDefault)+'</select></div>'
          + '<div><label style="display:block;font-size:.75em;color:#94a3b8;margin-bottom:4px">HEAD (newer)</label><select id="cmp-head" '+sel+'>'+optsFor(headDefault)+'</select></div>'
          + '<button id="cmp-go" style="padding:8px 24px;background:#38bdf8;color:#0f172a;border:none;border-radius:6px;font-weight:700;font-size:.85em;cursor:pointer">Compare</button>'
          + '</div><div id="cmp-result"></div>';
      }}

      /* ── JS for loading comparison.html into the slot ── */
      function comparisonLoaderJS() {{
        return 'fetch("comparison.html").then(function(r){{'
          + 'if(!r.ok)throw new Error(r.status);return r.text()}}).then(function(t){{'
          + 'var s=document.getElementById("comparison-slot");'
          + 'var f=document.createElement("iframe");'
          + 'f.style.cssText="width:100%;border:1px solid #334155;border-radius:8px;min-height:500px";'
          + 'f.srcdoc=t;s.innerHTML="";s.appendChild(f)'
          + '}}).catch(function(){{'
          + 'document.getElementById("comparison-slot").innerHTML='
          + '"<p style=\\"color:#64748b;font-size:.9em\\">No comparison available yet (generated after the second run).</p>"'
          + '}});';
      }}

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
