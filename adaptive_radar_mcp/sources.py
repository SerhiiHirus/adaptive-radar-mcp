"""Dynamic source configuration manager with persistent user storage."""

import importlib.resources
import os
from pathlib import Path

import yaml

from adaptive_radar_mcp.crawler.validator import SourceValidator


class SourcesManager:
    """Manages dynamic user sources stored in ~/.adaptive-radar/sources.yaml with fallback to defaults."""

    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            storage_dir = os.environ.get("RADAR_STORAGE_DIR")
            if storage_dir:
                self.config_dir = Path(storage_dir)
            else:
                self.config_dir = Path.home() / ".adaptive-radar"
        else:
            self.config_dir = config_dir

        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.sources_file = self.config_dir / "sources.yaml"
        self._ensure_config()

    def _get_packaged_defaults(self) -> dict:
        try:
            data_file = importlib.resources.files("adaptive_radar_mcp.data").joinpath("default_sources.yaml")
            content = data_file.read_text(encoding="utf-8")
            return yaml.safe_load(content) or {}
        except Exception:
            return {
                "github_repositories": ["pydantic/pydantic-ai", "BerriAI/litellm"],
                "rss_feeds": [],
            }

    def _ensure_config(self) -> None:
        """Create initial sources.yaml from defaults if not present."""
        if not self.sources_file.exists():
            defaults = self._get_packaged_defaults()
            self.save_sources(defaults)
            try:
                os.chmod(self.sources_file, 0o600)
            except OSError:
                pass

    def load_sources(self) -> dict:
        """Load configured sources."""
        if not self.sources_file.exists():
            return self._get_packaged_defaults()
        try:
            content = self.sources_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            return data if isinstance(data, dict) else self._get_packaged_defaults()
        except Exception:
            return self._get_packaged_defaults()

    def save_sources(self, data: dict) -> None:
        """Persist sources securely."""
        self.sources_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        try:
            os.chmod(self.sources_file, 0o600)
        except OSError:
            pass

    def add_github_repo(self, repo_identifier: str) -> str:
        """Validate and add a new GitHub repo source."""
        valid_repo = SourceValidator.validate_github_repo(repo_identifier)
        sources = self.load_sources()
        repos: list[str] = sources.setdefault("github_repositories", [])
        if valid_repo in repos:
            return f"Source '{valid_repo}' is already tracked."

        repos.append(valid_repo)
        self.save_sources(sources)
        return f"Successfully added GitHub repository '{valid_repo}'."

    def add_rss_feed(self, name: str, url: str) -> str:
        """Validate and add a new RSS feed source."""
        valid_url = SourceValidator.validate_rss_url(url)
        sources = self.load_sources()
        feeds: list[dict] = sources.setdefault("rss_feeds", [])
        for f in feeds:
            if f.get("url") == valid_url:
                return f"Feed with URL '{valid_url}' is already tracked."

        feeds.append({"name": name.strip(), "url": valid_url})
        self.save_sources(sources)
        return f"Successfully added RSS feed '{name.strip()}' ({valid_url})."

    def remove_source(self, identifier: str) -> bool:
        """Remove a GitHub repo or RSS URL."""
        sources = self.load_sources()
        removed = False

        # Check GitHub repos
        if "github_repositories" in sources and identifier in sources["github_repositories"]:
            sources["github_repositories"].remove(identifier)
            removed = True

        # Check RSS feeds
        if "rss_feeds" in sources:
            original_len = len(sources["rss_feeds"])
            sources["rss_feeds"] = [f for f in sources["rss_feeds"] if f.get("url") != identifier and f.get("name") != identifier]
            if len(sources["rss_feeds"]) < original_len:
                removed = True

        if removed:
            self.save_sources(sources)

        return removed
