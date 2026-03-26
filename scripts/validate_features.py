#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Validate features.yaml against features.schama (JSON Schema in YAML format).

Exit codes:
  0  - validation passed
  1  - validation failed (schema violations)
  2  - usage / file error
"""

import argparse
import sys
from typing import Any

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


DEFAULT_DATA_FILE = "features.yaml"
DEFAULT_SCHEMA_FILE = "features.schema"


def load_file(path: str) -> Any:
    """Load a YAML or JSON file (JSON is valid YAML)."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate(data_path: str, schema_path: str) -> list[str]:
    """Return a list of validation error messages (empty = valid)."""
    try:
        data = load_file(data_path)
    except FileNotFoundError:
        return [f"Data file not found: {data_path}"]
    except yaml.YAMLError as e:
        return [f"Failed to parse data file '{data_path}': {e}"]

    try:
        schema = load_file(schema_path)
    except FileNotFoundError:
        return [f"Schema file not found: {schema_path}"]
    except yaml.YAMLError as e:
        return [f"Failed to parse schema file '{schema_path}': {e}"]

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    messages = []
    for err in errors:
        path = list(err.path)
        feature_id = ""
        if len(path) >= 2 and path[0] == "features" and isinstance(path[1], int):
            feature_id = data["features"][path[1]].get("id", "")
        id_part = f" (id: {feature_id})" if feature_id else ""
        messages.append(f"  [{' -> '.join(str(p) for p in path) or '/'}]{id_part} {err.message}")
    return messages


def main() -> None:
    """Entrypoint"""
    parser = argparse.ArgumentParser(description="Validate features.yaml against its JSON Schema.")
    parser.add_argument(
        "--data",
        default=DEFAULT_DATA_FILE,
        help=f"Path to features YAML/JSON file (default: {DEFAULT_DATA_FILE})",
    )
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA_FILE,
        help=f"Path to JSON Schema file (default: {DEFAULT_SCHEMA_FILE})",
    )
    args = parser.parse_args()

    print(f"Validating '{args.data}' against schema '{args.schema}' ...")
    errors = validate(args.data, args.schema)

    if errors:
        print(f"FAILED — {len(errors)} error(s) found:\n")
        print("\n".join(errors))
        sys.exit(1)
    else:
        print("OK — features file is valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
