#!/usr/bin/env python3
"""Convert a Valor CSV test tracker export to JUnit XML format."""

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET


def parse_date(date_str: str) -> str:
    """Parse a date string and return ISO 8601 format, or empty string if unparseable."""
    if not date_str.strip():
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return date_str.strip()


def result_to_outcome(result: str) -> str:
    """Normalize result string to 'pass', 'fail', or 'skip'."""
    r = result.strip().lower()
    if r in ("pass", "passed"):
        return "pass"
    if r in ("fail", "failed", "error"):
        return "fail"
    return "skip"


_CORE_COLUMNS = ("Test ID", "Test Name", "Sub-Test", "Execution Date", "Result")


def _sniff_dialect(sample: str) -> type[csv.Dialect]:
    """Detect whether a CSV sample uses comma or semicolon as the delimiter."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        return csv.excel


def _add_testcase(testsuite: ET.Element, row: dict[str, str], extra_columns: list[str]) -> None:
    """Append a single testcase element built from a CSV row to testsuite."""
    test_id = row.get("Test ID", "").strip()
    test_name = " ".join(row.get("Test Name", "").split())
    sub_test = row.get("Sub-Test", "").strip()
    execution_date = parse_date(row.get("Execution Date", ""))
    result = row.get("Result", "").strip()

    classname = f"{test_name}.{sub_test}" if sub_test else test_name
    tc_attrs: dict[str, str] = {"name": test_id, "classname": classname}
    if execution_date:
        tc_attrs["timestamp"] = execution_date

    testcase = ET.SubElement(testsuite, "testcase", attrib=tc_attrs)

    props = ET.SubElement(testcase, "properties")
    for column in extra_columns:
        ET.SubElement(props, "property", name=column, value=row.get(column, "").strip())

    outcome = result_to_outcome(result)
    if outcome == "fail":
        ET.SubElement(testcase, "failure", message=f"Test {test_id} failed", type="AssertionError")
    elif outcome == "skip":
        ET.SubElement(testcase, "skipped", message=f"Test {test_id} skipped")

    ET.SubElement(testcase, "system-out")
    ET.SubElement(testcase, "system-err")


def _read_rows(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Read CSV rows, auto-detecting the delimiter, and list columns beyond the core ones."""
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        dialect = _sniff_dialect(f.read(4096))
        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)
        rows: list[dict[str, str]] = list(reader)
        extra_columns = [c for c in (reader.fieldnames or []) if c not in _CORE_COLUMNS]
    return rows, extra_columns


def csv_to_junit(csv_path: Path, output_path: Path, suite_name: str) -> None:
    """Convert a CSV tracker file to a JUnit XML file."""
    now = datetime.now(timezone.utc).isoformat()

    rows, extra_columns = _read_rows(csv_path)
    total = len(rows)
    failures = sum(1 for r in rows if result_to_outcome(r.get("Result", "")) == "fail")
    skipped = sum(1 for r in rows if result_to_outcome(r.get("Result", "")) == "skip")

    testsuites = ET.Element("testsuites", name=f"{suite_name} tests")
    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        name=suite_name,
        errors="0",
        failures=str(failures),
        skipped=str(skipped),
        tests=str(total),
        timestamp=now,
    )

    for row in rows:
        _add_testcase(testsuite, row, extra_columns)

    xml_str = minidom.parseString(ET.tostring(testsuites, encoding="unicode")).toprettyxml(indent="  ")
    # toprettyxml adds its own declaration; replace it to fix the encoding attribute
    lines = xml_str.splitlines()
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="utf-8"?>'
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Written {total} test cases to {output_path}")
    print(f"  passed={total - failures - skipped}, failed={failures}, skipped={skipped}")


def main() -> None:
    """Parse arguments and run the conversion."""
    parser = argparse.ArgumentParser(description="Convert Valor CSV to JUnit XML")
    parser.add_argument("-i", "--input", required=True, type=Path, metavar="CSV", help="Input CSV file")
    parser.add_argument("-o", "--output", type=Path, metavar="XML", help="Output XML file (default: <input_stem>.xml)")
    parser.add_argument("--suite-name", required=True, metavar="NAME", help="Test suite name (e.g. TIFG, WG11)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    output = args.output or args.input.with_suffix(".xml")
    csv_to_junit(args.input, output, args.suite_name)


if __name__ == "__main__":
    main()
