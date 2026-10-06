#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OpenInfra Foundation Europe. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Compare two test run results and produce a structured diff.

Reads two results.json files (produced by xunit_report.py) and classifies
every test into one of: regression, fix, new_failure, new_pass, removed,
or unchanged.  Outputs a JSON diff suitable for rendering or further analysis.

Usage:
    python diff_runs.py base.json head.json -o diff.json
    python diff_runs.py base.json head.json --summary
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class DiffClass(Enum):
    """Classification of a test case difference between two runs."""

    REGRESSION = "regression"  # pass/skip -> fail/error
    FIX = "fix"  # fail/error -> pass
    NEW_FAILURE = "new_failure"  # absent -> fail/error
    NEW_PASS = "new_pass"  # absent -> pass
    NEW_SKIP = "new_skip"  # absent -> skip
    REMOVED = "removed"  # present -> absent
    UNCHANGED = "unchanged"  # same status both runs


_FAIL_STATUSES = frozenset({"failed", "error"})
_PASS_STATUSES = frozenset({"passed"})


@dataclass
class DiffEntry:  # pylint: disable=too-many-instance-attributes
    """A single test case that differs between the two runs."""

    key: str
    diff_class: str
    status_base: str | None = None
    status_head: str | None = None
    duration_base: float | None = None
    duration_head: float | None = None
    labels: list[str] = field(default_factory=list)
    anchor: str = ""


@dataclass
class DiffSummary:  # pylint: disable=too-many-instance-attributes
    """Aggregate counts for each diff classification."""

    total_base: int = 0
    total_head: int = 0
    regressions: int = 0
    fixes: int = 0
    new_failures: int = 0
    new_passes: int = 0
    new_skips: int = 0
    removed: int = 0
    unchanged: int = 0


def _flatten_results(results: dict) -> dict[str, dict]:
    """Flatten a results.json structure into {key: test_entry} dict.

    Handles both the suite-grouped format and a flat list. If a key appears
    in multiple suites, the last occurrence wins (unlikely but handled).
    """
    flat: dict[str, dict] = {}
    for suite in results.get("suites", []):
        for test in suite.get("tests", []):
            flat[test["key"]] = test
    return flat


def _classify(  # pylint: disable=too-many-return-statements
    status_base: str | None, status_head: str | None
) -> DiffClass:
    """Classify the transition between two statuses."""
    if status_base is None:
        # New test in head
        if status_head in _FAIL_STATUSES:
            return DiffClass.NEW_FAILURE
        if status_head in _PASS_STATUSES:
            return DiffClass.NEW_PASS
        return DiffClass.NEW_SKIP

    if status_head is None:
        return DiffClass.REMOVED

    if status_base == status_head:
        return DiffClass.UNCHANGED

    # Status changed
    if status_head in _FAIL_STATUSES and status_base not in _FAIL_STATUSES:
        return DiffClass.REGRESSION
    if status_head in _PASS_STATUSES and status_base in _FAIL_STATUSES:
        return DiffClass.FIX

    # Other transitions (e.g. pass->skip, skip->pass, fail->skip)
    # These are status changes but not clearly regression or fix
    return DiffClass.UNCHANGED


