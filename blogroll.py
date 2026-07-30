#!/usr/bin/env python3
"""Shared helpers for building the articles OPML blogroll.

The blogroll is *cumulative*: ``articles.opml`` is the accumulated record of
every article ever linked from the link blog, not a snapshot of whatever the
RSS feed happens to be serving today. The feed only carries the most recent 25
posts, so regenerating from scratch would silently evict older entries.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

OPML_TITLE = "Tony Meyer's Articles"
BLOG_DOMAIN = "tonyandrewmeyer.blog"
USER_AGENT = "Mozilla/5.0 (compatible; BlogrollBot/1.0; +https://github.com/tonyandrewmeyer)"
REQUEST_TIMEOUT = 15
MAX_TITLE_BYTES = 51200

# Links that appear in post bodies but are never the article being shared.
_NON_ARTICLE_HOSTS = frozenset(
    {
        "micro.blog",
        "www.micro.blog",
    }
)


class LinkExtractor(HTMLParser):
    """Collect the ``href`` of every anchor in a fragment of HTML."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for attr, value in attrs:
            if attr == "href" and value:
                self.links.append(value)


class TitleExtractor(HTMLParser):
    """Collect the text content of the document's ``<title>`` element."""

    def __init__(self):
        super().__init__()
        self._in_title = False
        self._parts: list[str] = []
        self.done = False

    def handle_starttag(self, tag, attrs):
        if tag == "title" and not self.done:
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self.done = True

    def handle_data(self, data):
        if self._in_title:
            self._parts.append(data)

    @property
    def title(self) -> str | None:
        text = normalise_whitespace("".join(self._parts))
        return text or None


class PostBodyLinkExtractor(HTMLParser):
    """Collect anchors from a micro.blog post body only.

    Scopes extraction to ``<section class="e-content post-body">`` so theme
    chrome (navigation, footer, webmention links) is never mistaken for the
    article being shared.
    """

    def __init__(self):
        super().__init__()
        self._section_depth = 0
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_map = dict(attrs)
        if tag == "section":
            if self._section_depth:
                self._section_depth += 1
            elif "e-content" in (attrs_map.get("class") or "").split():
                self._section_depth = 1
            return
        if self._section_depth and tag == "a" and attrs_map.get("href"):
            self.links.append(attrs_map["href"])

    def handle_endtag(self, tag):
        if tag == "section" and self._section_depth:
            self._section_depth -= 1


def normalise_whitespace(text: str) -> str:
    """Collapse runs of whitespace so titles stay on one line."""
    return re.sub(r"\s+", " ", text).strip()


def detect_encoding(response: requests.Response, content: bytes) -> str:
    """Work out the character encoding of an HTML response.

    ``requests`` falls back to ISO-8859-1 whenever a ``text/html`` response
    carries no ``charset``, which mangles UTF-8 titles. Prefer the charset the
    server declared, then the document's own ``<meta charset>``, then UTF-8.
    """
    content_type = response.headers.get("Content-Type", "")
    match = re.search(r"charset=[\"']?([\w-]+)", content_type, re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", content[:4096], re.IGNORECASE)
    if match:
        return match.group(1).decode("ascii", errors="ignore")

    return "utf-8"


def title_from_url(url: str) -> str:
    """Derive a human-readable title from a URL when the page cannot be read.

    Never returns empty: an article with an imperfect title is far better than
    an article silently dropped from the blogroll.
    """
    parsed = urlparse(url)
    slug = parsed.path.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.IGNORECASE)
    if slug:
        return normalise_whitespace(slug.replace("-", " ").replace("_", " ")).title()
    return parsed.netloc or url


