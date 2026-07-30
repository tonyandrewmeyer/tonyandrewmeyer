# Blogroll Setup

This repository publishes two OPML files:

| File | Contents | Updated |
| --- | --- | --- |
| `articles.opml` | Articles linked from [tonyandrewmeyer.blog](https://tonyandrewmeyer.blog) | Automatically, daily |
| `feeds.opml` | RSS feeds followed in Feedly | Manually (see below) |

## `articles.opml` — automatic

Each post on the link blog quotes and links to an article elsewhere. It is that
outgoing link that belongs in the blogroll, so `generate_articles_opml.py`
extracts the first external link from each post and records it.

The blogroll is **cumulative**. The RSS feed only serves the 25 most recent
posts, so the script merges what it finds into the existing `articles.opml`
instead of rewriting it — articles that have scrolled out of the feed stay in
the blogroll, and titles already recorded are never re-fetched.

The `Update Blogroll OPML Files` workflow runs daily and commits only when an
article has actually been added.

### Backfilling

`generate_articles_opml.py` can only see the feed's 25-post window. To recover
everything older, `backfill_articles_opml.py` walks the blog's full archive
(`/archive/index.json`), fetches each post page, and merges in every outgoing
link it finds:

```sh
uv run backfill_articles_opml.py            # every post, ~0.2s apart
uv run backfill_articles_opml.py --limit 20 # try it on the 20 most recent first
```

Run the tests with `uv run --group dev pytest`.

It is safe to re-run: existing entries are never re-fetched or overwritten, so
an interrupted run picks up where it left off.

## `feeds.opml` — manual

There is no automation for this file, because Feedly no longer offers API
access to personal accounts. Their
[authorization docs](https://developers.feedly.com/reference/authorization)
state plainly that "self service API tokens are only available to Enterprise
clients", so a `FEEDLY_ACCESS_TOKEN` cannot be obtained for a Pro account.

To refresh it, export from Feedly and commit the result:

1. Visit <https://feedly.com/i/opml>.
2. Download the OPML export.
3. Replace `feeds.opml` and commit.

## Manual testing

To trigger the articles workflow by hand:

1. Go to the Actions tab.
2. Select "Update Blogroll OPML Files".
3. Click "Run workflow".
