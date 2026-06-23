#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
XUnit HTML reporter — aggregates multiple XUnit XML files into a single HTML report.

Usage:
    python xunit_report.py --dir FOLDER -o ./report/
"""

import argparse
import html
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Union

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


class Status(Enum):
    """Test result status."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


_TC_STATUS_SORT = {Status.SKIPPED: 0, Status.FAILED: 1, Status.ERROR: 1, Status.PASSED: 2}
_STATUS_ICONS = {"passed": "✓", "failed": "✗", "partial": "!", "skipped": "⊘", "untested": "—"}

_MS_ACTIONS = (
    '<div class="ms-actions">'
    '<button type="button" class="ms-action-btn" data-action="all">All</button>'
    '<button type="button" class="ms-action-btn" data-action="none">None</button>'
    "</div>"
)

_STATUS_VALUES = [
    ("failed", "Failed"),
    ("partial", "Partial"),
    ("passed", "Passed"),
    ("skipped", "Skipped"),
    ("untested", "Untested"),
]
_TC_STATUS_VALUES = [("failed", "Failed"), ("passed", "Passed"), ("skipped", "Skipped"), ("untested", "Untested")]


def _status_checkboxes(defaults: Optional[frozenset[str]] = None, values=None) -> str:
    vals = values if values is not None else _STATUS_VALUES
    return _MS_ACTIONS + "".join(
        f'<label class="ms-item"><input type="checkbox" value="{val}"'
        f'{" checked" if defaults is None or val in defaults else ""}>'
        f"<span>{label}</span></label>"
        for val, label in vals
    )


_GITLAB_LOGO = "https://about.gitlab.com/images/press/gitlab-logo-500-rgb.svg"
_SCRIPTS_DIR = Path(__file__).parent


def _read_asset(name: str) -> str:
    return (_SCRIPTS_DIR / name).read_text(encoding="utf-8")


def _stat_html(label: str, modifier: str = "") -> str:
    sid = modifier or "total"
    return (
        f'<div class="stat">'
        f'<div class="stat-value {modifier}" id="stat-{sid}">0</div>'
        f'<div class="stat-label">{label}</div>'
        f"</div>"
    )


def _clean_output(text: str) -> str:
    """Strip capture headers and convert ANSI escape codes to HTML."""
    text = CAPTURE_HEADER_RE.sub("", text)
    text = text.replace("#x1B", "\x1b")  # pytest XML writer drops the & from &#x1B;
    result: str = _ANSI_CONVERTER.convert(text.strip(), full=False)
    return result


@dataclass
class TestCase:
    """Holds data for a single test case parsed from an XUnit XML file."""

    # pylint: disable=too-many-instance-attributes
    name: str
    classname: str
    duration: float
    status: Status
    message: str = ""
    system_out: str = ""
    system_err: str = ""
    labels: list[str] = field(default_factory=list)
    url: str = ""


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


def _status_badge(status: Union[Status, str]) -> str:
    key = status.value if isinstance(status, Status) else status
    return f'<span class="badge {key}">{_STATUS_ICONS.get(key, "?")} {key}</span>'


def _gitlab_link(url: str, title: str = "GitLab") -> str:
    if not url:
        return ""
    return (
        f'<a class="tc-gitlab-link" href="{html.escape(url)}" target="_blank"'
        f' title="{html.escape(title)}" onclick="event.stopPropagation()">'
        f'<img src="{_GITLAB_LOGO}" alt="GitLab" height="20"></a>'
    )


def _render_testcase(tc: TestCase, idx: int) -> str:
    parity = "even" if idx % 2 == 0 else "odd"
    label = f"{html.escape(tc.classname)}." if tc.classname else ""
    display_status = Status.FAILED if tc.status == Status.ERROR else tc.status

    header = (
        f"{_status_badge(display_status)}"
        f'<span class="tc-name">{label}<b>{html.escape(tc.name)}</b></span>'
        f"{_gitlab_link(tc.url, 'GitLab pipeline')}"
        f'<span class="tc-duration">{_fmt_duration(tc.duration)}</span>'
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
            f'<details class="tc-detail {parity}" data-status="{display_status.value}">'
            f'<summary class="tc-row {parity}">{header}</summary>'
            f'<div class="tc-detail-body">{detail_body}</div>'
            f"</details>"
        )

    return f'<div class="tc-row {parity}" data-status="{display_status.value}">{header}</div>'


@dataclass
class FeatureDef:
    """A feature entry parsed from features.yaml."""

    description: str
    labels: set = field(default_factory=set)
    release: str = ""
    type: str = ""
    scope: str = ""


