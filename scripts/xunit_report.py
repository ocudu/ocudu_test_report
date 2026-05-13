#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
XUnit HTML reporter — aggregates multiple XUnit XML files into a single HTML report.

Usage:
    python xunit_report.py --dir FOLDER -o report.html
"""

import argparse
import html
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    from ansi2html import Ansi2HTMLConverter
except ImportError:
    print("ERROR: ansi2html is required. Install with: pip install ansi2html", file=sys.stderr)
    sys.exit(2)


_ANSI_CONVERTER = Ansi2HTMLConverter(inline=True, escaped=False)
CAPTURE_HEADER_RE = re.compile(r"^-+\s+Captured \w+\s+-+$", re.MULTILINE)
OTHER_CATEGORY = "others"
OTHER_CATEGORY_DESCRIPTION = "Tests without another classification"


class Status(Enum):
    """Test result status."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


_TC_STATUS_SORT = {Status.SKIPPED: 0, Status.FAILED: 1, Status.ERROR: 1, Status.PASSED: 2}
_FEATURE_STATUS_ICONS = {"passed": "✓", "failed": "✗", "skipped": "⊘", "untested": "—"}


def _clean_output(text: str) -> str:
    """Strip capture headers and convert ANSI escape codes to HTML."""
    text = CAPTURE_HEADER_RE.sub("", text)
    text = text.replace("#x1B", "\x1b")  # pytest XML writer drops the & from &#x1B;
    result: str = _ANSI_CONVERTER.convert(text.strip(), full=False)
    return result


@dataclass
class TestCase:  # pylint: disable=too-many-instance-attributes
    """Holds data for a single test case parsed from an XUnit XML file."""

    name: str
    classname: str
    duration: float
    status: Status
    message: str = ""
    system_out: str = ""
    system_err: str = ""
    labels: list[str] = field(default_factory=list)


@dataclass
class Suite:
    """Collection of test cases belonging to one named suite."""

    name: str
    testcases: list = field(default_factory=list)
    url: str = ""

    @property
    def total(self) -> int:
        """Total number of test cases."""
        return len(self.testcases)

    @property
    def passed(self) -> int:
        """Number of passing test cases."""
        return sum(1 for t in self.testcases if t.status == Status.PASSED)

    @property
    def failed(self) -> int:
        """Number of failed or errored test cases."""
        return sum(1 for t in self.testcases if t.status in (Status.FAILED, Status.ERROR))

    @property
    def skipped(self) -> int:
        """Number of skipped test cases."""
        return sum(1 for t in self.testcases if t.status == Status.SKIPPED)

    @property
    def duration(self) -> float:
        """Total duration in seconds."""
        return float(sum(t.duration for t in self.testcases))


def _parse_testcase(elem) -> TestCase:
    name = elem.get("name", "")
    classname = elem.get("classname", "")
    duration = float(elem.get("time", 0) or 0)

    failure = elem.find("failure")
    error = elem.find("error")
    skipped = elem.find("skipped")

    if failure is not None:
        status = Status.FAILED
        message = failure.get("message", "") or (failure.text or "")
    elif error is not None:
        status = Status.ERROR
        message = error.get("message", "") or (error.text or "")
    elif skipped is not None:
        status = Status.SKIPPED
        message = skipped.get("message", "") or (skipped.text or "")
    else:
        status = Status.PASSED
        message = ""

    system_out = _clean_output(elem.findtext("system-out", ""))
    system_err = _clean_output(elem.findtext("system-err", ""))

    labels: list[str] = []
    props_elem = elem.find("properties")
    if props_elem is not None:
        for prop in props_elem.findall("property"):
            if prop.get("name") in ("cmake_labels", "markers"):
                labels.extend(v.strip() for v in prop.get("value", "").split(";") if v.strip())

    return TestCase(name, classname, duration, status, message, system_out, system_err, labels)


