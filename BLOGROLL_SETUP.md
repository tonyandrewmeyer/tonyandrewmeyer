# Blogroll Setup

This repository includes automated blogroll functionality that generates OPML files from:
1. Articles shared on tonyandrewmeyer.blog
2. RSS feeds followed in Feedly

## Setup

### Feedly Access Token

To enable the Feedly integration, you need to set up a `FEEDLY_ACCESS_TOKEN` secret in your GitHub repository:

1. **Get your Feedly Access Token:**
   - For Enterprise/Threat Intelligence users: Visit https://feedly.com/i/team/api
   - For other users: You'll need to use the Feedly Developer API:
     1. Register your application at https://developers.feedly.com/
     2. Note your Client ID and Client Secret
     3. Authorize your application and get an access token
     
   Alternatively, you can manually export your Feedly feeds as OPML by visiting https://feedly.com/i/opml and downloading the file, then committing it as `feeds.opml`.

2. **Add the token as a GitHub Secret:**
   1. Go to your repository's Settings
   2. Navigate to Secrets and variables → Actions
   3. Click "New repository secret"
   4. Name: `FEEDLY_ACCESS_TOKEN`
   5. Value: Your Feedly access token
   6. Click "Add secret"

### Manual Testing

You can manually trigger the workflow:
1. Go to the Actions tab in your GitHub repository
2. Select "Update Blogroll OPML Files"
3. Click "Run workflow"

## Files Generated

- `articles.opml` - All articles from tonyandrewmeyer.blog
- `feeds.opml` - All RSS feeds from Feedly

These files are referenced in `BLOGROLL.md` and are automatically updated daily at 00:00 UTC.
