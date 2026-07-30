"""Tests for the blogroll parsing and merging logic."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import ClassVar

import pytest

import blogroll

# Spelled out so linters do not mistake the intent: reproducing the exact
# character that used to arrive mangled is the point of these tests.
EN_DASH = "\N{EN DASH}"


class FakeResponse:
    """Minimal stand-in for ``requests.Response`` for encoding detection."""

    def __init__(self, content_type: str = ""):
        self.headers = {"Content-Type": content_type} if content_type else {}


class TestNormaliseWhitespace:
    """Titles must collapse to a single line."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Hello  world  ", "Hello world"),
            ("Line\nbreak", "Line break"),
            ("Tabs\t\tand\nnewlines\n", "Tabs and newlines"),
            ("", ""),
        ],
    )
    def test_collapses_whitespace(self, raw, expected):
        assert blogroll.normalise_whitespace(raw) == expected


class TestDetectEncoding:
    """Encoding detection is what keeps UTF-8 titles from turning into mojibake."""

    def test_prefers_declared_charset(self):
        response = FakeResponse("text/html; charset=iso-8859-1")
        assert blogroll.detect_encoding(response, b"") == "iso-8859-1"

    def test_handles_quoted_charset(self):
        response = FakeResponse('text/html; charset="Shift_JIS"')
        assert blogroll.detect_encoding(response, b"") == "Shift_JIS"

    def test_falls_back_to_meta_charset(self):
        response = FakeResponse("text/html")
        content = b'<html><head><meta charset="windows-1252">'
        assert blogroll.detect_encoding(response, content) == "windows-1252"

    def test_defaults_to_utf8_when_nothing_declared(self):
        # requests would report ISO-8859-1 here, which is what mangled titles.
        response = FakeResponse("text/html")
        assert blogroll.detect_encoding(response, b"<html><head><title>Hi") == "utf-8"

    def test_ignores_meta_charset_beyond_the_head(self):
        response = FakeResponse("text/html")
        content = (
            b"<html><head><title>x</title></head>" + b"." * 5000 + b'<meta charset="latin-1">'
        )
        assert blogroll.detect_encoding(response, content) == "utf-8"

    def test_utf8_default_decodes_an_en_dash(self):
        """The GarageBand regression: an en dash must survive round-tripping."""
        title = f"The surprising richness of GarageBand {EN_DASH} Unsung"
        content = f"<html><head><title>{title}</title>".encode()
        response = FakeResponse("text/html")
        decoded = content.decode(blogroll.detect_encoding(response, content))
        parser = blogroll.TitleExtractor()
        parser.feed(decoded)
        assert parser.title == title


class TestTitleExtractor:
    """The document title drives the blogroll entry text."""

    def test_extracts_title(self):
        parser = blogroll.TitleExtractor()
        parser.feed("<html><head><title>A Post</title></head><body>ignored</body></html>")
        assert parser.title == "A Post"

    def test_resolves_character_references(self):
        parser = blogroll.TitleExtractor()
        parser.feed("<title>Cats &amp; Dogs &#8212; A Study</title>")
        assert parser.title == "Cats & Dogs — A Study"

    def test_joins_a_split_title(self):
        parser = blogroll.TitleExtractor()
        parser.feed("<title>Part one &amp; part two</title>")
        assert parser.title == "Part one & part two"

    def test_collapses_multiline_title(self):
        parser = blogroll.TitleExtractor()
        parser.feed("<title>\n  Wrapped\n  Title\n</title>")
        assert parser.title == "Wrapped Title"

    def test_ignores_later_titles(self):
        parser = blogroll.TitleExtractor()
        parser.feed("<title>First</title><svg><title>Tooltip</title></svg>")
        assert parser.title == "First"

    def test_returns_none_when_absent(self):
        parser = blogroll.TitleExtractor()
        parser.feed("<html><head></head></html>")
        assert parser.title is None

    def test_returns_none_when_blank(self):
        parser = blogroll.TitleExtractor()
        parser.feed("<title>   </title>")
        assert parser.title is None


