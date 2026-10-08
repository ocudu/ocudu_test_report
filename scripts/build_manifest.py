#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Build a runs.json manifest incrementally in the Generic Package Registry.

The manifest is kept as its own file in the registry (package
test-report-runs, version "index", file runs.json). Each run downloads the
previous manifest, appends its own metadata, and re-uploads it. The manifest
is used by the UI to offer run selection and by the comparison engine to
identify runs for diffing.

This avoids listing packages via GET /projects/:id/packages, which the CI job
token is not authorised to call. Downloading and uploading a package file by
version both work with the job token, so the whole flow stays job-token-only.

Usage:
    python build_manifest.py --project-id 12345 --current-run public/run_metadata.json -o public/runs.json
    python build_manifest.py --project-id 12345 --gitlab-url https://gitlab.example.com -o runs.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(2)

_PACKAGE_NAME = "test-report-runs"
_INDEX_VERSION = "index"
_INDEX_FILENAME = "runs.json"
_HTTP_TIMEOUT = 30
_SCHEMA_VERSION = 1

# GitLab returns 404 for a missing generic-package file when read with a
# personal access token, but the CI job token gets 401 (and can get 403)
# for a file that does not exist yet. On the very first run the index has
# never been uploaded, so all of these mean "no index yet, start empty".
# The upload (PUT) is authorised for the job token, so the first run still
# creates the index once we stop treating a missing-index read as fatal.
_INDEX_ABSENT_STATUSES = (401, 403, 404)


def _get_auth_headers(token: str, token_type: str = "private") -> dict[str, str]:
    """Return the appropriate auth header for the given token type."""
    if token_type == "job":
        return {"JOB-TOKEN": token}
    return {"PRIVATE-TOKEN": token}


def _index_url(api_url: str, project_id: str) -> str:
    """Return the generic-package URL for the runs.json index file."""
    return f"{api_url}/projects/{project_id}/packages/generic" f"/{_PACKAGE_NAME}/{_INDEX_VERSION}/{_INDEX_FILENAME}"


def _run_download_url(api_url: str, project_id: str, version: str) -> str:
    """Return the generic-package URL for a run's report.zip."""
    return f"{api_url}/projects/{project_id}/packages/generic" f"/{_PACKAGE_NAME}/{version}/report.zip"


def download_index(
    api_url: str,
    project_id: str,
    headers: dict[str, str],
) -> dict:
    """Download the existing runs.json index from the registry.

    Returns the parsed manifest dict. If the index does not exist yet (the
    first run) or cannot be parsed, returns a fresh empty manifest. GitLab
    reports a missing generic-package file as 404 for a personal token but as
    401/403 for the CI job token, so all of those are treated as "no index
    yet". Only genuine transport errors are surfaced (and also fall back to an
    empty manifest so a single flaky read never fails the whole step).
    """
    url = _index_url(api_url, project_id)
    try:
        resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        print(f"WARNING: Could not reach the registry to read the index: {exc}", file=sys.stderr)
        return _empty_manifest()

    if resp.status_code in _INDEX_ABSENT_STATUSES:
        print(
            f"No readable index found (HTTP {resp.status_code}); treating as first run and starting fresh.",
            file=sys.stderr,
        )
        return _empty_manifest()

    resp.raise_for_status()

    try:
        manifest: dict = json.loads(resp.content)
    except json.JSONDecodeError as exc:
        print(f"WARNING: Existing index is not valid JSON ({exc}). Starting fresh.", file=sys.stderr)
        return _empty_manifest()

    runs = manifest.get("runs")
    if not isinstance(runs, list):
        print("WARNING: Existing index has no runs list. Starting fresh.", file=sys.stderr)
        return _empty_manifest()

    return manifest


