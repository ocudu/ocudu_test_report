#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
XUnit HTML reporter — aggregates multiple XUnit XML files into a single HTML report.

Usage:
    python report.py --suite "CTest=ctest.xml" --suite "E2E=e2e.xml" -o report.html
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


def _render_testcase(tc: TestCase, idx: int) -> str:
    parity = "even" if idx % 2 == 0 else "odd"
    label = f"{html.escape(tc.classname)}." if tc.classname else ""
    header = (
        f'<span class="tc-name">{label}<b>{html.escape(tc.name)}</b></span>'
        f'<span class="tc-duration">{_fmt_duration(tc.duration)}</span>'
        f"{_status_badge(tc.status)}"
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


def _render_suite(name: str, testcases: list, url: str = "", description: str = "") -> str:
    total = len(testcases)
    passed = sum(1 for tc in testcases if tc.status == Status.PASSED)
    failed = sum(1 for tc in testcases if tc.status in (Status.FAILED, Status.ERROR))
    skipped = sum(1 for tc in testcases if tc.status == Status.SKIPPED)
    duration = sum(tc.duration for tc in testcases)

    fail_class = "fail" if (failed or passed == 0) else ""
    counts = f"✓ {passed}/{total} passed"
    if failed:
        counts += f' &nbsp; <span class="count-failed">✗ {failed} failed</span>'
    if skipped:
        counts += f' &nbsp; <span class="count-skipped">⊘ {skipped} skipped</span>'

    link_html = (
        (
            f'<a class="suite-link" href="{html.escape(url)}" target="_blank" title="{html.escape(url)}">'
            f'<img src="https://about.gitlab.com/images/press/gitlab-logo-500-rgb.svg" alt="GitLab" height="26">'
            f"</a>"
        )
        if url
        else ""
    )
    desc_html = f'<span class="suite-desc">{html.escape(description)}</span>' if description else ""
    summary = (
        f'<summary class="suite-summary {fail_class}">'
        f'<span class="suite-name">{html.escape(name)}</span>'
        f"{desc_html}"
        f'<span class="suite-counts">{counts} &nbsp; ⏱ {_fmt_duration(duration)}</span>'
        f"{link_html}"
        f"</summary>"
    )
    rows = "".join(
        _render_testcase(tc, i) for i, tc in enumerate(sorted(testcases, key=lambda tc: f"{tc.classname}.{tc.name}"))
    )
    return f'<details class="suite">{summary}{rows}</details>'


def _render_feature(fid: str, description: str, suites: dict) -> str:
    all_tcs = [tc for _url, tcs in suites.values() for tc in tcs]
    total = len(all_tcs)
    passed = sum(1 for tc in all_tcs if tc.status == Status.PASSED)
    failed = sum(1 for tc in all_tcs if tc.status in (Status.FAILED, Status.ERROR))
    skipped = sum(1 for tc in all_tcs if tc.status == Status.SKIPPED)
    duration = sum(tc.duration for tc in all_tcs)

    fail_class = "fail" if (failed or passed == 0) else ""
    counts = f"✓ {passed}/{total} passed"
    if failed:
        counts += f' &nbsp; <span class="count-failed">✗ {failed} failed</span>'
    if skipped:
        counts += f' &nbsp; <span class="count-skipped">⊘ {skipped} skipped</span>'

    desc_html = f'<span class="feature-desc">{html.escape(description)}</span>' if description else ""
    summary = (
        f'<summary class="feature-summary {fail_class}">'
        f'<span class="feature-title"><span class="feature-id">{html.escape(fid)}</span>{desc_html}</span>'
        f'<span class="feature-counts">{counts} &nbsp; ⏱ {_fmt_duration(duration)}</span>'
        f"</summary>"
    )
    suite_blocks = "".join(_render_suite(name, tcs, url) for name, (url, tcs) in sorted(suites.items()))
    return f'<details class="feature">{summary}{suite_blocks}</details>'


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


@dataclass
class SuiteGroup:
    """A suite with its test cases grouped by feature (for suites-first layout)."""

    url: str
    features: dict = field(default_factory=dict)  # {feature_name: (description, [TestCase])}


def _group_by_suites(suites: list, features: dict[str, FeatureDef]) -> dict[str, SuiteGroup]:
    """Return {suite_name: SuiteGroup}, tests with no matching label go under Others.

    features must already be parsed by _parse_features.
    """
    alias_map = {alias: name for name, fd in features.items() for alias in fd.labels}
    feat_desc = {name: fd.description for name, fd in features.items()}

    grouped: dict[str, SuiteGroup] = {}
    for suite in suites:
        sg = SuiteGroup(url=suite.url)
        for tc in suite.testcases:
            matched = list(dict.fromkeys(alias_map[lbl] for lbl in tc.labels if lbl in alias_map))
            for fid in matched or [OTHER_CATEGORY]:
                if fid not in sg.features:
                    desc = feat_desc.get(fid, OTHER_CATEGORY_DESCRIPTION)
                    sg.features[fid] = (desc, [])
                sg.features[fid][1].append(tc)
        if sg.features:
            grouped[suite.name] = sg
    return grouped


def _render_suite_toplevel(suite_name: str, sg: SuiteGroup) -> str:
    """Render a suite as the top level with features nested inside (suites-first layout)."""
    all_tcs = [tc for _desc, tcs in sg.features.values() for tc in tcs]
    total = len(all_tcs)
    passed = sum(1 for tc in all_tcs if tc.status == Status.PASSED)
    failed = sum(1 for tc in all_tcs if tc.status in (Status.FAILED, Status.ERROR))
    skipped = sum(1 for tc in all_tcs if tc.status == Status.SKIPPED)
    duration = sum(tc.duration for tc in all_tcs)

    fail_class = "fail" if failed else ""
    counts = f"✓ {passed}/{total} passed"
    if failed:
        counts += f' &nbsp; <span class="count-failed">✗ {failed} failed</span>'
    if skipped:
        counts += f' &nbsp; <span class="count-skipped">⊘ {skipped} skipped</span>'

    link_html = (
        (
            f'<a class="suite-link" href="{html.escape(sg.url)}" target="_blank" title="{html.escape(sg.url)}">'
            f'<img src="https://about.gitlab.com/images/press/gitlab-logo-500-rgb.svg" alt="GitLab" height="26">'
            f"</a>"
        )
        if sg.url
        else ""
    )
    summary = (
        f'<summary class="feature-summary {fail_class}">'
        f'<span class="feature-title"><span class="feature-id">{html.escape(suite_name)}</span></span>'
        f'<span class="feature-counts">{counts} &nbsp; ⏱ {_fmt_duration(duration)}</span>'
        f"{link_html}"
        f"</summary>"
    )
    feature_blocks = "".join(
        _render_suite(fid, tcs, description=desc) for fid, (desc, tcs) in sorted(sg.features.items())
    )
    return f'<details class="feature">{summary}{feature_blocks}</details>'


def _group_by_features(
    suites: list, features: dict[str, FeatureDef], always_keep: Optional[set] = None
) -> dict[str, FeatureGroup]:
    """Return {display_name: FeatureGroup}, tests with no matching label go under Others.

    features must already be parsed by _parse_features.
    always_keep: set of feature IDs to include even if they have no tests.
    Features not in always_keep only appear when they have at least one test.
    Others only appears when it has tests.
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

    if always_keep is not None:
        return {fid: fg for fid, fg in grouped.items() if fid in always_keep or fg.suites}
    return {fid: fg for fid, fg in grouped.items() if fg.suites}


def _header_link_or_duration(link: str, duration: float) -> str:
    """Return a GitLab link or a formatted duration for the report header."""
    if link:
        return f"<a class='header-link' href='{html.escape(link)}'>{link.split('/')[-1]}</a>"
    return f"⏱ {_fmt_duration(duration)}"


# pylint: disable=too-many-locals
def render_html(
    suites: list, features: Optional[dict] = None, favicon: str = "", link: str = "", release: str = ""
) -> str:
    """Render the full HTML report from a list of Suite objects."""
    total = sum(s.total for s in suites)
    passed = sum(s.passed for s in suites)
    failed = sum(s.failed for s in suites)
    skipped = sum(s.skipped for s in suites)
    duration = sum(s.duration for s in suites)

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
        f"<div>"
        f"{_header_link_or_duration(link, duration)}"
        f"</div></div>"
        f'{stat(total, "Total")}'
        f'{stat(passed, "Passed", "passed")}'
        f'{stat(failed, "Failed", "failed")}'
        f'{stat(skipped, "Skipped", "skipped")}'
        f"</div>"
    )

    if release and features:
        release_ids = {name for name, fd in features.items() if fd.release == release}
        grouped = _group_by_features(suites, features, always_keep=release_ids)
        body = "".join(_render_feature(fid, fg.description, fg.suites) for fid, fg in sorted(grouped.items()))
    elif features:
        by_suite = _group_by_suites(suites, features)
        body = "".join(_render_suite_toplevel(s.name, by_suite[s.name]) for s in suites if s.name in by_suite)
    else:
        body = "".join(_render_suite(s.name, s.testcases, s.url) for s in suites)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test Report</title>
{"<link rel='icon' href='" + html.escape(favicon) + "'>" if favicon else ""}
<style>
{(Path(__file__).parent / "style.css").read_text(encoding="utf-8")}
</style>
</head>
<body>
{header}
{body}
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
    parser.add_argument(
        "--release",
        default="",
        metavar="RELEASE",
        help="Show all features with this release value (e.g. '26.04 (v1.0)') plus an 'others' group. "
        "If not specified, uses suites layout.",
    )
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        parser.error(f"Not a directory: {root}")
    suites = parse_dir(root)

    features_yaml: dict[str, FeatureDef] = {}
    with (Path(__file__).parent.parent / "features" / "features.yaml").open(encoding="utf-8") as f:
        features_yaml.update(_parse_features(yaml.safe_load(f)))
    levels: dict[str, FeatureDef] = {}
    with (Path(__file__).parent / "levels.yaml").open(encoding="utf-8") as f:
        levels.update(_parse_features(yaml.safe_load(f)))

    # In release mode only features.yaml entries (filtered by release) are feature groups;
    # levels and other releases feed into "others". In suites mode all definitions are used.
    features = features_yaml if args.release else {**features_yaml, **levels}

    output = Path(args.output)
    output.write_text(
        render_html(suites, features=features, favicon=args.favicon, link=args.link, release=args.release),
        encoding="utf-8",
    )
    total = sum(s.total for s in suites)
    failed = sum(s.failed for s in suites)

    if args.release:
        release_ids = {name for name, fd in features.items() if fd.release == args.release}
        grouped = _group_by_features(suites, features, always_keep=release_ids)
        failed_features = []
        for fid, fg in sorted(grouped.items()):
            all_tcs = [tc for _url, tcs in fg.suites.values() for tc in tcs]
            nfailed = sum(1 for tc in all_tcs if tc.status in (Status.FAILED, Status.ERROR))
            npassed = sum(1 for tc in all_tcs if tc.status == Status.PASSED)
            nskipped = sum(1 for tc in all_tcs if tc.status == Status.SKIPPED)
            if nfailed or npassed == 0:
                failed_features.append((fid, nfailed, npassed, nskipped))
        if failed_features:
            print("")
            print(f"# Failed Features for {args.release}")
            print("| Feature | Failed | Passed | Skipped |")
            print("| --- | --- | --- | --- |")
            for fid, nfailed, npassed, nskipped in failed_features:
                print(f"| {fid} | {nfailed} | {npassed} | {nskipped} |")
            print("")

    print(f"Report written to {output}  ({total} tests, {failed} failed)")


if __name__ == "__main__":
    main()