class TestTitleFromUrl:
    """The slug fallback must always produce something usable."""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://example.com/my-great-article", "My Great Article"),
            ("https://example.com/my_great_article", "My Great Article"),
            ("https://example.com/2026/07/some-post/", "Some Post"),
            ("https://example.com/posts/thing.html", "Thing"),
            ("https://example.com/posts/thing.php", "Thing"),
        ],
    )
    def test_derives_title_from_slug(self, url, expected):
        assert blogroll.title_from_url(url) == expected

    def test_falls_back_to_host_for_bare_urls(self):
        assert blogroll.title_from_url("https://example.com/") == "example.com"
        assert blogroll.title_from_url("https://example.com") == "example.com"

    def test_never_returns_empty(self):
        for url in ("https://example.com", "https://example.com/", "https://example.com/a"):
            assert blogroll.title_from_url(url)


class TestIsShareableLink:
    """Only genuine outgoing article links belong in the blogroll."""

    @pytest.mark.parametrize(
        "link",
        [
            "https://example.com/post",
            "http://example.com/post",
            "https://sub.example.com/post",
        ],
    )
    def test_accepts_external_links(self, link):
        assert blogroll.is_shareable_link(link)

    @pytest.mark.parametrize(
        "link",
        [
            "https://tonyandrewmeyer.blog/2026/07/25/a-post.html",
            "https://www.tonyandrewmeyer.blog/a-post",
            "https://micro.blog/tonyandrewmeyer",
            "mailto:someone@example.com",
            "javascript:void(0)",
            "#footnote",
            "/relative/path",
            "../another",
        ],
    )
    def test_rejects_self_and_non_article_links(self, link):
        assert not blogroll.is_shareable_link(link)

    def test_does_not_reject_lookalike_domains(self):
        """Substring matching would wrongly discard these."""
        assert blogroll.is_shareable_link("https://nottonyandrewmeyer.blog/post")
        assert blogroll.is_shareable_link("https://example.com/tonyandrewmeyer.blog/post")


class TestFirstOutgoingLink:
    """Feed entries carry the post body as an HTML fragment."""

    def test_finds_the_quoted_article(self):
        html = (
            "<blockquote><p><a href='https://lucumr.pocoo.org/2026/7/24/codeberg-divides/'>"
            "There are serious questions</a></p></blockquote><p>Commentary.</p>"
        )
        assert blogroll.first_outgoing_link(html) == (
            "https://lucumr.pocoo.org/2026/7/24/codeberg-divides/"
        )

    def test_skips_self_links_before_the_article(self):
        html = (
            "<p><a href='https://tonyandrewmeyer.blog/earlier'>earlier</a> and "
            "<a href='https://example.com/article'>the article</a></p>"
        )
        assert blogroll.first_outgoing_link(html) == "https://example.com/article"

    def test_returns_none_without_outgoing_links(self):
        html = "<p>Just some thoughts, no links.</p>"
        assert blogroll.first_outgoing_link(html) is None

    def test_returns_none_for_empty_content(self):
        assert blogroll.first_outgoing_link("") is None


