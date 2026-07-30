#!/usr/bin/env python3
"""Update the articles OPML from the tonyandrewmeyer.blog RSS feed.

Each post on the link blog quotes and links to an article elsewhere; it is that
outgoing link, not the post itself, that belongs in the blogroll.

The feed only carries the 25 most recent posts, so this script *merges* what it
finds into the existing ``articles.opml`` rather than rewriting it. Articles
that have scrolled out of the feed stay in the blogroll, and their titles are
never re-fetched.
"""

from __future__ import annotations

import sys

import feedparser

import blogroll

BLOG_RSS_FEED = "https://tonyandrewmeyer.blog/feed"
OUTPUT_FILE = "articles.opml"


def entry_html(entry) -> str:
    """Return the HTML content of a feed entry."""
    if getattr(entry, "content", None):
        return entry.content[0].value
    return getattr(entry, "summary", "")


def update_articles_opml(feed_url: str, output_file: str) -> bool:
    """Merge outgoing links from the feed into the articles OPML.

    Returns whether the file was modified.
    """
    entries, previous_date = blogroll.load_existing(output_file)
    print(f"Loaded {len(entries)} existing articles from {output_file}", file=sys.stderr)

    print(f"Fetching {feed_url}...", file=sys.stderr)
    feed = feedparser.parse(feed_url)
    if feed.bozo:
        print(f"Warning: feed parsing had issues: {feed.bozo_exception}", file=sys.stderr)
    print(f"Found {len(feed.entries)} blog posts", file=sys.stderr)

    added = 0
    no_link = 0

    for entry in feed.entries:
        html = entry_html(entry)
        url = blogroll.first_outgoing_link(html) if html else None

        if not url:
            no_link += 1
            continue

        if url in entries:
            # Already recorded: keep the title we fetched the first time.
            continue

        article = {
            "text": blogroll.fetch_title(url),
            "type": "link",
            "url": url,
        }
        published = getattr(entry, "published", None)
        if published:
            article["created"] = published

        entries[url] = article
        added += 1
        print(f"Added: {article['text']} <{url}>", file=sys.stderr)

    print(
        f"{added} new article(s), {no_link} post(s) with no outgoing link, "
        f"{len(entries)} in the blogroll",
        file=sys.stderr,
    )
    return blogroll.write_if_changed(output_file, entries, previous_date)


if __name__ == "__main__":
    update_articles_opml(BLOG_RSS_FEED, OUTPUT_FILE)
