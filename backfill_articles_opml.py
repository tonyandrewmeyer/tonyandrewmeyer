#!/usr/bin/env python3
"""One-off backfill of articles.opml from the full micro.blog archive.

The RSS feed only exposes the 25 most recent posts, so the blogroll built from
it starts in mid-2026. This walks ``/archive/index.json`` — every post ever —
fetches each post page, and merges the outgoing links it finds into
``articles.opml``.

Safe to re-run: existing entries are never re-fetched or overwritten, so an
interrupted run simply picks up where it left off.

    python backfill_articles_opml.py [--limit N] [--delay SECONDS]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

import requests

import blogroll

ARCHIVE_URL = "https://tonyandrewmeyer.blog/archive/index.json"
OUTPUT_FILE = "articles.opml"


def fetch_archive(url: str) -> list[dict]:
    """Fetch the archive feed listing every post on the blog."""
    print(f"Fetching archive from {url}...", file=sys.stderr)
    response = requests.get(
        url, headers={"User-Agent": blogroll.USER_AGENT}, timeout=blogroll.REQUEST_TIMEOUT
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    print(f"Archive lists {len(items)} posts", file=sys.stderr)
    return items


def fetch_post_html(url: str) -> str | None:
    """Fetch a single post page."""
    try:
        response = requests.get(
            url, headers={"User-Agent": blogroll.USER_AGENT}, timeout=blogroll.REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Could not fetch post {url}: {e}", file=sys.stderr)
        return None
    return response.content.decode(
        blogroll.detect_encoding(response, response.content), errors="replace"
    )


def to_rfc2822(date_published: str) -> str | None:
    """Convert an ISO 8601 timestamp from the archive into OPML's date format."""
    try:
        parsed = datetime.fromisoformat(date_published)
    except (TypeError, ValueError):
        return None
    return parsed.strftime("%a, %d %b %Y %H:%M:%S %z")


def backfill(limit: int | None, delay: float) -> None:
    """Merge every archived post's outgoing link into the articles OPML."""
    entries, previous_date = blogroll.load_existing(OUTPUT_FILE)
    print(f"Loaded {len(entries)} existing articles", file=sys.stderr)

    posts = fetch_archive(ARCHIVE_URL)
    if limit is not None:
        posts = posts[:limit]

    known_urls = set(entries)
    added = 0
    no_link = 0
    unreachable = 0

    for index, post in enumerate(posts, start=1):
        post_url = post.get("url")
        if not post_url:
            continue

        print(f"[{index}/{len(posts)}] {post_url}", file=sys.stderr)
        html = fetch_post_html(post_url)
        if html is None:
            unreachable += 1
            continue

        url = blogroll.first_outgoing_link_in_page(html)
        if not url:
            no_link += 1
        elif url not in known_urls:
            article = {"text": blogroll.fetch_title(url), "type": "link", "url": url}
            created = to_rfc2822(post.get("date_published", ""))
            if created:
                article["created"] = created
            entries[url] = article
            known_urls.add(url)
            added += 1
            print(f"  + {article['text']}", file=sys.stderr)

        if delay:
            time.sleep(delay)

    print(
        f"\nBackfill complete: {added} added, {no_link} post(s) with no outgoing link, "
        f"{unreachable} unreachable. {len(entries)} articles in the blogroll.",
        file=sys.stderr,
    )
    blogroll.write_if_changed(OUTPUT_FILE, entries, previous_date)


def main() -> None:
    """Parse arguments and run the backfill."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="only process the N most recent posts")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="seconds to wait between posts (default: 0.2)",
    )
    args = parser.parse_args()
    backfill(args.limit, args.delay)


if __name__ == "__main__":
    main()
