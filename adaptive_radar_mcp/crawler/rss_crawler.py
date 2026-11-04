"""Lightweight RSS/Atom feed crawler with defusedxml protection and size limits."""

import asyncio
import email.utils
import hashlib
import logging
from datetime import datetime, timezone

import defusedxml.ElementTree as ET
import httpx

from adaptive_radar_mcp.models import SourceType, TechRelease
from adaptive_radar_mcp.sanitizer import ContentSanitizer

logger = logging.getLogger("adaptive-radar.rss")
MAX_FEED_BYTES = 2 * 1024 * 1024  # 2 MB limit


def _parse_to_iso(date_str: str) -> str:
    """Normalize RFC 822 or ISO date strings to standard ISO 8601 UTC."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        # Try RFC 822 (common in RSS)
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            # Try ISO 8601 format
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return date_str


class RSSCrawler:
    """Fetches updates from public RSS and Atom XML feeds with hardened XML defenses."""

    def __init__(self, concurrency_limit: int = 5):
        self.headers = {
            "User-Agent": "Adaptive-Radar-MCP/1.0",
        }
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def fetch_feed_items(
        self, client: httpx.AsyncClient, feed_name: str, feed_url: str, limit: int = 3
    ) -> list[TechRelease]:
        """Fetch latest posts from an RSS or Atom feed with size checking and safe parsing."""
        releases: list[TechRelease] = []
        async with self.semaphore:
            try:
                response = await client.get(feed_url, headers=self.headers)
                if response.status_code != 200:
                    return releases

                # Enforce response body size limit
                if len(response.content) > MAX_FEED_BYTES:
                    logger.warning("Feed %s exceeded maximum allowed size (%d bytes)", feed_name, MAX_FEED_BYTES)
                    return releases

                # Parse using defusedxml (protects against XXE, Billion Laughs, quadratic blowup in all encodings)
                root = ET.fromstring(response.content)

                # RSS 2.0 (channel -> item)
                channel = root.find("channel")
                if channel is not None:
                    items = channel.findall("item")[:limit]
                    for item in items:
                        title_raw = item.findtext("title") or "Announcement"
                        link_raw = item.findtext("link") or feed_url
                        desc_raw = item.findtext("description") or ""
                        pub_date_raw = item.findtext("pubDate") or ""

                        title = ContentSanitizer.sanitize_title(title_raw)
                        link = ContentSanitizer.sanitize_url(link_raw) or feed_url
                        desc = ContentSanitizer.sanitize_text(desc_raw, max_length=1000)
                        published_at = _parse_to_iso(pub_date_raw)

                        content_raw = f"{feed_name}:{link}:{title}"
                        content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()

                        releases.append(
                            TechRelease(
                                release_id=f"rss:{feed_name}:{content_hash[:12]}",
                                source_type=SourceType.RSS_FEED,
                                project_or_repo=feed_name,
                                version=None,
                                title=title,
                                body=desc,
                                url=link,
                                published_at=published_at,
                                content_hash=content_hash,
                            )
                        )
                else:
                    # Atom feed (feed -> entry)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall("atom:entry", ns) or root.findall("entry")
                    for entry in entries[:limit]:
                        title_el = entry.find("atom:title", ns) if ns else entry.find("title")
                        title_raw = (title_el.text if title_el is not None else None) or "Announcement"

                        link_el = entry.find("atom:link", ns) if ns else entry.find("link")
                        link_raw = (link_el.attrib.get("href") if link_el is not None else None) or feed_url

                        summary_el = entry.find("atom:summary", ns) if ns else entry.find("summary")
                        body_raw = (summary_el.text if summary_el is not None else None) or ""

                        updated_el = entry.find("atom:updated", ns) if ns else entry.find("updated")
                        pub_date_raw = (updated_el.text if updated_el is not None else None) or ""

                        title = ContentSanitizer.sanitize_title(title_raw)
                        link = ContentSanitizer.sanitize_url(link_raw) or feed_url
                        desc = ContentSanitizer.sanitize_text(body_raw, max_length=1000)
                        published_at = _parse_to_iso(pub_date_raw)

                        content_raw = f"{feed_name}:{link}:{title}"
                        content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()

                        releases.append(
                            TechRelease(
                                release_id=f"atom:{feed_name}:{content_hash[:12]}",
                                source_type=SourceType.RSS_FEED,
                                project_or_repo=feed_name,
                                version=None,
                                title=title,
                                body=desc,
                                url=link,
                                published_at=published_at,
                                content_hash=content_hash,
                            )
                        )
            except Exception as e:
                logger.debug("Failed to parse feed %s: %s", feed_name, e)

        return releases

    async def fetch_all(self, feeds: list[dict], limit_per_feed: int = 2) -> list[TechRelease]:
        """Fetch all feeds concurrently using a pooled HTTP client."""
        if not feeds:
            return []

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            tasks = [
                self.fetch_feed_items(client, feed["name"], feed["url"], limit=limit_per_feed)
                for feed in feeds
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        releases: list[TechRelease] = []
        for r in results:
            if isinstance(r, list):
                releases.extend(r)
        return releases
