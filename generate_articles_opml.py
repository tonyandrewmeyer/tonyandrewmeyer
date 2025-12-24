#!/usr/bin/env python3
"""
Generate OPML file for articles from tonyandrewmeyer.blog RSS feed.
"""

import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import sys


def create_opml_root():
    """Create the root OPML structure."""
    root = ET.Element('opml', version='2.0')
    
    # Head section
    head = ET.SubElement(root, 'head')
    title = ET.SubElement(head, 'title')
    title.text = "Tony Meyer's Articles"
    
    date_created = ET.SubElement(head, 'dateCreated')
    date_created.text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    return root


def fetch_articles(feed_url):
    """Fetch articles from RSS feed."""
    print(f"Fetching articles from {feed_url}...", file=sys.stderr)
    feed = feedparser.parse(feed_url)
    
    if feed.bozo:
        print(f"Warning: Feed parsing had issues: {feed.bozo_exception}", file=sys.stderr)
    
    print(f"Found {len(feed.entries)} articles", file=sys.stderr)
    return feed.entries


def generate_articles_opml(feed_url, output_file):
    """Generate OPML file from blog articles."""
    root = create_opml_root()
    body = ET.SubElement(root, 'body')
    
    # Fetch articles
    articles = fetch_articles(feed_url)
    
    # Add each article as an outline
    for entry in articles:
        outline = ET.SubElement(body, 'outline')
        outline.set('text', entry.get('title', 'Untitled'))
        outline.set('title', entry.get('title', 'Untitled'))
        outline.set('type', 'link')
        outline.set('url', entry.get('link', ''))
        
        # Add published date if available
        if hasattr(entry, 'published'):
            outline.set('created', entry.published)
        
        # Add description/summary if available
        if hasattr(entry, 'summary'):
            outline.set('description', entry.summary[:200])  # Limit length
    
    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"Generated {output_file} with {len(articles)} articles", file=sys.stderr)


if __name__ == '__main__':
    BLOG_RSS_FEED = 'https://tonyandrewmeyer.blog/feed'
    OUTPUT_FILE = 'articles.opml'
    
    generate_articles_opml(BLOG_RSS_FEED, OUTPUT_FILE)
