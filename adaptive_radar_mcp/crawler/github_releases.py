"""GitHub Releases crawler with concurrent execution and connection pooling."""

import asyncio
import hashlib
import logging
import os
from typing import List, Optional
import httpx

from adaptive_radar_mcp.models import SourceType, TechRelease

logger = logging.getLogger("adaptive-radar.github")


class GitHubReleasesCrawler:
    """Fetches latest releases from GitHub repositories concurrently."""

    def __init__(self, token: Optional[str] = None, concurrency_limit: int = 5):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Adaptive-Radar-MCP/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def fetch_latest_release(self, client: httpx.AsyncClient, repo: str) -> Optional[TechRelease]:
        """Fetch the latest published release for owner/repo with error inspection."""
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        
        async with self.semaphore:
            try:
                response = await client.get(url, headers=self.headers)
                if response.status_code == 403:
                    logger.warning(
                        "GitHub API Rate Limit reached (HTTP 403) for %s. Set GITHUB_TOKEN to increase limits.",
                        repo,
                    )
                    return None
                if response.status_code == 404 or response.status_code != 200:
                    return None

                data = response.json()
                tag_name = data.get("tag_name", "")
                title = data.get("name") or tag_name or "Release"
                body = data.get("body") or ""
                html_url = data.get("html_url", f"https://github.com/{repo}")
                published_at = data.get("published_at") or ""

                content_raw = f"{repo}:{tag_name}:{body}"
                content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()

                return TechRelease(
                    release_id=f"gh:{repo}:{tag_name}",
                    source_type=SourceType.GITHUB_RELEASE,
                    project_or_repo=repo,
                    version=tag_name,
                    title=f"{repo} {tag_name}: {title}",
                    body=body,
                    url=html_url,
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
