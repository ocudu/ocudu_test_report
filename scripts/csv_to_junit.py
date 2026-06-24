#!/usr/bin/env python3
"""Convert a Valor CSV test tracker export to JUnit XML format."""

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom


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


def csv_to_junit(csv_path: Path, output_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    total = len(rows)
    failures = sum(1 for r in rows if result_to_outcome(r.get("Result", "")) == "fail")
    skipped = sum(1 for r in rows if result_to_outcome(r.get("Result", "")) == "skip")
    errors = 0

    testsuites = ET.Element("testsuites", name="TIFG tests")
    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        name="TIFG",
        errors=str(errors),
        failures=str(failures),
        skipped=str(skipped),
        tests=str(total),
        timestamp=now,
    )

    for row in rows:
        test_id = row.get("Test ID", "").strip()
        test_name = row.get("Test Name", "").strip()
        sub_test = row.get("Sub-Test", "").strip()
        radio_condition = row.get("Radio Condition", "").strip()
        dut = row.get("DUT", "").strip()
        priority = row.get("Priority", "").strip()
        execution_date = parse_date(row.get("Execution Date", ""))
        result = row.get("Result", "").strip()
        comments = row.get("Comments", "").strip()

        classname = f"{test_name}.{sub_test}" if sub_test else test_name

        tc_attrs: dict[str, str] = {
            "name": test_id,
            "classname": classname,
        }
        if execution_date:
            tc_attrs["timestamp"] = execution_date

        testcase = ET.SubElement(testsuite, "testcase", attrib=tc_attrs)

        props = ET.SubElement(testcase, "properties")
        for prop_name, prop_value in [
            ("Radio Condition", radio_condition),
            ("DUT", dut),
            ("Priority", priority),
            ("Comments", comments),
        ]:
            ET.SubElement(props, "property", name=prop_name, value=prop_value)

        outcome = result_to_outcome(result)
        if outcome == "fail":
            ET.SubElement(testcase, "failure", message=f"Test {test_id} failed", type="AssertionError")
        elif outcome == "skip":
            ET.SubElement(testcase, "skipped", message=f"Test {test_id} skipped")

        ET.SubElement(testcase, "system-out")
        ET.SubElement(testcase, "system-err")

    xml_str = minidom.parseString(ET.tostring(testsuites, encoding="unicode")).toprettyxml(indent="  ")
    # Remove the extra XML declaration added by toprettyxml since we prepend our own
    lines = xml_str.splitlines()
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="utf-8"?>'
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Written {total} test cases to {output_path}")
    print(f"  passed={total - failures - skipped}, failed={failures}, skipped={skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Valor CSV to JUnit XML")
    parser.add_argument("-i", "--input", required=True, type=Path, metavar="CSV", help="Input CSV file")
    parser.add_argument("-o", "--output", type=Path, metavar="XML", help="Output XML file (default: <input_stem>.xml)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    output = args.output or args.input.with_suffix(".xml")
    csv_to_junit(args.input, output)


if __name__ == "__main__":
    main()
