"""PyPI API metadata resolver to discover official GitHub repositories and latest versions."""

import logging
import re
from typing import Any

import httpx

from adaptive_radar_mcp.crawler.validator import SourceValidator
from adaptive_radar_mcp.scanner.manifest import ManifestScanner

logger = logging.getLogger("adaptive-radar.pypi")

GITHUB_URL_PATTERN = re.compile(
    r"^https?://github\.com/([a-zA-Z0-9_\.\-]+)/([a-zA-Z0-9_\.\-]+?)(?:\.git|/.*)?$"
)


class PyPIResolver:
    """Safely queries PyPI JSON API to map Python package names to GitHub repositories."""

    BASE_URL = "https://pypi.org/pypi/{package}/json"

    @classmethod
    def _extract_github_repo_from_url(cls, raw_url: str) -> str | None:
        """Extract and validate owner/repo from a GitHub project URL."""
        if not raw_url or not isinstance(raw_url, str):
            return None
        raw_url = raw_url.strip()
        match = GITHUB_URL_PATTERN.match(raw_url)
        if match:
            owner, repo = match.group(1), match.group(2)
            candidate = f"{owner}/{repo}"
            try:
                return SourceValidator.validate_github_repo(candidate)
            except ValueError:
                return None
        return None

    @classmethod
    async def resolve_package(
        cls, client: httpx.AsyncClient, package_name: str
    ) -> dict[str, Any] | None:
        """Query PyPI API for a single package and extract GitHub repository and latest version."""
        clean_name = package_name.strip().lower()
        if not ManifestScanner._is_safe_package_name(clean_name):
            return None

        url = cls.BASE_URL.format(package=clean_name)
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                logger.debug("PyPI lookup failed for %s with status %d", clean_name, response.status_code)
                return None

            data = response.json()
            info = data.get("info", {})
            latest_version = info.get("version", "unknown")

            # Check project_urls
            project_urls = info.get("project_urls") or {}
            urls_to_check: list[str] = []

            for key in ("Source", "Repository", "Source Code", "Code", "Homepage", "GitHub"):
                val = project_urls.get(key)
                if val:
                    urls_to_check.append(val)

            # Also check home_page
            home_page = info.get("home_page")
            if home_page:
                urls_to_check.append(home_page)

            detected_repo: str | None = None
            for candidate_url in urls_to_check:
                repo = cls._extract_github_repo_from_url(candidate_url)
                if repo:
                    detected_repo = repo
                    break

            return {
                "package_name": clean_name,
                "latest_version": latest_version,
                "github_repo": detected_repo,
                "summary": str(info.get("summary") or "")[:200],
            }
        except Exception as e:
            logger.debug("Error querying PyPI for %s: %s", clean_name, e)
            return None

    @classmethod
    async def resolve_packages(
        cls, package_names: list[str], concurrency_limit: int = 5
    ) -> dict[str, dict[str, Any]]:
        """Concurrently resolve multiple packages against PyPI."""
        if not package_names:
            return {}

        semaphore = httpx.AsyncClient(timeout=10.0, follow_redirects=False)
        results: dict[str, dict[str, Any]] = {}

        async with semaphore as client:
            import asyncio
            tasks = [cls.resolve_package(client, name) for name in package_names]
            completed = await asyncio.gather(*tasks, return_exceptions=True)

            for item in completed:
                if isinstance(item, dict) and "package_name" in item:
                    results[item["package_name"]] = item

        return results