@dataclass
class FeatureGroup:
    """A feature with its matched test cases grouped by suite."""

    description: str
    suites: dict = field(default_factory=dict)  # {suite_name: (url, [TestCase])}


@dataclass
class FilterDefaults:
    """Pre-selected filter values for the HTML report dropdowns."""

    statuses: Optional[list[str]] = None
    scopes: Optional[list[str]] = None
    types: Optional[list[str]] = None
    releases: Optional[list[str]] = None


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
        result[parts[0]] = FeatureDef(
            description=description or "",
            labels=set(parts),
            release=item.get("release", ""),
            type=item.get("type", ""),
            scope=item.get("scope", ""),
        )
    return result


def _group_by_features(suites: list, features: dict[str, FeatureDef]) -> dict[str, FeatureGroup]:
    """Return {display_name: FeatureGroup}.

    All defined features are always included (untested ones show with zero counts).
    Tests with no matching feature label are silently dropped.
    """
    alias_map = {alias: name for name, fd in features.items() for alias in fd.labels}
    grouped: dict[str, FeatureGroup] = {name: FeatureGroup(description=fd.description) for name, fd in features.items()}

    for suite in suites:
        for tc in suite.testcases:
            matched = list(dict.fromkeys(alias_map[lbl] for lbl in tc.labels if lbl in alias_map))
            for fid in matched:
                if suite.name not in grouped[fid].suites:
                    grouped[fid].suites[suite.name] = (suite.url, [])
                grouped[fid].suites[suite.name][1].append(tc)

    return grouped


def _header_subtitle(link: str, duration: float) -> str:
    duration_html = f"⏱ {_fmt_duration(duration)}"
    if not link:
        return duration_html
    link_html = f"<a class='header-link' href='{html.escape(link)}'>{link.split('/')[-1]}</a>"
    return f"{link_html} · {duration_html}"


def _feature_status(failed: int, passed: int) -> str:
    total = failed + passed
    if total == 0:
        return "untested"
    if failed == 0:
        return "passed"
    if failed / total > 0.5:
        return "failed"
    return "partial"


def _report_header(title: str, link: str, duration: float) -> str:
    return (
        '<div class="report-header">'
        '<div class="header-logo"></div>'
        f'<div class="header-title"><h1>{title}</h1>'
        f"<div>{_header_subtitle(link, duration)}</div>"
        "</div>"
        f'{_stat_html("Total")}'
        f'{_stat_html("Failed", "failed")}'
        f'{_stat_html("Passed", "passed")}'
        "</div>"
    )


def _html_doc(title: str, favicon: str, preamble: str, body: str, js_name: str) -> str:
    favicon_tag = f"<link rel='icon' href='{html.escape(favicon)}'>" if favicon else ""
    css = _read_asset("style.css")
    js = _read_asset(js_name)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{favicon_tag}
