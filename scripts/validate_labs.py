#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Validate labs/labs.yaml and releases.yaml against their schemas.

On top of the schema, checks that ids are unique and that every public key a
lab points to is present under labs/. Runs on every MR so a broken lab or
release entry is caught before it reaches the report.

Exit codes:
  0  - validation passed
  1  - validation failed
  2  - usage / file error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
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


_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LABS_FILE = _REPO_ROOT / "labs" / "labs.yaml"
DEFAULT_LABS_SCHEMA = _REPO_ROOT / "schemas" / "labs.schema.yaml"
DEFAULT_RELEASES_FILE = _REPO_ROOT / "releases.yaml"
DEFAULT_RELEASES_SCHEMA = _REPO_ROOT / "schemas" / "releases.schema.yaml"


def load_yaml(path: Path) -> Any:
    """Load a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def schema_errors(data: Any, schema: dict[str, Any]) -> list[str]:
    """Return schema violations as '[path] message' strings."""
    errors = sorted(Draft7Validator(schema).iter_errors(data), key=lambda e: [str(p) for p in e.path])
    return [f"[{' -> '.join(str(p) for p in err.path) or '/'}] {err.message}" for err in errors]


def duplicate_errors(items: Any, field: str, section: str) -> list[str]:
    """Report entries in a list of dicts that repeat the value of `field`."""
    if not isinstance(items, list):
        return []
    seen: dict[Any, int] = {}
    errors: list[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict) or field not in item:
            continue
        value = item[field]
        if value in seen:
            errors.append(f"[{section} -> {idx}] duplicate {field} '{value}' (first seen at index {seen[value]})")
        else:
            seen[value] = idx
    return errors


def check_labs(data: Any, schema: dict[str, Any], labs_dir: Path) -> list[str]:
    """Validate parsed labs.yaml content. `labs_dir` is where public keys live."""
    errors = schema_errors(data, schema)
    labs = data.get("labs") if isinstance(data, dict) else None
    errors.extend(duplicate_errors(labs, "id", "labs"))
    for idx, lab in enumerate(labs if isinstance(labs, list) else []):
        key = lab.get("public_key") if isinstance(lab, dict) else None
        if isinstance(key, str) and not (labs_dir / key).is_file():
            errors.append(f"[labs -> {idx}] public key '{key}' not found in {labs_dir}")
    return errors


def check_releases(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate parsed releases.yaml content."""
    errors = schema_errors(data, schema)
    releases = data.get("releases") if isinstance(data, dict) else None
    for field in ("name", "tag", "ocudu_commit"):
        errors.extend(duplicate_errors(releases, field, "releases"))
    return errors


def _run(label: str, data_path: Path, schema_path: Path, check) -> int:
    """Load, check and print the result for one file. Returns 0, 1 or 2."""
    try:
        data = load_yaml(data_path)
        schema = load_yaml(schema_path)
    except (OSError, yaml.YAMLError) as exc:
        print(f"ERROR: {label}: {exc}", file=sys.stderr)
        return 2
    errors = check(data, schema)
    if errors:
        print(f"FAILED {data_path} ({len(errors)} error(s)):")
        for err in errors:
            print(f"  {err}")
        return 1
    print(f"OK     {data_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entrypoint."""
    parser = argparse.ArgumentParser(description="Validate labs.yaml and releases.yaml.")
    parser.add_argument("--labs", type=Path, default=DEFAULT_LABS_FILE, help="Labs registry file")
    parser.add_argument("--labs-schema", type=Path, default=DEFAULT_LABS_SCHEMA, help="Labs JSON Schema")
    parser.add_argument("--releases", type=Path, default=DEFAULT_RELEASES_FILE, help="Pinned releases file")
    parser.add_argument("--releases-schema", type=Path, default=DEFAULT_RELEASES_SCHEMA, help="Releases JSON Schema")
    args = parser.parse_args(argv)

    labs_rc = _run("labs", args.labs, args.labs_schema, lambda d, s: check_labs(d, s, args.labs.parent))
    releases_rc = _run("releases", args.releases, args.releases_schema, check_releases)
    return max(labs_rc, releases_rc)


if __name__ == "__main__":
    sys.exit(main())
