#!/usr/bin/env python3
"""
Generate OPML file for RSS feeds from Feedly.
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import sys
import os


def create_opml_root():
    """Create the root OPML structure."""
    root = ET.Element('opml', version='2.0')
    
    # Head section
    head = ET.SubElement(root, 'head')
    title = ET.SubElement(head, 'title')
    title.text = "Tony Meyer's RSS Feeds"
    
    date_created = ET.SubElement(head, 'dateCreated')
    date_created.text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    return root


def fetch_feedly_subscriptions(access_token):
    """Fetch subscriptions from Feedly API."""
    url = 'https://cloud.feedly.com/v3/subscriptions'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    print(f"Fetching subscriptions from Feedly...", file=sys.stderr)
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error fetching subscriptions: {response.status_code}", file=sys.stderr)
        print(f"Response: {response.text}", file=sys.stderr)
        sys.exit(1)
    
    subscriptions = response.json()
    print(f"Found {len(subscriptions)} subscriptions", file=sys.stderr)
    return subscriptions


def generate_feeds_opml(access_token, output_file):
    """Generate OPML file from Feedly subscriptions."""
    root = create_opml_root()
    body = ET.SubElement(root, 'body')
    
    # Fetch subscriptions
    subscriptions = fetch_feedly_subscriptions(access_token)
    
    # Group by categories
    categories = {}
    for sub in subscriptions:
        # Get categories for this subscription
        sub_categories = sub.get('categories', [])
        
        if not sub_categories:
            # Uncategorized
            if 'Uncategorized' not in categories:
                categories['Uncategorized'] = []
            categories['Uncategorized'].append(sub)
        else:
            for cat in sub_categories:
                cat_label = cat.get('label', 'Uncategorized')
                if cat_label not in categories:
                    categories[cat_label] = []
                categories[cat_label].append(sub)
    
    # Add each category as an outline
    for cat_name, feeds in sorted(categories.items()):
        cat_outline = ET.SubElement(body, 'outline')
        cat_outline.set('text', cat_name)
        cat_outline.set('title', cat_name)
        
        # Add each feed in this category
        for feed in feeds:
            feed_outline = ET.SubElement(cat_outline, 'outline')
            feed_outline.set('text', feed.get('title', 'Untitled'))
            feed_outline.set('title', feed.get('title', 'Untitled'))
            feed_outline.set('type', 'rss')
            
            # xmlUrl is the actual RSS feed URL
            xml_url = feed.get('xmlUrl', '')
            if not xml_url and 'id' in feed:
                # Fallback: extract from feed ID (format: "feed/http://...")
                feed_id = feed['id']
                if feed_id.startswith('feed/'):
                    xml_url = feed_id[5:]  # Remove 'feed/' prefix
            feed_outline.set('xmlUrl', xml_url)
            
            # Add website URL if available
            if 'website' in feed:
                feed_outline.set('htmlUrl', feed['website'])
    
    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"Generated {output_file} with {len(subscriptions)} feeds in {len(categories)} categories", file=sys.stderr)


if __name__ == '__main__':
    # Get Feedly access token from environment variable
    access_token = os.environ.get('FEEDLY_ACCESS_TOKEN')
    
    if not access_token:
        print("Error: FEEDLY_ACCESS_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    OUTPUT_FILE = 'feeds.opml'
    
    generate_feeds_opml(access_token, OUTPUT_FILE)
