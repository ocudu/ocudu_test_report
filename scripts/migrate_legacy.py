#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Add the results-contract properties to existing JUnit XML files.

Results published before the lab results contract (schemas/results.schema.yaml)
don't say which lab ran them, and some don't say which OCUDU commit they
tested either. This one-off tool copies a folder of such files and adds the
missing <testsuite> properties so they pass validate_results.py:

  * schema_version  - always set to the current upload format version;
  * lab             - set to --lab; a file that already names a different lab
                      is an error, because that is a mistake, not missing data;
  * ocudu_commit    - set to --commit when missing or empty. A file that
                      already names a different commit keeps its own value
                      unless --overwrite-commit is given, so real data is
                      never replaced silently.

A commit already in a file can be a short SHA (e.g. "35d45fa"), which the
contract does not accept. --expand-commit SHORT=FULL rewrites it to the full
SHA; FULL must start with SHORT, so it names the same commit and never
changes which commit a result is recorded against.

The input folder is never modified. Every file under it is copied to the
output folder with the same relative path; XML files get the properties added,
everything else (e.g. _url.txt, _order.txt) is copied unchanged.

Usage:
  migrate_legacy.py SRC -o OUT --lab ocudu-ci --commit <40-hex sha>

Exit codes:
  0  - every XML file was migrated and passes validate_results.py
  1  - at least one XML file could not be migrated or fails validation
  2  - usage error
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import validate_results

SCHEMA_VERSION = "1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class MigrationError(Exception):
    """Raised when a file cannot be migrated without guessing."""


@dataclass
class FileReport:
    """What happened to one XML file."""

    path: Path
    # How many suites had their commit filled, matched, expanded, kept or overwritten.
    commits: Counter = field(default_factory=Counter)
    error: str = ""
    validation_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if the file was migrated and passes validation."""
        return not self.error and not self.validation_errors


def _parse(data: bytes) -> ET.Element:
    """Parse XML bytes, keeping comments so SPDX headers survive the round trip."""
    if b"<!DOCTYPE" in data.upper():
        raise MigrationError("DOCTYPE declarations are not allowed in result files")
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    try:
        return ET.fromstring(data, parser=parser)
    except ET.ParseError as exc:
        raise MigrationError(f"not well-formed XML: {exc}") from exc


def _suites(root: ET.Element) -> list[ET.Element]:
    if root.tag == "testsuites":
        return root.findall("testsuite")
    if root.tag == "testsuite":
        return [root]
    raise MigrationError(f"root element must be <testsuites> or <testsuite>, not <{root.tag}>")


def _properties_elem(suite: ET.Element) -> ET.Element:
    """Return the suite's own <properties>, creating it as the first child if missing."""
    props = suite.find("properties")
    if props is None:
        props = ET.Element("properties")
        suite.insert(0, props)
    return props


def _get_property(props: ET.Element, name: str) -> Optional[str]:
    for prop in props.findall("property"):
        if prop.get("name") == name:
            return prop.get("value", "")
    return None


def _set_property(props: ET.Element, name: str, value: str) -> None:
    """Set a property, updating the first existing entry or appending a new one."""
    for prop in props.findall("property"):
        if prop.get("name") == name:
            prop.set("value", value)
            return
    ET.SubElement(props, "property", {"name": name, "value": value})


def parse_expansions(values: list[str]) -> dict[str, str]:
    """Parse SHORT=FULL pairs, checking each FULL is a full SHA that starts with SHORT."""
    expansions: dict[str, str] = {}
    for value in values:
        short, sep, full = value.partition("=")
        if not sep or not short or not _SHA_RE.match(full) or not full.startswith(short):
            raise ValueError(f"'{value}' must be SHORT=FULL, where FULL is a 40-character SHA starting with SHORT")
        expansions[short] = full
    return expansions


def migrate_suite(
    suite: ET.Element,
    lab: str,
    commit: str,
    overwrite_commit: bool = False,
    expansions: Optional[dict[str, str]] = None,
) -> str:
    """Add the contract properties to one <testsuite>.

    Returns how the commit was handled: "filled", "matched", "expanded", "kept"
    or "overwritten". Raises MigrationError if the suite already names another lab.
    """
    props = _properties_elem(suite)

    existing_lab = _get_property(props, "lab")
    if existing_lab not in (None, "", lab):
        raise MigrationError(f"testsuite '{suite.get('name', '')}' already names lab '{existing_lab}', not '{lab}'")
    _set_property(props, "schema_version", SCHEMA_VERSION)
    _set_property(props, "lab", lab)

    existing_commit = _get_property(props, "ocudu_commit")
    if not existing_commit:
        _set_property(props, "ocudu_commit", commit)
        return "filled"
    if existing_commit in (expansions or {}):
        existing_commit = (expansions or {})[existing_commit]
        _set_property(props, "ocudu_commit", existing_commit)
        if existing_commit == commit:
            return "matched"
        if not overwrite_commit:
            return "expanded"
    if existing_commit == commit:
        return "matched"
    if overwrite_commit:
        _set_property(props, "ocudu_commit", commit)
        return "overwritten"
    return "kept"