def parse_xml(name: str, path: Path) -> Suite:
    """Parse a single XUnit XML file and return a Suite."""
    tree = ET.parse(path)
    root = tree.getroot()
    suite = Suite(name=name)

    if root.tag == "testsuites":
        elems = [tc for ts in root.findall("testsuite") for tc in ts.findall("testcase")]
    elif root.tag == "testsuite":
        elems = root.findall("testcase")
    else:
        elems = root.findall(".//testcase")

    for elem in elems:
        suite.testcases.append(_parse_testcase(elem))
    suite.testcases.sort(key=lambda tc: f"{tc.classname}.{tc.name}")
    return suite


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{int(m)}m {s:.1f}s"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{int(h)}h {int(m)}m"
    d, h = divmod(h, 24)
    return f"{int(d)}d {int(h)}h"


_ICONS = {
    Status.PASSED: "✓",
    Status.FAILED: "✗",
    Status.ERROR: "!",
    Status.SKIPPED: "⊘",
}


def _status_badge(status: Status) -> str:
    icon = _ICONS.get(status, "?")
    return f'<span class="badge {status.value}">{icon} {status.value}</span>'


def _render_testcase(tc: TestCase, idx: int, url: str = "") -> str:
    parity = "even" if idx % 2 == 0 else "odd"
    label = f"{html.escape(tc.classname)}." if tc.classname else ""

    gitlab_html = ""
    if url:
        gitlab_html = (
            f'<a class="tc-gitlab-link" href="{html.escape(url)}" target="_blank"'
            f' title="GitLab pipeline" onclick="event.stopPropagation()">'
            f'<img src="https://about.gitlab.com/images/press/gitlab-logo-500-rgb.svg"'
            f' alt="GitLab" height="20"></a>'
        )

    header = (
        f"{_status_badge(tc.status)}"
        f'<span class="tc-name">{label}<b>{html.escape(tc.name)}</b></span>'
        f'<span class="tc-duration">{_fmt_duration(tc.duration)}</span>'
        f"{gitlab_html}"
    )

    labels_html = ""
    if tc.labels:
        chips = "".join(f'<span class="label-chip">{html.escape(lbl)}</span>' for lbl in tc.labels)
        labels_html = f'<div class="labels"><span class="labels-title">Labels:</span>{chips}</div>'

    msg_html = ""
    if tc.message:
        msg_html = f'<pre class="msg-failure">{html.escape(tc.message.strip())}</pre>'

    out_html = ""
    if tc.system_out.strip():
        out_html = f'<pre class="system-out">{tc.system_out.strip()}</pre>'

    err_html = ""
    if tc.system_err.strip():
        err_html = f'<pre class="system-err">{tc.system_err.strip()}</pre>'

    detail_body = labels_html + msg_html + out_html + err_html

    if detail_body:
        return (
            f'<details class="tc-detail {parity}">'
            f'<summary class="tc-row {parity}">{header}</summary>'
            f'<div class="tc-detail-body">{detail_body}</div>'
            f"</details>"
        )

    return f'<div class="tc-row {parity}">{header}</div>'


@dataclass
class FeatureDef:
    """A feature entry parsed from features.yaml."""

    description: str
    labels: set = field(default_factory=set)
    release: str = ""


@dataclass
class FeatureGroup:
    """A feature with its matched test cases grouped by suite."""

    description: str
    suites: dict = field(default_factory=dict)  # {suite_name: (url, [TestCase])}


def _parse_features(raw: dict) -> dict[str, FeatureDef]:
    """Parse features YAML.

    Keys may use 'name|alias1|alias2' syntax: the first token is the display name,
    all tokens (including the first) are valid matching labels.
    Returns {display_name: FeatureDef}.
    """
    result: dict[str, FeatureDef] = {}
    for item in raw["features"]:
        key = item["id"]
        description = item["description"]
        parts = [p.strip() for p in str(key).split("|")]
        result[parts[0]] = FeatureDef(description=description or "", labels=set(parts), release=item.get("release", ""))
    return result