class TestFirstOutgoingLinkInPage:
    """Backfill reads whole post pages, so theme chrome must be excluded."""

    PAGE = """
    <html><body>
      <header><a href="https://external-nav.example/about">About</a></header>
      <article class="h-entry post">
        <section class="e-content post-body">
          <blockquote><p><a href="https://example.com/the-article">Quote</a></p></blockquote>
        </section>
      </article>
      <footer><a href="https://micro.blog/tonyandrewmeyer">micro.blog</a>
        <a href="https://external-footer.example/">Footer</a></footer>
    </body></html>
    """

    def test_ignores_links_outside_the_post_body(self):
        assert blogroll.first_outgoing_link_in_page(self.PAGE) == "https://example.com/the-article"

    def test_handles_nested_sections(self):
        page = """
        <section class="e-content post-body">
          <section><p><a href="https://example.com/nested">Nested</a></p></section>
        </section>
        <footer><a href="https://chrome.example/">Chrome</a></footer>
        """
        assert blogroll.first_outgoing_link_in_page(page) == "https://example.com/nested"

    def test_stops_collecting_after_the_body_closes(self):
        page = """
        <section class="e-content post-body"><p>No links here.</p></section>
        <footer><a href="https://chrome.example/">Chrome</a></footer>
        """
        assert blogroll.first_outgoing_link_in_page(page) is None

    def test_returns_none_without_a_post_body(self):
        page = "<html><body><a href='https://example.com/x'>x</a></body></html>"
        assert blogroll.first_outgoing_link_in_page(page) is None


class TestLoadExisting:
    """Existing entries are the record that must never be lost."""

    def test_loads_entries_keyed_by_url(self, tmp_path):
        path = tmp_path / "articles.opml"
        path.write_text(
            """<?xml version='1.0' encoding='utf-8'?>
<opml version="2.0">
  <head><title>T</title><dateCreated>Sat, 25 Jul 2026 19:51:29 GMT</dateCreated></head>
  <body>
    <outline text="One" type="link" url="https://example.com/1"
      created="Mon, 11 May 2026 08:00:00 +1300" />
    <outline text="Two" type="link" url="https://example.com/2" />
  </body>
</opml>""",
            encoding="utf-8",
        )
        entries, date_created = blogroll.load_existing(str(path))
        assert date_created == "Sat, 25 Jul 2026 19:51:29 GMT"
        assert set(entries) == {"https://example.com/1", "https://example.com/2"}
        assert entries["https://example.com/1"]["text"] == "One"

    def test_missing_file_is_not_an_error(self, tmp_path):
        entries, date_created = blogroll.load_existing(str(tmp_path / "absent.opml"))
        assert entries == {}
        assert date_created is None

    def test_malformed_file_starts_fresh(self, tmp_path):
        path = tmp_path / "broken.opml"
        path.write_text("<opml><body><outline", encoding="utf-8")
        entries, date_created = blogroll.load_existing(str(path))
        assert entries == {}
        assert date_created is None

    def test_skips_outlines_without_a_url(self, tmp_path):
        path = tmp_path / "articles.opml"
        path.write_text(
            "<opml version='2.0'><head/><body>"
            "<outline text='Category' />"
            "<outline text='Real' url='https://example.com/1' />"
            "</body></opml>",
            encoding="utf-8",
        )
        entries, _ = blogroll.load_existing(str(path))
        assert list(entries) == ["https://example.com/1"]


class TestBuildOpml:
    """Ordering keeps the file's diffs readable."""

    def test_sorts_newest_first(self):
        entries = {
            "https://example.com/old": {
                "text": "Old",
                "url": "https://example.com/old",
                "created": "Mon, 11 May 2026 08:00:00 +1300",
            },
            "https://example.com/new": {
                "text": "New",
                "url": "https://example.com/new",
                "created": "Sat, 25 Jul 2026 11:41:41 +1300",
            },
        }
        root = blogroll.build_opml(entries, "now").getroot()
        assert [o.get("text") for o in root.iterfind("./body/outline")] == ["New", "Old"]

    def test_undated_entries_sort_last(self):
        entries = {
            "https://example.com/undated": {
                "text": "Undated",
                "url": "https://example.com/undated",
            },
            "https://example.com/dated": {
                "text": "Dated",
                "url": "https://example.com/dated",
                "created": "Mon, 11 May 2026 08:00:00 +1300",
            },
        }
        root = blogroll.build_opml(entries, "now").getroot()
        assert [o.get("text") for o in root.iterfind("./body/outline")] == ["Dated", "Undated"]

    def test_unparseable_date_sorts_last_without_raising(self):
        entries = {
            "https://example.com/bad": {
                "text": "Bad",
                "url": "https://example.com/bad",
                "created": "not a date",
            },
            "https://example.com/good": {
                "text": "Good",
                "url": "https://example.com/good",
                "created": "Mon, 11 May 2026 08:00:00 +1300",
            },
        }
        root = blogroll.build_opml(entries, "now").getroot()
        assert [o.get("text") for o in root.iterfind("./body/outline")] == ["Good", "Bad"]

    def test_omits_empty_attributes(self):
        entries = {"https://example.com/1": {"text": "One", "url": "https://example.com/1"}}
        outline = blogroll.build_opml(entries, "now").getroot().find("./body/outline")
        assert outline.get("created") is None
        assert "type" not in outline.attrib