def diff_runs(base: dict, head: dict) -> tuple[list[DiffEntry], DiffSummary]:  # pylint: disable=too-many-locals
    """Compare two results.json structures and return classified differences.

    Args:
        base: Parsed results.json for the baseline run (older).
        head: Parsed results.json for the head run (newer).

    Returns:
        A tuple of (entries, summary) where entries contains only tests that
        differ between the runs (unchanged tests are counted but not included
        in the entries list).
    """
    base_tests = _flatten_results(base)
    head_tests = _flatten_results(head)

    keys_base = set(base_tests.keys())
    keys_head = set(head_tests.keys())

    common = keys_base & keys_head
    added = keys_head - keys_base
    removed = keys_base - keys_head

    entries: list[DiffEntry] = []
    summary = DiffSummary(total_base=len(keys_base), total_head=len(keys_head))

    # Common tests — check for status changes
    for key in sorted(common):
        tc_base = base_tests[key]
        tc_head = head_tests[key]
        diff_class = _classify(tc_base["status"], tc_head["status"])

        if diff_class == DiffClass.UNCHANGED:
            summary.unchanged += 1
            continue

        entry = DiffEntry(
            key=key,
            diff_class=diff_class.value,
            status_base=tc_base["status"],
            status_head=tc_head["status"],
            duration_base=tc_base.get("duration_s"),
            duration_head=tc_head.get("duration_s"),
            labels=tc_head.get("labels", []),
            anchor=tc_head.get("anchor", "") or tc_base.get("anchor", ""),
        )
        entries.append(entry)

        if diff_class == DiffClass.REGRESSION:
            summary.regressions += 1
        elif diff_class == DiffClass.FIX:
            summary.fixes += 1

    # Added tests (in head but not base)
    for key in sorted(added):
        tc_head = head_tests[key]
        diff_class = _classify(None, tc_head["status"])

        entry = DiffEntry(
            key=key,
            diff_class=diff_class.value,
            status_base=None,
            status_head=tc_head["status"],
            duration_base=None,
            duration_head=tc_head.get("duration_s"),
            labels=tc_head.get("labels", []),
            anchor=tc_head.get("anchor", ""),
        )
        entries.append(entry)

        if diff_class == DiffClass.NEW_FAILURE:
            summary.new_failures += 1
        elif diff_class == DiffClass.NEW_PASS:
            summary.new_passes += 1
        elif diff_class == DiffClass.NEW_SKIP:
            summary.new_skips += 1

    # Removed tests (in base but not head)
    for key in sorted(removed):
        tc_base = base_tests[key]
        entry = DiffEntry(
            key=key,
            diff_class=DiffClass.REMOVED.value,
            status_base=tc_base["status"],
            status_head=None,
            duration_base=tc_base.get("duration_s"),
            duration_head=None,
            labels=tc_base.get("labels", []),
            anchor=tc_base.get("anchor", ""),
        )
        entries.append(entry)
        summary.removed += 1

    return entries, summary


def build_diff_output(
    base: dict,
    head: dict,
) -> dict:
    """Build the complete diff output dictionary.

    Returns a JSON-serialisable dict with summary, metadata from both runs,
    and categorised diff entries.
    """
    entries, summary = diff_runs(base, head)

    # Group entries by diff class for the output
    grouped: dict[str, list[dict]] = {
        "regressions": [],
        "fixes": [],
        "new_failures": [],
        "new_passes": [],
        "new_skips": [],
        "removed": [],
    }

    class_to_group = {
        "regression": "regressions",
        "fix": "fixes",
        "new_failure": "new_failures",
        "new_pass": "new_passes",
        "new_skip": "new_skips",
        "removed": "removed",
    }

    for entry in entries:
        entry_dict = asdict(entry)
        del entry_dict["diff_class"]  # redundant once grouped
        group_key = class_to_group.get(entry.diff_class)
        if group_key:
            grouped[group_key].append(entry_dict)

    return {
        "schema_version": 1,
        "base": {
            "pipeline_id": base.get("pipeline_id", ""),
            "commit_sha": base.get("commit_sha", ""),
            "generated_at": base.get("generated_at", ""),
        },
        "head": {
            "pipeline_id": head.get("pipeline_id", ""),
            "commit_sha": head.get("commit_sha", ""),
            "generated_at": head.get("generated_at", ""),
        },
        "summary": asdict(summary),
        **grouped,
    }


def main():
    """Entry point: parse arguments, load files, write diff."""
    parser = argparse.ArgumentParser(description="Compare two test run results and produce a structured diff")
    parser.add_argument(
        "base",
        type=Path,
        help="Path to the baseline results.json (older run)",
    )
    parser.add_argument(
        "head",
        type=Path,
        help="Path to the head results.json (newer run)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print only the summary counts to stderr",
    )
    args = parser.parse_args()

    if not args.base.exists():
        print(f"ERROR: Base file not found: {args.base}", file=sys.stderr)
        sys.exit(1)
    if not args.head.exists():
        print(f"ERROR: Head file not found: {args.head}", file=sys.stderr)
        sys.exit(1)

    base = json.loads(args.base.read_text(encoding="utf-8"))
    head = json.loads(args.head.read_text(encoding="utf-8"))

    result = build_diff_output(base, head)

    if args.summary:
        s = result["summary"]
        print(
            f"Base: {s['total_base']} tests | Head: {s['total_head']} tests\n"
            f"  Regressions:  {s['regressions']}\n"
            f"  Fixes:        {s['fixes']}\n"
            f"  New failures: {s['new_failures']}\n"
            f"  New passes:   {s['new_passes']}\n"
            f"  New skips:    {s['new_skips']}\n"
            f"  Removed:      {s['removed']}\n"
            f"  Unchanged:    {s['unchanged']}",
            file=sys.stderr,
        )

    output_text = json.dumps(result, indent=2) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")
        print(f"Diff written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output_text)


if __name__ == "__main__":
    main()
