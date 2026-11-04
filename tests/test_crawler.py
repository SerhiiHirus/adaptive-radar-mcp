"""Unit tests for crawler components, ETag caching, and defusedxml."""

import pytest
import httpx
from adaptive_radar_mcp.crawler.rss_crawler import RSSCrawler, _parse_to_iso
from adaptive_radar_mcp.crawler.github_releases import GitHubReleasesCrawler


@pytest.mark.asyncio
async def test_rss_crawler_xxe_protection():
    """Verify that defusedxml safely mitigates XML entity expansion bombs."""
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

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=malicious_xml)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # defusedxml will raise or safely ignore entity expansion
        items = await crawler.fetch_feed_items(client, "test_feed", "https://example.com/rss")
        assert items == []


@pytest.mark.asyncio
async def test_github_crawler_etag_caching():
    """Verify that ETag 304 response is handled and returns None without re-parsing."""
    crawler = GitHubReleasesCrawler()

    # First request: 200 OK with ETag
    def handler_initial(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, 
            json={"tag_name": "v1.0", "name": "Release 1.0", "body": "Initial", "html_url": "https://example.com"},
            headers={"ETag": 'W/"12345"'}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_initial)) as client:
        rel = await crawler.fetch_latest_release(client, "test/repo")
        assert rel is not None
        assert crawler._etags.get("test/repo") == 'W/"12345"'

    # Second request: 304 Not Modified
    def handler_cached(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("If-None-Match") == 'W/"12345"'
        return httpx.Response(304)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_cached)) as client:
        rel_cached = await crawler.fetch_latest_release(client, "test/repo")
        assert rel_cached is None


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


def test_date_parsing_rfc822_to_iso():
    """Verify that RFC 822 RSS dates are converted to standard ISO 8601 (B2 fix)."""
    rfc_date = "Tue, 03 Nov 2026 12:00:00 GMT"
    iso_result = _parse_to_iso(rfc_date)
    assert iso_result.startswith("2026-11-03T12:00:00")