class TestWriteIfChanged:
    """Rewriting an unchanged file produced a daily no-op commit."""

    ENTRY: ClassVar[dict[str, dict[str, str]]] = {
        "https://example.com/1": {
            "text": "One",
            "type": "link",
            "url": "https://example.com/1",
            "created": "Mon, 11 May 2026 08:00:00 +1300",
        }
    }

    def test_creates_a_missing_file(self, tmp_path):
        path = tmp_path / "articles.opml"
        assert blogroll.write_if_changed(str(path), self.ENTRY, None) is True
        assert path.exists()

    def test_writes_a_trailing_newline(self, tmp_path):
        path = tmp_path / "articles.opml"
        blogroll.write_if_changed(str(path), self.ENTRY, None)
        assert path.read_bytes().endswith(b"\n")

    def test_leaves_an_unchanged_file_alone(self, tmp_path):
        path = tmp_path / "articles.opml"
        blogroll.write_if_changed(str(path), self.ENTRY, None)
        entries, date_created = blogroll.load_existing(str(path))
        before = path.read_bytes()

        assert blogroll.write_if_changed(str(path), entries, date_created) is False
        assert path.read_bytes() == before

    def test_rewrites_when_an_article_is_added(self, tmp_path):
        path = tmp_path / "articles.opml"
        blogroll.write_if_changed(str(path), self.ENTRY, None)
        entries, date_created = blogroll.load_existing(str(path))
        entries["https://example.com/2"] = {
            "text": "Two",
            "type": "link",
            "url": "https://example.com/2",
            "created": "Sat, 25 Jul 2026 11:41:41 +1300",
        }

        assert blogroll.write_if_changed(str(path), entries, date_created) is True
        reloaded, _ = blogroll.load_existing(str(path))
        assert len(reloaded) == 2
        assert reloaded["https://example.com/2"]["text"] == "Two"

    def test_round_trip_preserves_entries(self, tmp_path):
        path = tmp_path / "articles.opml"
        blogroll.write_if_changed(str(path), self.ENTRY, None)
        reloaded, _ = blogroll.load_existing(str(path))
        assert reloaded == self.ENTRY

    def test_preserves_non_ascii_titles(self, tmp_path):
        path = tmp_path / "articles.opml"
        entries = {
            "https://example.com/1": {
                "text": f"The surprising richness of GarageBand {EN_DASH} Unsung",
                "type": "link",
                "url": "https://example.com/1",
            }
        }
        blogroll.write_if_changed(str(path), entries, None)
        reloaded, _ = blogroll.load_existing(str(path))
        assert (
            reloaded["https://example.com/1"]["text"] == entries["https://example.com/1"]["text"]
        )

    def test_output_is_valid_xml(self, tmp_path):
        path = tmp_path / "articles.opml"
        blogroll.write_if_changed(str(path), self.ENTRY, None)
        root = ET.fromstring(path.read_text(encoding="utf-8"))  # noqa: S314 - our own output.
        assert root.tag == "opml"
        assert root.findtext("./head/title") == blogroll.OPML_TITLE