def migrate_bytes(
    data: bytes,
    lab: str,
    commit: str,
    overwrite_commit: bool = False,
    expansions: Optional[dict[str, str]] = None,
) -> tuple[bytes, Counter]:
    """Migrate one XML document. Returns (new_bytes, commit_actions)."""
    root = _parse(data)
    actions: Counter = Counter()
    for suite in _suites(root):
        actions[migrate_suite(suite, lab, commit, overwrite_commit, expansions)] += 1
    if not actions:
        raise MigrationError("file contains no <testsuite> elements")
    body = ET.tostring(root, encoding="unicode")
    prolog = _prolog(data)
    return f"<?xml version='1.0' encoding='utf-8'?>\n{prolog}{body}".encode("utf-8"), actions


# Anything between the XML declaration and the root element, i.e. comments and
# processing instructions. ElementTree throws these away, and some files keep
# their licence header there.
_PROLOG_RE = re.compile(rb"^\s*(?:<\?xml[^>]*\?>)?((?:\s|<!--.*?-->|<\?.*?\?>)*)", re.DOTALL)


def _prolog(data: bytes) -> str:
    """Return the comments that sit before the root element, unchanged."""
    match = _PROLOG_RE.match(data)
    prolog = match.group(1).strip() if match else b""
    return prolog.decode("utf-8") + "\n" if prolog else ""


def migrate_tree(
    src: Path,
    out: Path,
    lab: str,
    commit: str,
    overwrite_commit: bool = False,
    lab_ids: Optional[set[str]] = None,
    schema: Optional[dict] = None,
    expansions: Optional[dict[str, str]] = None,
) -> list[FileReport]:
    """Copy src to out, migrating every XML file. Returns one report per XML file.

    If lab_ids and schema are given, each migrated file is also checked with
    validate_results so problems show up here rather than at upload.
    """
    reports: list[FileReport] = []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() != ".xml":
            shutil.copy2(path, dest)
            continue

        report = FileReport(rel)
        reports.append(report)
        try:
            new_data, report.commits = migrate_bytes(path.read_bytes(), lab, commit, overwrite_commit, expansions)
        except (MigrationError, OSError) as exc:
            report.error = str(exc)
            continue
        dest.write_bytes(new_data)
        if lab_ids is not None and schema is not None:
            report.validation_errors = validate_results.validate_bytes(new_data, schema, lab_ids, lab)
    return reports


def _print_summary(reports: list[FileReport]) -> None:
    totals: Counter = Counter()
    for report in reports:
        totals.update(report.commits)
        if report.error:
            print(f"FAILED  {report.path}: {report.error}")
        for err in report.validation_errors:
            print(f"INVALID {report.path}: {err}")
        if report.commits.get("kept") or report.commits.get("expanded") or report.commits.get("overwritten"):
            print(f"NOTE    {report.path}: {dict(report.commits)}")

    ok = sum(1 for r in reports if r.ok)
    print(f"\n{ok} of {len(reports)} XML file(s) migrated and valid.")
    print(
        "Suites by commit handling: "
        + ", ".join(f"{k}={totals.get(k, 0)}" for k in ("filled", "matched", "expanded", "kept", "overwritten"))
    )
    if totals.get("kept"):
        print("'kept' suites already named a different commit and were left as they are (see --overwrite-commit).")


def main(argv: Optional[list[str]] = None) -> int:
    """Entrypoint."""
    parser = argparse.ArgumentParser(description="Add lab/commit properties to existing JUnit XML results.")
    parser.add_argument("src", type=Path, help="Folder of existing result files (left untouched)")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Folder to write migrated files to")
    parser.add_argument("--lab", required=True, help="Lab id to record (must exist in labs/labs.yaml)")
    parser.add_argument("--commit", required=True, help="Full 40-character OCUDU commit for suites that lack one")
    parser.add_argument(
        "--overwrite-commit",
        action="store_true",
        help="Replace commits already present in the files instead of keeping them",
    )
    parser.add_argument(
        "--expand-commit",
        action="append",
        default=[],
        metavar="SHORT=FULL",
        help="Rewrite a short commit already in the files to its full SHA (repeatable)",
    )
    parser.add_argument("--labs", type=Path, default=validate_results.DEFAULT_LABS_FILE, help="Labs registry")
    parser.add_argument("--schema", type=Path, default=validate_results.DEFAULT_SCHEMA_FILE, help="Results schema")
    args = parser.parse_args(argv)

    if not _SHA_RE.match(args.commit):
        parser.error("--commit must be a full 40-character lowercase SHA")
    try:
        expansions = parse_expansions(args.expand_commit)
    except ValueError as exc:
        parser.error(f"--expand-commit {exc}")
    if not args.src.is_dir():
        parser.error(f"source folder not found: {args.src}")
    src, out = args.src.resolve(), args.output.resolve()
    if out == src or src in out.parents:
        parser.error("output folder must not be inside the source folder")

    try:
        lab_ids = validate_results.load_lab_ids(args.labs)
        schema = validate_results.load_yaml(args.schema)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.lab not in lab_ids:
        parser.error(f"unknown lab '{args.lab}' (not listed in {args.labs})")

    reports = migrate_tree(src, out, args.lab, args.commit, args.overwrite_commit, lab_ids, schema, expansions)
    _print_summary(reports)
    return 0 if reports and all(r.ok for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