<style>
{css}
</style>
</head>
<body>
{preamble}
{body}
<script>{js}</script>
</body>
</html>"""


def render_html(
    suites: list,
    features: Optional[dict] = None,
    favicon: str = "",
    link: str = "",
    defaults: Optional[FilterDefaults] = None,
) -> str:
    """Render the full HTML report from a list of Suite objects."""
    # pylint: disable=too-many-locals
    duration_total = sum(s.duration for s in suites)
    default_statuses = frozenset(defaults.statuses) if defaults and defaults.statuses else None
    default_scopes = frozenset(defaults.scopes) if defaults and defaults.scopes else None
    default_types = frozenset(defaults.types) if defaults and defaults.types else None
    default_releases = frozenset(defaults.releases) if defaults and defaults.releases else None

    if features:
        grouped = _group_by_features(suites, features)

        all_releases = sorted({features[fid].release for fid in grouped if fid in features and features[fid].release})
        release_checkboxes = _MS_ACTIONS + "".join(
            f'<label class="ms-item"><input type="checkbox" value="{html.escape(r, quote=True)}"'
            f'{" checked" if default_releases is None or r in default_releases else ""}>'
            f"<span>{html.escape(r)}</span></label>"
            for r in all_releases
        )

        all_types = sorted({features[fid].type for fid in grouped if fid in features and features[fid].type})
        type_checkboxes = _MS_ACTIONS + "".join(
            f'<label class="ms-item"><input type="checkbox" value="{html.escape(t, quote=True)}"'
            f'{" checked" if default_types is None or t in default_types else ""}>'
            f"<span>{html.escape(t)}</span></label>"
            for t in all_types
        )

        all_scopes = sorted({features[fid].scope for fid in grouped if fid in features and features[fid].scope})
        scope_checkboxes = _MS_ACTIONS + "".join(
            f'<label class="ms-item"><input type="checkbox" value="{html.escape(s, quote=True)}"'
            f'{" checked" if default_scopes is None or s in default_scopes else ""}>'
            f"<span>{html.escape(s)}</span></label>"
            for s in all_scopes
        )

        rows_parts = []
        for i, (fid, fg) in enumerate(grouped.items()):
            all_tcs = [tc for _, tcs in fg.suites.values() for tc in tcs]
            nfailed = sum(1 for tc in all_tcs if tc.status in (Status.FAILED, Status.ERROR, Status.SKIPPED))
            npassed = sum(1 for tc in all_tcs if tc.status == Status.PASSED)
            fstatus = _feature_status(nfailed, npassed)
            feat_release = features[fid].release if fid in features else "unspecified"
            feat_type = features[fid].type if fid in features else ""
            feat_scope = features[fid].scope if fid in features else ""

            badge = _status_badge(fstatus)
            all_tcs.sort(key=lambda tc: (_TC_STATUS_SORT.get(tc.status, 99), tc.classname, tc.name))
            expanded = "".join(_render_testcase(tc, j) for j, tc in enumerate(all_tcs))

            expand_id = f"exp{i}"
            failed_cls = " num-failed" if nfailed else ""
            passed_cls = " num-passed" if npassed else ""

            expand_attr = f' data-expand="{expand_id}"' if expanded else ""
            expand_row = (
                (
                    f'<tr class="expand-row" id="{expand_id}" hidden>'
                    f'<td colspan="6"><div class="expand-body">{expanded}</div></td>'
                    f"</tr>"
                )
                if expanded
                else ""
            )
            rows_parts.append(
                f'<tr class="feature-row"'
                f' data-status="{fstatus}"'
                f' data-release="{html.escape(feat_release, quote=True)}"'
                f' data-type="{html.escape(feat_type, quote=True)}"'
                f' data-scope="{html.escape(feat_scope, quote=True)}"'
                f' data-fid="{html.escape(fid, quote=True)}"'
                f"{expand_attr}"
                f' data-failed="{nfailed}"'
                f' data-passed="{npassed}">'
                f'<td class="col-fid">{html.escape(fid)}</td>'
                f"<td>{badge}</td>"
                f'<td class="col-desc">{html.escape(fg.description)}</td>'
                f'<td class="col-release">{html.escape(feat_release)}</td>'
                f'<td class="col-num{failed_cls}">{nfailed}</td>'
                f'<td class="col-num{passed_cls}">{npassed}</td>'
                f"</tr>"
                f"{expand_row}"
            )

        rows_html = "".join(rows_parts)

        body = (
            f'<div class="controls">'
            f'<div class="ms-wrap" id="ms-status">'
            f'<button type="button" class="ms-btn">Status: <span class="ms-label">All</span></button>'
            f'<div class="ms-panel" hidden>{_status_checkboxes(default_statuses)}</div>'
            f"</div>"
            f'<div class="ms-wrap" id="ms-scope">'
            f'<button type="button" class="ms-btn">Scope: <span class="ms-label">All</span></button>'
            f'<div class="ms-panel" hidden>{scope_checkboxes}</div>'
            f"</div>"
            f'<div class="ms-wrap" id="ms-type">'
            f'<button type="button" class="ms-btn">Type: <span class="ms-label">All</span></button>'
            f'<div class="ms-panel" hidden>{type_checkboxes}</div>'
            f"</div>"
            f'<div class="ms-wrap" id="ms-release">'
            f'<button type="button" class="ms-btn">Release: <span class="ms-label">All</span></button>'
            f'<div class="ms-panel" hidden>{release_checkboxes}</div>'
            f"</div>"
            f"</div>"
            f'<div class="table-wrap">'
            f'<table class="feature-table" id="feature-table">'
            f"<thead><tr>"
            f'<th data-col="fid">Feature ID</th>'
            f'<th data-col="status">Status</th>'
            f'<th data-col="desc">Description</th>'
            f'<th data-col="release">Release</th>'
            f'<th data-col="failed" class="col-num">F</th>'
            f'<th data-col="passed" class="col-num">P</th>'
            f"</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
            f"</div>"
        )
    else:
        body = "<p>No features defined.</p>"

    header = _report_header("Results", link, duration_total)
    return _html_doc("Results", favicon, header, body, "report.js")


def render_all_html(suites: list, favicon: str = "", link: str = "") -> str:
    """Render the all-tests HTML report: one accordion per suite, tests inside."""
    # pylint: disable=too-many-locals
    duration_total = sum(s.duration for s in suites)

    suite_checkboxes = _MS_ACTIONS + "".join(
        f'<label class="ms-item">'
        f'<input type="checkbox" value="{html.escape(s.name, quote=True)}" checked>'
        f"<span>{html.escape(s.name)}</span></label>"
        for s in suites
    )

    controls = (
        f'<div class="controls">'
        f'<div class="ms-wrap" id="ms-status">'
        f'<button type="button" class="ms-btn">Status: <span class="ms-label">All</span></button>'
        f'<div class="ms-panel" hidden>{_status_checkboxes(values=_TC_STATUS_VALUES)}</div>'
        f"</div>"
        f'<div class="ms-wrap" id="ms-suite">'
        f'<button type="button" class="ms-btn">Suite: <span class="ms-label">All</span></button>'
        f'<div class="ms-panel" hidden>{suite_checkboxes}</div>'
        f"</div>"
        f"</div>"
    )

    rows_parts = []
    for i, suite in enumerate(suites):
        nfailed = suite.failed + suite.skipped
        npassed = suite.passed
        fstatus = _feature_status(nfailed, npassed)
        badge = _status_badge(fstatus)

        tcs = sorted(suite.testcases, key=lambda tc: (_TC_STATUS_SORT.get(tc.status, 99), tc.classname, tc.name))
        expanded = "".join(_render_testcase(tc, j) for j, tc in enumerate(tcs))

        expand_id = f"sexp{i}"
        failed_cls = " num-failed" if nfailed else ""
        passed_cls = " num-passed" if npassed else ""

        rows_parts.append(
            f'<tr class="suite-row" data-suite="{html.escape(suite.name, quote=True)}" data-expand="{expand_id}">'
            f'<td class="suite-name-cell">{badge}'
            f'<span class="suite-name-text">{html.escape(suite.name)}</span>'
            f"{_gitlab_link(suite.url)}</td>"
            f'<td class="col-num{failed_cls}">{nfailed}</td>'
            f'<td class="col-num{passed_cls}">{npassed}</td>'
            f"</tr>"
            f'<tr class="expand-row" id="{expand_id}" hidden>'
            f'<td colspan="3"><div class="expand-body">{expanded}</div></td>'
            f"</tr>"
        )

    rows_html = "".join(rows_parts)

    body = (
        f"{controls}"
        f'<div class="table-wrap">'
        f'<table class="feature-table" id="suite-table">'
        f"<thead><tr>"
        f"<th>Suite</th>"
        f'<th class="col-num">F</th>'
        f'<th class="col-num">P</th>'
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>"
        f"</div>"
    )

    header = _report_header("All test suites", link, duration_total)
    return _html_doc("All test suites", favicon, header, body, "all.js")


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
            job_url_file = xml_path.with_name(xml_path.stem + "_url.txt")
            job_url = job_url_file.read_text(encoding="utf-8").strip() if job_url_file.exists() else url
            child = parse_xml(name, xml_path)
            for tc in child.testcases:
                tc.url = job_url
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
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("report"),
        help="Output directory — writes index.html and all.html (default: ./report/)",
    )
    parser.add_argument(
        "--favicon", default="http://www.google.com/s2/favicons?domain=ocudu.org", metavar="URL", help="Favicon URL"
    )
    parser.add_argument("--link", default="", metavar="URL", help="Gitlab Link")
    parser.add_argument(
        "--status",
        nargs="+",
        metavar="STATUS",
        default=None,
        choices=["failed", "passed", "skipped", "untested"],
        help="Pre-select status filter",
    )
    parser.add_argument(
        "--scope",
        nargs="+",
        metavar="SCOPE",
        default=None,
        help="Pre-select scope filter (space-separate multiple values)",
    )
    parser.add_argument(
        "--type",
        nargs="+",
        metavar="TYPE",
        default=None,
        help="Pre-select type filter (space-separate multiple values)",
    )
    parser.add_argument(
        "--release",
        nargs="+",
        metavar="RELEASE",
        default=None,
        help="Pre-select release filter (space-separate multiple values)",
    )
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        parser.error(f"Not a directory: {root}")
    suites = parse_dir(root)

    features: dict[str, FeatureDef] = {}
    with (Path(__file__).parent.parent / "features" / "features.yaml").open(encoding="utf-8") as f:
        features.update(_parse_features(yaml.safe_load(f)))

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "report.html").write_text(
        render_html(
            suites,
            features=features,
            favicon=args.favicon,
            link=args.link,
            defaults=FilterDefaults(
                statuses=args.status,
                scopes=args.scope,
                types=args.type,
                releases=args.release,
            ),
        ),
        encoding="utf-8",
    )
    (out_dir / "all.html").write_text(
        render_all_html(suites, favicon=args.favicon, link=args.link),
        encoding="utf-8",
    )

    print(f"report.html + all.html written to {out_dir}/")


if __name__ == "__main__":
    main()
