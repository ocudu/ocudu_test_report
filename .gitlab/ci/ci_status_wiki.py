#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Add today's CI status summary on top of the project's wiki page, one `## ` section per day.

Usage:
    ci_status_wiki.py SUMMARY.md [--days 30] [--slug CI-status]

SUMMARY.md starts with its own `## ` heading (ocudu_tools' summary.py). A section with the same heading, from an
earlier run today, is replaced. Only the newest --days sections are kept. Needs $GITLAB_TOKEN (Developer, to edit the
wiki), $CI_API_V4_URL and $CI_PROJECT_ID.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TITLE = "CI status"


def sections(content: str) -> list[str]:
    """The page's `## ` sections, in order; text before the first one is dropped."""
    parts = re.split(r"(?m)^(?=## )", content)
    return [p.strip() + "\n" for p in parts if p.startswith("## ")]


def merge(page: str, today: str, days: int) -> str:
    heading = today.splitlines()[0]
    older = [s for s in sections(page) if s.splitlines()[0] != heading]
    return "\n".join([today.strip() + "\n"] + older[:days - 1])


def request(method: str, url: str, token: str, data: dict | None = None) -> dict | None:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={"PRIVATE-TOKEN": token})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and method == "GET":
            return None
        raise SystemExit(f"ERROR: {method} {url}: HTTP {exc.code} {exc.read().decode(errors='replace')[:300]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("summary", help="Today's summary, markdown starting with a `## ` heading")
    parser.add_argument("--days", type=int, default=30, help="Sections kept, today's included (default 30)")
    parser.add_argument("--slug", default="CI-status", help="Wiki page slug (default: CI-status)")
    args = parser.parse_args()

    today = open(args.summary, encoding="utf-8").read()
    if not today.startswith("## "):
        sys.exit("ERROR: the summary must start with a `## ` heading")
    token = os.environ["GITLAB_TOKEN"]
    wikis = f"{os.environ['CI_API_V4_URL']}/projects/{os.environ['CI_PROJECT_ID']}/wikis"

    page = request("GET", f"{wikis}/{args.slug}", token)
    content = merge(page["content"] if page else "", today, args.days)
    if page:
        request("PUT", f"{wikis}/{args.slug}", token, {"title": TITLE, "content": content})
    else:
        request("POST", wikis, token, {"title": TITLE, "content": content})
    print(f"Wiki page {args.slug}: {len(sections(content))} days")


if __name__ == "__main__":
    main()
