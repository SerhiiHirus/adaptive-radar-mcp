"""GitHub Releases crawler with concurrent execution, ETag caching, and rate limit resilience."""

import asyncio
import hashlib
import logging
import os
from typing import Dict, List, Optional
import httpx

from adaptive_radar_mcp.models import SourceType, TechRelease
from adaptive_radar_mcp.sanitizer import ContentSanitizer

logger = logging.getLogger("adaptive-radar.github")


class GitHubReleasesCrawler:
    """Fetches latest releases from GitHub repositories concurrently with ETag caching."""

    def __init__(self, token: Optional[str] = None, concurrency_limit: int = 5):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Adaptive-Radar-MCP/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self._etags: Dict[str, str] = {}

    async def fetch_latest_release(self, client: httpx.AsyncClient, repo: str) -> Optional[TechRelease]:
        """Fetch the latest published release for owner/repo with ETag support."""
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req_headers = dict(self.headers)
        if repo in self._etags:
            req_headers["If-None-Match"] = self._etags[repo]

        async with self.semaphore:
            try:
                response = await client.get(url, headers=req_headers)
                if response.status_code == 304:
                    # 304 Not Modified: Upstream release has not changed
                    return None

                if response.status_code == 403:
                    logger.warning(
                        "GitHub API Rate Limit reached (HTTP 403) for %s. Set GITHUB_TOKEN to increase limits.",
                        repo,
                    )
                    return None

                if response.status_code != 200:
                    return None

                # Store ETag header for conditional request caching
                if "ETag" in response.headers:
                    self._etags[repo] = response.headers["ETag"]

                data = response.json()
                tag_name = data.get("tag_name", "")
                title_raw = data.get("name") or tag_name or "Release"
                body_raw = data.get("body") or ""
                html_url_raw = data.get("html_url", f"https://github.com/{repo}")
                published_at = data.get("published_at") or ""

                title = ContentSanitizer.sanitize_title(f"{repo} {tag_name}: {title_raw}")
                body = ContentSanitizer.sanitize_text(body_raw, max_length=1000)
                url = ContentSanitizer.sanitize_url(html_url_raw) or f"https://github.com/{repo}"

                content_raw = f"{repo}:{tag_name}:{body}"
                content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()

                return TechRelease(
                    release_id=f"gh:{repo}:{tag_name}",
                    source_type=SourceType.GITHUB_RELEASE,
                    project_or_repo=repo,
                    version=tag_name,
                    title=title,
                    body=body,
                    url=url,
                    published_at=published_at,
                    content_hash=content_hash,
                )
            except Exception as e:
                logger.debug("Network error fetching release for %s: %s", repo, e)
                return None

    async def fetch_all(self, repos: List[str]) -> List[TechRelease]:
        """Fetch latest releases concurrently using a pooled HTTP client."""
        if not repos:
            return []

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            tasks = [self.fetch_latest_release(client, repo) for repo in repos]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        releases: List[TechRelease] = []
        for r in results:
            if isinstance(r, TechRelease):
                releases.append(r)
        return releases
