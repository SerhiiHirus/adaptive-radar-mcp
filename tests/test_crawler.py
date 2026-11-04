"""Unit tests for crawler components."""

import pytest
import httpx
from adaptive_radar_mcp.crawler.rss_crawler import RSSCrawler
from adaptive_radar_mcp.crawler.github_releases import GitHubReleasesCrawler


@pytest.mark.asyncio
async def test_rss_crawler_xxe_protection():
    """Verify that RSS crawler rejects XML with malicious DTD / entity definitions."""
    malicious_xml = b"""<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ELEMENT lolz (#PCDATA)>
      <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <rss version="2.0">
      <channel>
        <title>&lol1;</title>
      </channel>
    </rss>
    """
    
    crawler = RSSCrawler()

    # Mock transport returning malicious content
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=malicious_xml)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        items = await crawler.fetch_feed_items(client, "test_feed", "https://example.com/rss")
        # Should safely return empty list without parsing entities
        assert items == []


@pytest.mark.asyncio
async def test_github_crawler_rate_limit_handling():
    """Verify that GitHub crawler handles 403 rate limit without throwing exceptions."""
    crawler = GitHubReleasesCrawler()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        release = await crawler.fetch_latest_release(client, "pydantic/pydantic-ai")
        assert release is None