def fetch_title(url: str) -> str:
    """Fetch the ``<title>`` of a remote page, falling back to the URL slug.

    Always returns a usable title. Fetch failures (403, 404, timeouts) are
    reported but never cause the article to be dropped.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        print(f"Skipping non-HTTP(S) URL: {url}", file=sys.stderr)
        return title_from_url(url)

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        response.raise_for_status()

        # The title lives in <head>; reading the whole document is wasteful.
        content = b""
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) >= MAX_TITLE_BYTES:
                break

        text = content.decode(detect_encoding(response, content), errors="replace")
        parser = TitleExtractor()
        parser.feed(text)
        if parser.title:
            return parser.title
    except (requests.RequestException, UnicodeDecodeError, ValueError) as e:
        print(f"Could not fetch title for {url} ({e}); using URL slug", file=sys.stderr)
        return title_from_url(url)

    print(f"No <title> found at {url}; using URL slug", file=sys.stderr)
    return title_from_url(url)


def is_shareable_link(link: str) -> bool:
    """Report whether a link looks like an article being shared."""
    lowered = link.lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    host = urlparse(lowered).netloc
    if host in _NON_ARTICLE_HOSTS:
        return False
    return not (host == BLOG_DOMAIN or host.endswith(f".{BLOG_DOMAIN}"))


def first_outgoing_link(html: str) -> str | None:
    """Return the first outgoing article link in a fragment of post HTML."""
    parser = LinkExtractor()
    try:
        parser.feed(html)
    except AssertionError as e:  # HTMLParser raises these on malformed markup.
        print(f"Error parsing post HTML: {e}", file=sys.stderr)
        return None

    for link in parser.links:
        if is_shareable_link(link):
            return link
    return None


def first_outgoing_link_in_page(html: str) -> str | None:
    """Return the first outgoing article link in a full micro.blog post page."""
    parser = PostBodyLinkExtractor()
    try:
        parser.feed(html)
    except AssertionError as e:
        print(f"Error parsing post page: {e}", file=sys.stderr)
        return None

    for link in parser.links:
        if is_shareable_link(link):
            return link
    return None


def load_existing(path: str) -> tuple[dict[str, dict[str, str]], str | None]:
    """Load an existing OPML file into a URL-keyed mapping of outline attributes.

    Returns the entries and the file's existing ``dateCreated``, or an empty
    mapping if the file does not exist or cannot be parsed.
    """
    try:
        tree = ET.parse(path)  # noqa: S314 - our own file, regenerated from scratch on error.
    except FileNotFoundError:
        return {}, None
    except ET.ParseError as e:
        print(f"Warning: could not parse {path} ({e}); starting fresh", file=sys.stderr)
        return {}, None

    root = tree.getroot()
    date_created_el = root.find("./head/dateCreated")
    date_created = date_created_el.text if date_created_el is not None else None

    entries: dict[str, dict[str, str]] = {}
    for outline in root.iterfind("./body/outline"):
        url = outline.get("url")
        if url:
            entries[url] = dict(outline.attrib)
    return entries, date_created


_UNDATED = datetime.min.replace(tzinfo=UTC)


def _sort_key(entry: dict[str, str]) -> tuple[int, datetime]:
    """Sort key for newest-first ordering, with undated entries last.

    Callers sort in reverse, so undated entries take the *lower* rank in order
    to end up at the bottom of the file.
    """
    created = entry.get("created")
    if not created:
        return (0, _UNDATED)
    try:
        parsed = parsedate_to_datetime(created)
    except (TypeError, ValueError):
        return (0, _UNDATED)
    if parsed.tzinfo is None:
        # Undated-but-parseable: assume UTC so keys stay mutually comparable.
        parsed = parsed.replace(tzinfo=UTC)
    return (1, parsed)


def build_opml(entries: dict[str, dict[str, str]], date_created: str) -> ET.ElementTree:
    """Build the OPML document for the given entries, newest first."""
    root = ET.Element("opml", version="2.0")
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = OPML_TITLE
    ET.SubElement(head, "dateCreated").text = date_created

    body = ET.SubElement(root, "body")
    for entry in sorted(entries.values(), key=_sort_key, reverse=True):
        outline = ET.SubElement(body, "outline")
        for name in ("text", "type", "url", "created"):
            if entry.get(name):
                outline.set(name, entry[name])

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return tree


def _serialise(tree: ET.ElementTree) -> bytes:
    return ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True) + b"\n"


def write_if_changed(
    path: str, entries: dict[str, dict[str, str]], previous_date: str | None
) -> bool:
    """Write the OPML file, but only if the article list actually changed.

    ``dateCreated`` is deliberately excluded from the comparison. Refreshing it
    on every run produced a daily no-op commit that said nothing except that
    the job had run.
    """
    now = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")

    if previous_date is not None:
        unchanged = _serialise(build_opml(entries, previous_date))
        try:
            with open(path, "rb") as f:
                if f.read() == unchanged:
                    print(f"No changes to {path}; leaving it alone", file=sys.stderr)
                    return False
        except FileNotFoundError:
            pass

    with open(path, "wb") as f:
        f.write(_serialise(build_opml(entries, now)))
    return True