def _group_by_features(suites: list, features: dict[str, FeatureDef]) -> dict[str, FeatureGroup]:
    """Return {display_name: FeatureGroup}, tests with no matching label go under Others.

    All defined features are always included (untested ones show with zero counts).
    The Others bucket is included only when it has at least one test.
    """
    alias_map = {alias: name for name, fd in features.items() for alias in fd.labels}

    grouped: dict[str, FeatureGroup] = {name: FeatureGroup(description=fd.description) for name, fd in features.items()}
    grouped[OTHER_CATEGORY] = FeatureGroup(description=OTHER_CATEGORY_DESCRIPTION)

    for suite in suites:
        for tc in suite.testcases:
            matched = list(dict.fromkeys(alias_map[lbl] for lbl in tc.labels if lbl in alias_map))
            for fid in matched or [OTHER_CATEGORY]:
                if suite.name not in grouped[fid].suites:
                    grouped[fid].suites[suite.name] = (suite.url, [])
                grouped[fid].suites[suite.name][1].append(tc)

    return {fid: fg for fid, fg in grouped.items() if fid != OTHER_CATEGORY or fg.suites}


def _header_link_or_duration(link: str, duration: float) -> str:
    if link:
        return f"<a class='header-link' href='{html.escape(link)}'>{link.split('/')[-1]}</a>"
    return f"⏱ {_fmt_duration(duration)}"


def _feature_status(failed: int, passed: int, skipped: int) -> str:
    if failed > 0:
        return "failed"
    if passed > 0:
        return "passed"
    if skipped > 0:
        return "skipped"
    return "untested"


_REPORT_JS = r"""
(function () {
  const STATUS_ORDER = { untested: 0, skipped: 1, failed: 2, passed: 3 };
  let sortCol = null, sortDir = 1;

  function cmp(a, b) {
    if (typeof a === 'number' && typeof b === 'number') return a - b;
    return String(a).localeCompare(String(b));
  }

  function cellValue(row, col) {
    switch (col) {
      case 'status':  return STATUS_ORDER[row.dataset.status] ?? 99;
      case 'fid':     return row.dataset.fid || '';
      case 'desc':    return row.cells[2].textContent.trim();
      case 'release': return row.dataset.release || '';
      case 'failed':  return +row.dataset.failed;
      case 'passed':  return +row.dataset.passed;
      case 'skipped': return +row.dataset.skipped;
      default:        return '';
    }
  }

  function defaultCompare(a, b) {
    return cmp(a.dataset.release || '', b.dataset.release || '')
        || cmp(STATUS_ORDER[a.dataset.status] ?? 99, STATUS_ORDER[b.dataset.status] ?? 99)
        || cmp(a.dataset.fid || '', b.dataset.fid || '');
  }

  function reorder(rows) {
    const tbody = document.querySelector('#feature-table tbody');
    rows.forEach((row, i) => {
      row.classList.toggle('even', i % 2 === 0);
      row.classList.toggle('odd',  i % 2 !== 0);
      tbody.appendChild(row);
      const exp = document.getElementById(row.dataset.expand);
      if (exp) tbody.appendChild(exp);
    });
    document.querySelectorAll('#feature-table thead th').forEach(th => {
      th.classList.remove('sort-asc', 'sort-desc');
      if (sortCol && th.dataset.col === sortCol)
        th.classList.add(sortDir === 1 ? 'sort-asc' : 'sort-desc');
    });
  }

  function applyFilters() {
    const sf = document.getElementById('filter-status').value;
    const rf = document.getElementById('filter-release').value;
    let vi = 0;
    document.querySelectorAll('#feature-table .feature-row').forEach(row => {
      const ok = (!sf || row.dataset.status === sf)
               && (!rf || row.dataset.release === rf);
      row.hidden = !ok;
      const exp = document.getElementById(row.dataset.expand);
      if (!ok) {
        if (exp) exp.hidden = true;
        row.classList.remove('open');
      } else {
        row.classList.toggle('even', vi % 2 === 0);
        row.classList.toggle('odd',  vi % 2 !== 0);
        vi++;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    const tbody = document.querySelector('#feature-table tbody');
    if (!tbody) return;

    const getRows = () => [...tbody.querySelectorAll('.feature-row')];

    reorder(getRows().sort(defaultCompare));

    document.querySelectorAll('#feature-table thead th[data-col]').forEach(th => {
      th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (sortCol === col) sortDir *= -1;
        else { sortCol = col; sortDir = 1; }
        reorder(getRows().sort((a, b) => cmp(cellValue(a, col), cellValue(b, col)) * sortDir));
      });
    });

    document.getElementById('filter-status').addEventListener('change', applyFilters);
    document.getElementById('filter-release').addEventListener('change', applyFilters);

    tbody.addEventListener('click', e => {
      const row = e.target.closest('.feature-row');
      if (!row) return;
      const exp = document.getElementById(row.dataset.expand);
      if (!exp) return;
      exp.hidden = !exp.hidden;
      row.classList.toggle('open');
    });
  });
})();
"""


