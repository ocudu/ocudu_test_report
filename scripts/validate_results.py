#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Validate JUnit XML result files against schemas/results.schema.yaml.

Every lab (OCUDU CI included) pushes JUnit XML results to the report. Each
<testsuite> must say which lab produced it and which OCUDU commit it tested, as
<property> entries. XSD cannot require a property with a given name, so this
script turns the XML into a plain dict and checks that against a JSON Schema,
then runs the checks a schema cannot express:

  * the lab exists in labs/labs.yaml (and matches --lab, if given);
  * the upload format version is one this tool understands;
  * every <testsuite> in a file names the same lab and commit;
  * required properties are not given twice with different values.

The same checks run in the push tool before uploading and again at ingest,
because uploads cannot be trusted. Errors are returned as lists of strings so
ingest can report a bad file and carry on with the rest.

Usage:
  validate_results.py results/*.xml
  validate_results.py --lab valor results/*.xml

Exit codes:
  0  - every file is valid
  1  - at least one file failed validation
  2  - usage / setup error (schema or labs file missing or unreadable)
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    from jsonschema import Draft7Validator
except ImportError:
    print("ERROR: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)


_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA_FILE = _REPO_ROOT / "schemas" / "results.schema.yaml"
DEFAULT_LABS_FILE = _REPO_ROOT / "labs" / "labs.yaml"

# Upload format versions this tool can read. Bump when the format changes, and
# keep the old value here for as long as labs may still push it.
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1"})

# Properties that identify a result. Each must appear once per <testsuite>, and
# all suites in a file must agree on lab and commit.
_IDENTITY_PROPERTIES = ("schema_version", "lab", "ocudu_commit")


class ResultsFileError(Exception):
    """Raised when a file cannot be read or parsed as JUnit XML."""


# ---------------------------------------------------------------------------
# XML -> dict
# ---------------------------------------------------------------------------


def _testcase_status(elem: ET.Element) -> str:
    """Return the outcome of a <testcase>, using the same precedence as xunit_report.py."""
    if elem.find("failure") is not None:
        return "failed"
    if elem.find("error") is not None:
        return "error"
    if elem.find("skipped") is not None:
        return "skipped"
    return "passed"


def _testcase_to_dict(elem: ET.Element) -> dict[str, Any]:
    """Convert a <testcase> element to the shape the schema expects."""
    case: dict[str, Any] = {"name": elem.get("name", ""), "status": _testcase_status(elem)}
    if elem.get("classname") is not None:
        case["classname"] = elem.get("classname", "")
    raw_time = elem.get("time")
    if raw_time not in (None, ""):
        try:
            case["time"] = float(raw_time)  # type: ignore[arg-type]
        except ValueError:
            # Keep the raw string so the schema reports it as "not a number".
            case["time"] = raw_time
    return case


def _suite_properties(elem: ET.Element) -> tuple[dict[str, str], list[str]]:
    """Return (properties, duplicate_errors) for a <testsuite>'s own <properties> block.

    Only the suite-level block is read; <testcase> properties are per test and
    never carry the result's identity.
    """
    props: dict[str, str] = {}
    errors: list[str] = []
    props_elem = elem.find("properties")
    if props_elem is None:
        return props, errors
    for prop in props_elem.findall("property"):
        name = prop.get("name", "")
        if not name:
            continue
        value = prop.get("value", "")
        if name in props and name in _IDENTITY_PROPERTIES and props[name] != value:
            errors.append(f"property '{name}' is given twice with different values ('{props[name]}', '{value}')")
        props[name] = value
    return props, errors


def _suite_to_dict(elem: ET.Element) -> tuple[dict[str, Any], list[str]]:
    """Convert a <testsuite> element; returns (suite, property_errors)."""
    props, errors = _suite_properties(elem)
    suite: dict[str, Any] = {
        "name": elem.get("name", ""),
        "properties": props,
        "testcases": [_testcase_to_dict(tc) for tc in elem.findall("testcase")],
    }
    if elem.get("timestamp"):
        suite["timestamp"] = elem.get("timestamp", "")
    return suite, errors


def parse_results(data: bytes) -> tuple[dict[str, Any], list[str]]:
    """Parse JUnit XML bytes into the schema's dict shape.

    Returns (document, property_errors). Raises ResultsFileError if the bytes
    are not well-formed JUnit XML.

    Documents with a DOCTYPE are rejected outright: JUnit never needs one, and
    refusing them closes off entity-expansion tricks in untrusted uploads
    without adding a dependency.
    """
    if b"<!DOCTYPE" in data.upper():
        raise ResultsFileError("DOCTYPE declarations are not allowed in result files")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ResultsFileError(f"not well-formed XML: {exc}") from exc

    if root.tag == "testsuites":
        suite_elems = root.findall("testsuite")
    elif root.tag == "testsuite":
        suite_elems = [root]
    else:
        raise ResultsFileError(f"root element must be <testsuites> or <testsuite>, not <{root.tag}>")

    suites = []
    errors: list[str] = []
    for idx, elem in enumerate(suite_elems):
        suite, suite_errors = _suite_to_dict(elem)
        suites.append(suite)
        errors.extend(f"[testsuites -> {idx} -> properties] {e}" for e in suite_errors)
    return {"testsuites": suites}, errors


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> Any:
    """Load a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_lab_ids(labs_path: Path) -> set[str]:
    """Return the set of lab ids declared in labs.yaml."""
    data = load_yaml(labs_path) or {}
    labs = data.get("labs", []) if isinstance(data, dict) else []
    return {lab["id"] for lab in labs if isinstance(lab, dict) and isinstance(lab.get("id"), str)}


def _schema_errors(doc: dict[str, Any], validator: Draft7Validator) -> list[str]:
    """Format schema violations as '[path] message' strings."""
    errors = sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.path])
    return [f"[{' -> '.join(str(p) for p in err.path) or '/'}] {err.message}" for err in errors]


def _identity_errors(doc: dict[str, Any], lab_ids: set[str], expected_lab: Optional[str]) -> list[str]:
    """Checks the schema cannot express: known lab, supported version, one identity per file."""
    errors: list[str] = []
    suites = doc.get("testsuites", [])

    for prop in ("lab", "ocudu_commit"):
        values = sorted({s["properties"][prop] for s in suites if prop in s.get("properties", {})})
        if len(values) > 1:
            errors.append(f"all testsuites in a file must share one '{prop}', found: {', '.join(values)}")

    for idx, suite in enumerate(suites):
        props = suite.get("properties", {})
        where = f"[testsuites -> {idx} -> properties]"
        lab = props.get("lab")
        if lab is not None and lab not in lab_ids:
            errors.append(f"{where} unknown lab '{lab}' (not listed in labs/labs.yaml)")
        if lab is not None and expected_lab is not None and lab != expected_lab:
            errors.append(f"{where} lab '{lab}' does not match the expected lab '{expected_lab}'")
        version = props.get("schema_version")
        if version is not None and version not in SUPPORTED_SCHEMA_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
            errors.append(f"{where} unsupported schema_version '{version}' (supported: {supported})")
    return errors


def validate_document(
    doc: dict[str, Any],
    schema: dict[str, Any],
    lab_ids: set[str],
    expected_lab: Optional[str] = None,
) -> list[str]:
    """Return validation errors for an already-parsed document (empty = valid)."""
    errors = _schema_errors(doc, Draft7Validator(schema))
    errors.extend(_identity_errors(doc, lab_ids, expected_lab))
    return errors


def validate_bytes(
    data: bytes,
    schema: dict[str, Any],
    lab_ids: set[str],
    expected_lab: Optional[str] = None,
) -> list[str]:
    """Return validation errors for raw XML bytes (empty = valid). Never raises on bad input."""
    try:
        doc, errors = parse_results(data)
    except ResultsFileError as exc:
        return [str(exc)]
    return errors + validate_document(doc, schema, lab_ids, expected_lab)


def validate_file(
    path: Path,
    schema: dict[str, Any],
    lab_ids: set[str],
    expected_lab: Optional[str] = None,
) -> list[str]:
    """Return validation errors for one result file (empty = valid). Never raises on bad input."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [f"cannot read file: {exc}"]
    return validate_bytes(data, schema, lab_ids, expected_lab)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """Validate result files given on the command line."""
    parser = argparse.ArgumentParser(description="Validate JUnit XML result files for the OCUDU test report.")
    parser.add_argument("files", nargs="+", type=Path, help="JUnit XML result files to validate")
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_FILE,
        help=f"Results JSON Schema (default: {DEFAULT_SCHEMA_FILE})",
    )
    parser.add_argument(
        "--labs",
        type=Path,
        default=DEFAULT_LABS_FILE,
        help=f"Labs registry (default: {DEFAULT_LABS_FILE})",
    )
    parser.add_argument("--lab", help="Require every file to name this lab")
    args = parser.parse_args(argv)

    try:
        schema = load_yaml(args.schema)
        lab_ids = load_lab_ids(args.labs)
    except (OSError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    failed = 0
    for path in args.files:
        errors = validate_file(path, schema, lab_ids, args.lab)
        if errors:
            failed += 1
            print(f"FAILED {path} ({len(errors)} error(s)):")
            for err in errors:
                print(f"  {err}")
        else:
            print(f"OK     {path}")

    print(f"\n{len(args.files) - failed} of {len(args.files)} file(s) valid.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