def upload_index(
    api_url: str,
    project_id: str,
    headers: dict[str, str],
    manifest: dict,
) -> bool:
    """Upload the manifest back to the registry as the runs.json index.

    Returns True on success (HTTP 200/201), False otherwise. Uploading a
    generic package file is permitted with the CI job token.
    """
    url = _index_url(api_url, project_id)
    payload = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    try:
        resp = requests.put(url, headers=headers, data=payload, timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        print(f"WARNING: Failed to upload the index: {exc}", file=sys.stderr)
        return False

    if resp.status_code in (200, 201):
        return True

    print(f"WARNING: Index upload returned HTTP {resp.status_code}.", file=sys.stderr)
    return False


def _empty_manifest() -> dict:
    """Return a fresh, empty manifest structure."""
    return {"schema_version": _SCHEMA_VERSION, "total_runs": 0, "runs": []}


def _run_sort_key(run: dict) -> int:
    """Sort key for a run: numeric pipeline_id descending, unknowns last."""
    value = run.get("pipeline_id") or run.get("package_version") or ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _run_fingerprint(run: dict) -> tuple:
    """Return a comparable fingerprint of a run's test results.

    Captures only the stable result content -- the per-suite names with their
    pass/fail/skip/total counts, plus the overall totals -- and deliberately
    ignores volatile fields such as pipeline_id, commit_sha, generated_at,
    label, and the derived download URL. Two runs with the same fingerprint
    describe the same test estate in the same state.
    """
    suites = run.get("suites", [])
    suite_prints = tuple(
        sorted(
            (
                str(s.get("name", "")),
                int(s.get("total", 0) or 0),
                int(s.get("passed", 0) or 0),
                int(s.get("failed", 0) or 0),
                int(s.get("skipped", 0) or 0),
            )
            for s in suites
        )
    )
    totals = run.get("totals", {})
    totals_print = (
        int(totals.get("tests", 0) or 0),
        int(totals.get("passed", 0) or 0),
        int(totals.get("failed", 0) or 0),
        int(totals.get("skipped", 0) or 0),
    )
    return (suite_prints, totals_print)


def add_run(
    manifest: dict,
    run_metadata: dict,
    api_url: str,
    project_id: str,
    max_runs: int = 0,
) -> dict:
    """Return a new manifest with run_metadata added (or replacing a duplicate).

    Runs are keyed by pipeline_id. A run with the same pipeline_id as an
    existing entry replaces it, so re-running a pipeline does not create
    duplicates. In addition, a fresh re-trigger on unchanged data (a new
    pipeline_id but identical test results to the newest indexed run) is not
    appended at all -- it would only clutter the history and skew the trends
    and comparison, which both treat each run as a distinct snapshot. Runs are
    sorted newest-first and capped at max_runs (0 = all).
    """
    version = str(run_metadata.get("pipeline_id", "")).strip()
    existing = manifest.get("runs", [])

    # Index-time dedupe: if this run is a new pipeline whose results are
    # identical to the current newest run, skip it. Runs that share a
    # pipeline_id are a retry and fall through to the replace path below.
    # Only runs that actually carry result content are deduped -- an empty
    # fingerprint (no suites and no totals) is never treated as a match.
    if existing:
        newest = max(existing, key=_run_sort_key)
        newest_version = str(newest.get("pipeline_id", "")).strip()
        new_print = _run_fingerprint(run_metadata)
        has_content = new_print != ((), (0, 0, 0, 0))
        if has_content and version != newest_version and new_print == _run_fingerprint(newest):
            return {
                "schema_version": _SCHEMA_VERSION,
                "total_runs": len(existing),
                "runs": existing,
            }

    entry = dict(run_metadata)
    if version:
        entry["package_version"] = version
        entry["download_url"] = _run_download_url(api_url, project_id, version)

    kept = [r for r in existing if str(r.get("pipeline_id", "")).strip() != version or not version]
    kept.append(entry)
    kept.sort(key=_run_sort_key, reverse=True)

    if max_runs > 0:
        kept = kept[:max_runs]

    return {
        "schema_version": _SCHEMA_VERSION,
        "total_runs": len(kept),
        "runs": kept,
    }


def _load_current_run(path: Path) -> dict | None:
    """Load the current run's metadata from a local run_metadata.json file."""
    try:
        metadata: dict = json.loads(path.read_text(encoding="utf-8"))
        return metadata
    except FileNotFoundError:
        print(f"WARNING: Current run metadata not found at {path}.", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"WARNING: Current run metadata is not valid JSON ({exc}).", file=sys.stderr)
        return None


def main():
    """Entry point: parse arguments, update the index, and write the manifest."""
    parser = argparse.ArgumentParser(
        description="Build the runs.json manifest incrementally in the Generic Package Registry"
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="GitLab project ID (numeric)",
    )
    parser.add_argument(
        "--gitlab-url",
        default="https://gitlab.com",
        help="GitLab instance URL (default: https://gitlab.com)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="GitLab API token (defaults to GITLAB_TOKEN or CI_JOB_TOKEN env var)",
    )
    parser.add_argument(
        "--token-type",
        choices=["private", "job"],
        default="private",
        help="Token type: 'private' for PRIVATE-TOKEN, 'job' for JOB-TOKEN (default: private)",
    )
    parser.add_argument(
        "--current-run",
        type=Path,
        default=None,
        help="Path to the current run's run_metadata.json to append to the index",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Maximum number of runs to keep in the manifest (0 = all, default: 0)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Do not upload the updated index back to the registry (write locally only)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("runs.json"),
        help="Output file path (default: runs.json)",
    )
    args = parser.parse_args()

    # Resolve token from args or environment
    token = args.token or os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN") or ""
    if not token:
        print("ERROR: No token provided. Use --token, GITLAB_TOKEN, or CI_JOB_TOKEN.", file=sys.stderr)
        sys.exit(1)

    api_url = f"{args.gitlab_url.rstrip('/')}/api/v4"
    headers = _get_auth_headers(token, args.token_type)

    print("Downloading existing runs index...", file=sys.stderr)
    manifest = download_index(api_url, args.project_id, headers)
    print(f"Existing index has {len(manifest.get('runs', []))} run(s).", file=sys.stderr)

    if args.current_run is not None:
        run_metadata = _load_current_run(args.current_run)
        if run_metadata is not None:
            manifest = add_run(manifest, run_metadata, api_url, args.project_id, max_runs=args.max_runs)
            print(f"Added current run. Index now has {manifest['total_runs']} run(s).", file=sys.stderr)
            if not args.no_upload:
                if upload_index(api_url, args.project_id, headers, manifest):
                    print("Index uploaded to the registry.", file=sys.stderr)
                else:
                    print("WARNING: Index upload failed. Local manifest is still written.", file=sys.stderr)
    else:
        print("No --current-run given. Writing the index as-is.", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest written to {args.output} ({manifest['total_runs']} runs)", file=sys.stderr)


if __name__ == "__main__":
    main()