# pylint: disable=too-many-locals
def render_html(suites: list, features: Optional[dict] = None, favicon: str = "", link: str = "") -> str:
    """Render the full HTML report from a list of Suite objects."""
    total = sum(s.total for s in suites)
    passed_total = sum(s.passed for s in suites)
    failed_total = sum(s.failed for s in suites)
    skipped_total = sum(s.skipped for s in suites)
    duration_total = sum(s.duration for s in suites)

    def stat(value, label, modifier=""):
        return (
            f'<div class="stat">'
            f'<div class="stat-value {modifier}">{value}</div>'
            f'<div class="stat-label">{label}</div>'
            f"</div>"
        )

    header = (
        f'<div class="report-header">'
        f'<div class="header-logo"></div>'
        f'<div class="header-title"><h1>Test Report</h1>'
        f"<div>{_header_link_or_duration(link, duration_total)}</div>"
        f"</div>"
        f'{stat(total, "Total")}'
        f'{stat(passed_total, "Passed", "passed")}'
        f'{stat(failed_total, "Failed", "failed")}'
        f'{stat(skipped_total, "Skipped", "skipped")}'
        f"</div>"
    )

    if features:
        grouped = _group_by_features(suites, features)

        all_releases = sorted({features[fid].release for fid in grouped if fid in features and features[fid].release})

        rows_parts = []
        for i, (fid, fg) in enumerate(sorted(grouped.items())):
            all_tcs = [tc for _url, tcs in fg.suites.values() for tc in tcs]
            nfailed = sum(1 for tc in all_tcs if tc.status in (Status.FAILED, Status.ERROR))
            npassed = sum(1 for tc in all_tcs if tc.status == Status.PASSED)
            nskipped = sum(1 for tc in all_tcs if tc.status == Status.SKIPPED)
            fstatus = _feature_status(nfailed, npassed, nskipped)
            feat_release = features[fid].release if fid in features else "unspecified"

            icon = _FEATURE_STATUS_ICONS[fstatus]
            badge = f'<span class="badge {fstatus}">{icon} {fstatus}</span>'

            tc_with_url = [(tc, url) for _sname, (url, tcs) in fg.suites.items() for tc in tcs]
            tc_with_url.sort(key=lambda x: (_TC_STATUS_SORT.get(x[0].status, 99), x[0].classname, x[0].name))
            expanded = "".join(_render_testcase(tc, j, url) for j, (tc, url) in enumerate(tc_with_url))

            expand_id = f"exp{i}"
            failed_cls = " num-failed" if nfailed else ""
            passed_cls = " num-passed" if npassed else ""
            skipped_cls = " num-skipped" if nskipped else ""

            rows_parts.append(
                f'<tr class="feature-row"'
                f' data-status="{fstatus}"'
                f' data-release="{html.escape(feat_release, quote=True)}"'
                f' data-fid="{html.escape(fid, quote=True)}"'
                f' data-expand="{expand_id}"'
                f' data-failed="{nfailed}"'
                f' data-passed="{npassed}"'
                f' data-skipped="{nskipped}">'
                f"<td>{badge}</td>"
                f'<td class="col-fid">{html.escape(fid)}</td>'
                f'<td class="col-desc">{html.escape(fg.description)}</td>'
                f'<td class="col-release">{html.escape(feat_release)}</td>'
                f'<td class="col-num{failed_cls}">{nfailed}</td>'
                f'<td class="col-num{passed_cls}">{npassed}</td>'
                f'<td class="col-num{skipped_cls}">{nskipped}</td>'
                f"</tr>"
                f'<tr class="expand-row" id="{expand_id}" hidden>'
                f'<td colspan="7"><div class="expand-body">{expanded}</div></td>'
                f"</tr>"
            )

        rows_html = "".join(rows_parts)

        release_options = '<option value="">All releases</option>' + "".join(
            f'<option value="{html.escape(r, quote=True)}">{html.escape(r)}</option>' for r in all_releases
        )

        body = (
            f'<div class="controls">'
            f"<label>Status"
            f'<select id="filter-status">'
            f'<option value="">All</option>'
            f'<option value="failed">Failed</option>'
            f'<option value="passed">Passed</option>'
            f'<option value="skipped">Skipped</option>'
            f'<option value="untested">Untested</option>'
            f"</select></label>"
            f'<label>Release <select id="filter-release">{release_options}</select></label>'
            f"</div>"
            f'<div class="table-wrap">'
            f'<table class="feature-table" id="feature-table">'
            f"<thead><tr>"
            f'<th data-col="status">Status</th>'
            f'<th data-col="fid">Feature ID</th>'
            f'<th data-col="desc">Description</th>'
            f'<th data-col="release">Release</th>'
            f'<th data-col="failed" class="col-num">Failed</th>'
            f'<th data-col="passed" class="col-num">Passed</th>'
            f'<th data-col="skipped" class="col-num">Skipped</th>'
            f"</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
            f"</div>"
        )
    else:
        body = "<p>No features defined.</p>"

    favicon_tag = f"<link rel='icon' href='{html.escape(favicon)}'>" if favicon else ""
    css = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test Report</title>
{favicon_tag}
<style>
{css}
</style>
</head>
<body>
{header}
{body}
<script>{_REPORT_JS}</script>
</body>
</html>"""


def parse_dir(root: Path) -> list:
    """Return one Suite per immediate subdirectory of root, merging all XML files inside."""
    order_file = root / "_order.txt"
    if order_file.exists():
        order = [ln.strip() for ln in order_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        order = None

    subdirs = [p for p in root.iterdir() if p.is_dir()]
    if order:
        subdirs.sort(key=lambda p: order.index(p.name) if p.name in order else len(order))
    else:
        subdirs.sort()

    suites = []
    for subdir in subdirs:
        name = subdir.name.replace("_", " ")
        url_file = subdir / "_url.txt"
        url = url_file.read_text(encoding="utf-8").strip() if url_file.exists() else ""
        suite = Suite(name=name, url=url)
        for xml_path in sorted(subdir.glob("*.xml")):
            child = parse_xml(name, xml_path)
            suite.testcases.extend(child.testcases)
        if suite.testcases:
            suites.append(suite)
    return suites


def main():
    """Entry point: parse arguments and write the HTML report."""
    parser = argparse.ArgumentParser(description="Generate HTML report from XUnit XML files")
    parser.add_argument(
        "--dir",
        metavar="FOLDER",
        required=True,
        help="Root artifacts folder: each subfolder becomes a suite (underscores→spaces)",
    )
    parser.add_argument("-o", "--output", default="report.html", help="Output HTML file (default: report.html)")
    parser.add_argument(
        "--favicon", default="http://www.google.com/s2/favicons?domain=ocudu.org", metavar="URL", help="Favicon URL"
    )
    parser.add_argument("--link", default="", metavar="URL", help="Gitlab Link")
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        parser.error(f"Not a directory: {root}")
    suites = parse_dir(root)

    features: dict[str, FeatureDef] = {}
    with (Path(__file__).parent.parent / "features" / "features.yaml").open(encoding="utf-8") as f:
        features.update(_parse_features(yaml.safe_load(f)))

    output = Path(args.output)
    output.write_text(
        render_html(suites, features=features, favicon=args.favicon, link=args.link),
        encoding="utf-8",
    )
    total = sum(s.total for s in suites)
    failed = sum(s.failed for s in suites)
    print(f"Report written to {output}  ({total} tests, {failed} failed)")


if __name__ == "__main__":
    main()
