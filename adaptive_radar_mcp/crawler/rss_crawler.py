"""Lightweight RSS/Atom feed crawler with concurrency and security defenses."""

import asyncio
import hashlib
import xml.etree.ElementTree as ET
from typing import List
import httpx

from adaptive_radar_mcp.models import SourceType, TechRelease


class RSSCrawler:
    """Fetches updates from public RSS and Atom XML feeds concurrently."""

    def __init__(self, concurrency_limit: int = 5):
        self.headers = {
            "User-Agent": "Adaptive-Radar-MCP/1.0",
        }
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def fetch_feed_items(
        self, client: httpx.AsyncClient, feed_name: str, feed_url: str, limit: int = 3
    ) -> List[TechRelease]:
        """Fetch latest posts from an RSS or Atom feed."""
        releases: List[TechRelease] = []
        async with self.semaphore:
            try:
                response = await client.get(feed_url, headers=self.headers)
                if response.status_code != 200:
                    return releases

                raw_bytes = response.content
                # Security: Defend against XXE and recursive entity expansion
                if b"<!ENTITY" in raw_bytes or b"<!DOCTYPE" in raw_bytes:
                    return releases

                root = ET.fromstring(raw_bytes)
                # RSS 2.0 (channel -> item)
                channel = root.find("channel")
                if channel is not None:
                    items = channel.findall("item")[:limit]
                    for item in items:
                        title = (item.findtext("title") or "").strip() or "Announcement"
                        link = (item.findtext("link") or "").strip() or feed_url
                        desc = (item.findtext("description") or "").strip()
                        pub_date = (item.findtext("pubDate") or "").strip()
                        
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
                                published_at=pub_date,
                                content_hash=content_hash,
                            )
                        )
                else:
                    # Atom feed (feed -> entry)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall("atom:entry", ns) or root.findall("entry")
                    for entry in entries[:limit]:
                        title_el = entry.find("atom:title", ns) if ns else entry.find("title")
                        title = (title_el.text if title_el is not None else None) or "Announcement"
                        
                        link_el = entry.find("atom:link", ns) if ns else entry.find("link")
                        link = link_el.attrib.get("href", feed_url) if link_el is not None else feed_url
                        
                        summary_el = entry.find("atom:summary", ns) if ns else entry.find("summary")
                        body = (summary_el.text if summary_el is not None else None) or ""
                        
                        updated_el = entry.find("atom:updated", ns) if ns else entry.find("updated")
                        pub_date = (updated_el.text if updated_el is not None else None) or ""

                        content_raw = f"{feed_name}:{link}:{title}"
                        content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()

                        releases.append(
                            TechRelease(
                                release_id=f"atom:{feed_name}:{content_hash[:12]}",
                                source_type=SourceType.RSS_FEED,
                                project_or_repo=feed_name,
                                version=None,
                                title=title,
                                body=body,
                                url=link,
                                published_at=pub_date,
                                content_hash=content_hash,
                            )
                        )
            except Exception:
                pass

        return releases

    async def fetch_all(self, feeds: List[dict], limit_per_feed: int = 2) -> List[TechRelease]:
        """Fetch all feeds concurrently using a pooled HTTP client."""
        if not feeds:
            return []

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            tasks = [
                self.fetch_feed_items(client, feed["name"], feed["url"], limit=limit_per_feed)
                for feed in feeds
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        releases: List[TechRelease] = []
        for r in results:
            if isinstance(r, list):
                releases.extend(r)
        return releases
