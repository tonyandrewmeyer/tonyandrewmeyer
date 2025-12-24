#!/usr/bin/env python3
"""
Generate OPML file for articles from tonyandrewmeyer.blog RSS feed.
Extracts outgoing links from blog posts rather than linking to the posts themselves.
"""

import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
import sys
import re
import requests
from urllib.parse import urlparse

# Constants
MAX_DESCRIPTION_LENGTH = 200
BLOG_DOMAIN = 'tonyandrewmeyer.blog'


class LinkExtractor(HTMLParser):
    """Extract links from HTML content."""
    def __init__(self):
        super().__init__()
        self.links = []
    
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr, value in attrs:
                if attr == 'href':
                    self.links.append(value)


class TitleExtractor(HTMLParser):
    """Extract title from HTML content."""
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = None
    
    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True
    
    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
    
    def handle_data(self, data):
        if self.in_title and self.title is None:
            self.title = data.strip()


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


def fetch_title_from_url(url):
    """Fetch the title from a remote URL.
    
    Returns the title from the <title> tag, or None if unable to fetch.
    """
    try:
        # Validate URL scheme
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ('http', 'https'):
            print(f"Skipping non-HTTP(S) URL: {url}", file=sys.stderr)
            return None
        
        # Set a timeout and user agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; BlogrollBot/1.0)'
        }
        # Stream the response and only read the first 50KB (title is typically in head)
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True, stream=True)
        response.raise_for_status()
        
        # Read only first 50KB to avoid processing large documents
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) >= 51200:  # 50KB
                break
        
        # Decode content
        text_content = content.decode(response.encoding or 'utf-8', errors='ignore')
        
        # Parse the HTML to extract title
        parser = TitleExtractor()
        parser.feed(text_content)
        
        if parser.title:
            return parser.title
        
        # Fallback: try to extract from URL path
        path = parsed_url.path.rstrip('/').split('/')[-1]
        if path:
            # Convert URL slug to title (e.g., "my-article" -> "My Article")
            return path.replace('-', ' ').replace('_', ' ').title()
        
        return None
        
    except (requests.RequestException, UnicodeDecodeError, ValueError) as e:
        print(f"Error fetching title from {url}: {e}", file=sys.stderr)
        return None


def extract_outgoing_link(entry):
    """Extract the first outgoing link from a blog post entry.
    
    Returns the URL and title of the linked article, or None if no external link found.
    """
    # Get the content or summary
    content = ''
    if hasattr(entry, 'content') and entry.content:
        content = entry.content[0].value
    elif hasattr(entry, 'summary'):
        content = entry.summary
    
    if not content:
        return None
    
    # Parse HTML and extract links
    parser = LinkExtractor()
    try:
        parser.feed(content)
    except Exception as e:
        print(f"Error parsing HTML: {e}", file=sys.stderr)
        return None
    
    # Filter out self-referential links and common non-article links
    external_links = []
    for link in parser.links:
        # Skip links to the blog itself (check domain more precisely)
        link_lower = link.lower()
        if f'//{BLOG_DOMAIN}' in link_lower or f'www.{BLOG_DOMAIN}' in link_lower:
            continue
        # Skip common non-article links
        if link.startswith(('mailto:', 'javascript:', '#')):
            continue
        # Skip relative links
        if not link.startswith(('http://', 'https://')):
            continue
        external_links.append(link)
    
    # Return the first external link found
    if external_links:
        return external_links[0]
    
    return None


def fetch_articles(feed_url):
    """Fetch articles from RSS feed."""
    print(f"Fetching articles from {feed_url}...", file=sys.stderr)
    feed = feedparser.parse(feed_url)
    
    if feed.bozo:
        print(f"Warning: Feed parsing had issues: {feed.bozo_exception}", file=sys.stderr)
    
    print(f"Found {len(feed.entries)} blog posts", file=sys.stderr)
    return feed.entries


def generate_articles_opml(feed_url, output_file):
    """Generate OPML file from blog articles.
    
    Extracts outgoing links from blog posts and creates OPML entries for those links.
    Blog posts without outgoing links are skipped.
    """
    root = create_opml_root()
    body = ET.SubElement(root, 'body')
    
    # Fetch blog posts
    blog_posts = fetch_articles(feed_url)
    
    # Extract outgoing links from each post
    articles_added = 0
    posts_skipped = 0
    
    for entry in blog_posts:
        outgoing_url = extract_outgoing_link(entry)
        
        if not outgoing_url:
            posts_skipped += 1
            continue
        
        # Fetch the title from the remote URL
        article_title = fetch_title_from_url(outgoing_url)
        if not article_title:
            print(f"Warning: Could not fetch title for {outgoing_url}, skipping", file=sys.stderr)
            posts_skipped += 1
            continue
        
        # Create OPML entry for the linked article
        outline = ET.SubElement(body, 'outline')
        
        # Use the title from the remote URL
        outline.set('text', article_title)
        outline.set('type', 'link')
        outline.set('url', outgoing_url)
        
        # Add published date if available
        if hasattr(entry, 'published'):
            outline.set('created', entry.published)
        
        articles_added += 1
    
    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"Generated {output_file} with {articles_added} articles (skipped {posts_skipped} posts without outgoing links)", file=sys.stderr)


if __name__ == '__main__':
    BLOG_RSS_FEED = 'https://tonyandrewmeyer.blog/feed'
    OUTPUT_FILE = 'articles.opml'
    
    generate_articles_opml(BLOG_RSS_FEED, OUTPUT_FILE)
