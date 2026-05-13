#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Download XUnit artifacts from GitLab jobs, pipelines, or pipeline schedules.

Usage:
    fetch-xunit --suite "A=<job-url>" --suite "B=<pipeline-url>" --suite "C=<schedule-api-url>" -o ./artifacts

Schedule API URLs (https://gitlab.example.com/api/v4/projects/<id>/pipeline_schedules/<id>)
resolve to the latest pipeline run automatically. Requires --token or GITLAB_TOKEN env var.
"""

import argparse
import io
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(2)

# Matches: https://gitlab.example.com/group/sub/project/-/jobs/123
#      or: https://gitlab.example.com/group/sub/project/-/pipelines/123
_URL_RE = re.compile(r"(https?://[^/]+)/(.+?)/-/(jobs|pipelines)/(\d+)/?$")
_KIND_MAP = {"jobs": "job", "pipelines": "pipeline"}

# Matches the GitLab API URL for a schedule:
#   https://gitlab.example.com/api/v4/projects/<project_id>/pipeline_schedules/<schedule_id>
_API_SCHEDULE_RE = re.compile(r"(https?://[^/]+)/api/v4/projects/([^/]+)/pipeline_schedules/(\d+)/?$")

# XUnit files we recognize inside an artifacts zip
_XUNIT_RE = re.compile(r"(^|/)([^/]+_xunit\.xml|out\.xml)$")


class _ParsedURL(NamedTuple):
    base: str
    project: str
    kind: str
    id_: int
    url: str


def _parse_url(raw: str) -> _ParsedURL:
    url = raw.rstrip("/")
    m = _API_SCHEDULE_RE.match(url)
    if m:
        return _ParsedURL(m.group(1), m.group(2), "schedule", int(m.group(3)), url)
    m = _URL_RE.match(url)
    if not m:
        raise ValueError(f"Cannot parse as GitLab job/pipeline/schedule API URL: {raw!r}")
    return _ParsedURL(m.group(1), m.group(2), _KIND_MAP[m.group(3)], int(m.group(4)), url)


class _Client:
    def __init__(self, base_url: str, project_path: str, token: str = ""):
        encoded = quote(project_path, safe="")
        self._root = f"{base_url}/api/v4/projects/{encoded}"
        self._session = requests.Session()
        if token:
            self._session.headers["PRIVATE-TOKEN"] = token

    def _get(self, path: str, **kwargs) -> requests.Response:
        r = self._session.get(f"{self._root}/{path}", **kwargs)
        r.raise_for_status()
        return r

    def pipeline_jobs(self, pipeline_id: int) -> list:
        """Return all jobs for a pipeline, handling pagination."""
        jobs, page = [], 1
        while True:
            batch = self._get(
                f"pipelines/{pipeline_id}/jobs",
                params={"per_page": 100, "page": page},
            ).json()
            if not batch:
                break
            jobs.extend(batch)
            page += 1
        return jobs

    def latest_scheduled_pipeline(self, schedule_id: int) -> tuple[int, str]:
        """Return (pipeline_id, web_url) for the most recent run of a pipeline schedule."""
        pipelines = self._get(
            f"pipeline_schedules/{schedule_id}/pipelines",
            params={"per_page": 1, "order_by": "id", "sort": "desc"},
        ).json()
        if not pipelines:
            raise ValueError(f"No pipelines found for schedule {schedule_id}")
        p = pipelines[0]
        return p["id"], p["web_url"]

    def artifacts_zip(self, job_id: int) -> bytes:
        """Download the full artifacts zip for a job."""
        return bytes(self._get(f"jobs/{job_id}/artifacts").content)


def _extract_xunits(zip_bytes: bytes) -> list[tuple[str, bytes]]:
    """Return [(filename, data)] for every XUnit file found in the zip."""
    results = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if _XUNIT_RE.search(name):
                results.append((Path(name).name, zf.read(name)))
    return results


def _safe_name(name: str) -> str:
    """Strip characters that are invalid or problematic in file/directory names."""
    return re.sub(r"[^\w\-.]", "_", name).strip("_. ")


def _fetch_job(client: _Client, job_id: int, report_name: str, suite_dir: Path) -> list[tuple[str, Path]]:
    """Download artifacts for one job into suite_dir. report_name is used as the xunit-report suite label."""
    print(f"  job {job_id} ({report_name}) — downloading artifacts ...", end=" ", flush=True)
    try:
        zip_bytes = client.artifacts_zip(job_id)
    except requests.HTTPError as exc:
        print(f"skipped ({exc})")
        return []

    files = _extract_xunits(zip_bytes)
    if not files:
        print("no XUnit files found")
        return []

    print(f"{len(files)} XUnit file(s) found")
    saved = []
    for filename, data in files:
        stem = Path(filename).stem
        out_name = report_name if len(files) == 1 else f"{report_name} ({stem})"
        out_path = suite_dir / f"{_safe_name(report_name)}_{_safe_name(stem)}.xml"
        out_path.write_bytes(data)
        print(f"    saved {out_path}")
        saved.append((out_name, out_path))

    return saved


def _fetch_suite(client: _Client, name: str, ref: _ParsedURL, suite_dir: Path) -> list[tuple[str, Path]]:
    """Resolve a suite entry and download its XUnit artifacts. Returns list of (name, path) saved."""
    kind, id_ = ref.kind, ref.id_
    if kind == "schedule":
        print(f"'{name}' — schedule {id_}, resolving latest pipeline ...")
        try:
            id_, pipeline_url = client.latest_scheduled_pipeline(id_)
            print(f"  latest pipeline: {id_} ({pipeline_url})")
            kind = "pipeline"
            (suite_dir / "_url.txt").write_text(pipeline_url, encoding="utf-8")
        except (requests.HTTPError, ValueError) as exc:
            print(f"  error fetching schedule: {exc}")
            return []
    else:
        (suite_dir / "_url.txt").write_text(ref.url, encoding="utf-8")

    if kind == "job":
        print(f"'{name}' — job {id_}")
        return _fetch_job(client, id_, name, suite_dir)

    print(f"'{name}' — pipeline {id_}")
    try:
        jobs = client.pipeline_jobs(id_)
    except requests.HTTPError as exc:
        print(f"  error fetching pipeline jobs: {exc}")
        return []
    print(f"  {len(jobs)} jobs in pipeline")
    saved = []
    for job in jobs:
        saved.extend(_fetch_job(client, job["id"], job["name"], suite_dir))
    return saved


def main():
    """Entry point: parse arguments and download XUnit artifacts from GitLab."""
    parser = argparse.ArgumentParser(description="Download XUnit artifacts from GitLab jobs or pipelines")
    parser.add_argument(
        "--suite",
        metavar="NAME=URL",
        action="append",
        required=True,
        help="Suite label and GitLab URL, repeatable",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directory to save downloaded XUnit files (default: ./artifacts)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITLAB_TOKEN", ""),
        metavar="TOKEN",
        help="GitLab personal/project access token (default: $GITLAB_TOKEN)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_saved: list[tuple[str, Path]] = []
    suite_order: list[str] = []

    for entry in args.suite:
        if "=" not in entry:
            parser.error(f"Expected NAME=URL, got: {entry!r}")
        name, _, url = entry.partition("=")
        name, url = name.strip(), url.strip()
        try:
            ref = _parse_url(url)
        except ValueError as exc:
            parser.error(str(exc))
        client = _Client(ref.base, ref.project, token=args.token)
        suite_dir = args.output_dir / _safe_name(name)
        suite_dir.mkdir(parents=True, exist_ok=True)
        suite_order.append(_safe_name(name))
        all_saved.extend(_fetch_suite(client, name, ref, suite_dir))

    (args.output_dir / "_order.txt").write_text("\n".join(suite_order), encoding="utf-8")

    if not all_saved:
        print("\nNo XUnit files downloaded.")
        return

    print("\nDownloaded files.")


if __name__ == "__main__":
    main()
