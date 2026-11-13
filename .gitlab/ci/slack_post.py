#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Post a markdown file to Slack.

Usage:
    slack_post.py FILE.md

Posts {"text": ...} to $SLACK_WEBHOOK_URL. For an incoming webhook (hooks.slack.com/services/...) the markdown becomes
Slack mrkdwn (links, bold, headings as bold lines), without link previews. A Workflow Builder webhook
(.../triggers/...) shows its variables as plain text, so it gets plain text: a line's only link keeps its URL,
several become their text; headings and bold become Unicode bold; list items get bullets.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

LINK_RE = r"\[([^\]]*)\]\(([^)\s]+)\)"


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_slack(markdown: str) -> str:
    """Markdown to Slack mrkdwn: <url|text> links, *bold* (headings too), &<> escaped."""
    out = []
    for part in re.split(r"(\[[^\]]*\]\([^)\s]+\))", markdown):
        link = re.fullmatch(LINK_RE, part)
        if link:
            out.append(f"<{link[2]}|{esc(link[1]).replace('|', '¦')}>")
        else:
            part = re.sub(r"(?m)^#+ (.+)$", r"*\1*", esc(part))
            out.append(re.sub(r"\*\*(.+?)\*\*", r"*\1*", part))
    return "".join(out)


def bold(text: str) -> str:
    """Unicode sans-serif bold: plain text that still looks bold. Slack search does not match it."""
    def char(c: str) -> str:
        if "A" <= c <= "Z":
            return chr(0x1D5D4 + ord(c) - ord("A"))
        if "a" <= c <= "z":
            return chr(0x1D5EE + ord(c) - ord("a"))
        if "0" <= c <= "9":
            return chr(0x1D7EC + ord(c) - ord("0"))
        return c
    return "".join(map(char, text))


def to_plain(markdown: str) -> str:
    """Markdown to plain text: a line's only link becomes "label - url -", several links become their text; headings
    and **bold** become Unicode bold; list items get • and ◦ bullets."""
    def line(text: str) -> str:
        links = re.findall(LINK_RE, text)
        if len(links) == 1:   # one link: keep its URL, as "label - url -"
            return re.sub(LINK_RE, lambda m: f"{m[1]} - {m[2]} -", text).replace(" -:", ":")
        return re.sub(LINK_RE, r"\1", text)

    text = "\n".join(map(line, markdown.split("\n")))
    text = re.sub(r"(?m)^#+ (.+)$", lambda m: bold(m[1]), text)
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: bold(m[1]), text)
    text = re.sub(r"(?m)^- ", "• ", text)
    return re.sub(r"(?m)^ {2,}- ", "    ◦ ", text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Post a markdown file to Slack ($SLACK_WEBHOOK_URL)")
    parser.add_argument("file", help="Markdown file")
    args = parser.parse_args()

    markdown = open(args.file, encoding="utf-8").read()
    webhook = os.environ["SLACK_WEBHOOK_URL"]
    workflow = "/triggers/" in webhook
    text = (to_plain(markdown) if workflow else to_slack(markdown)).rstrip() + "\n"
    payload = {"text": text}
    if not workflow:   # a workflow takes only its variables
        payload.update(unfurl_links=False, unfurl_media=False)
    req = urllib.request.Request(webhook, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        sys.exit(f"ERROR: Slack answered HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}")
    print("Posted to Slack")


if __name__ == "__main__":
    main()
