#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Validate tifg_tests.yaml against its YAML schema.

Exit codes:
  0  - validation passed
  1  - validation failed (schema violations or duplicate IDs)
  2  - usage / file error
"""

import argparse
import sys
from pathlib import Path

import jsonschema
import yaml

DEFAULT_TESTS_FILE = str(Path(__file__).parent.parent / "tifg_test_plan" / "tifg_tests.yaml")
DEFAULT_SCHEMA_FILE = str(Path(__file__).parent.parent / "tifg_test_plan" / "tifg_tests.schema")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a TIFG test plan YAML against its JSON Schema.")
    parser.add_argument(
        "--data",
        default=DEFAULT_TESTS_FILE,
        help=f"Path to the TIFG tests YAML file (default: {DEFAULT_TESTS_FILE})",
    )
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA_FILE,
        help=f"Path to the YAML schema file (default: {DEFAULT_SCHEMA_FILE})",
    )
    args = parser.parse_args()

    try:
        with open(args.schema) as f:
            schema = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: schema file not found: {args.schema}", file=sys.stderr)
        return 2
    except yaml.YAMLError as e:
        print(f"ERROR: failed to parse schema file '{args.schema}': {e}", file=sys.stderr)
        return 2

    try:
        with open(args.data) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: data file not found: {args.data}", file=sys.stderr)
        return 2
    except yaml.YAMLError as e:
        print(f"ERROR: failed to parse data file '{args.data}': {e}", file=sys.stderr)
        return 2

    print(f"Validating '{args.data}' against schema '{args.schema}' ...")

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        path = " -> ".join(str(p) for p in e.absolute_path)
        print(f"FAILED: {e.message}", file=sys.stderr)
        if path:
            print(f"  Path: {path}", file=sys.stderr)
        return 1

    tests = data.get("tests", [])
    ids = [t["test_id"] for t in tests]
    duplicates = sorted({tid for tid in ids if ids.count(tid) > 1})
    if duplicates:
        print(f"FAILED: duplicate test_ids: {duplicates}", file=sys.stderr)
        return 1

    scopes: dict[str, int] = {}
    for t in tests:
        scopes[t["scope"]] = scopes.get(t["scope"], 0) + 1

    print(f"OK - {len(tests)} test cases")
    for scope, count in sorted(scopes.items()):
        print(f"  {scope}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
