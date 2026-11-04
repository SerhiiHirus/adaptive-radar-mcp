"""FastMCP Server for Adaptive Tech Radar & Active Learning."""

import asyncio
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import List, Optional
import yaml

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server import MCPServer as FastMCP

from src.crawler.github_releases import GitHubReleasesCrawler
from src.crawler.rss_crawler import RSSCrawler
from src.evaluator.scoring import ReleaseEvaluator
from src.memory.active_learning import ActiveLearningEngine
from src.memory.db import RadarDatabase
from src.models import (
    DecisionType,
    FeedbackRecord,
    SourceType,
    TechRelease,
    UserStackProfile,
)

mcp = FastMCP("adaptive-radar-mcp")


def get_db() -> RadarDatabase:
    """Return database instance based on active configuration/environment."""
    return RadarDatabase()


def _load_sources_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "default_sources.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return {
        "github_repositories": ["pydantic/pydantic-ai", "BerriAI/litellm"],
        "rss_feeds": [],
    }


@mcp.tool()
async def radar_check_updates(fetch_remote: bool = True, limit: int = 5) -> str:
    """Fetch and score latest AI/LLMOps tech updates against developer preferences and Token ROI.
    
    Args:
        fetch_remote: If True, crawls latest GitHub releases and RSS feeds before scoring.
        limit: Maximum number of evaluated recommendations to return.
    """
    config = _load_sources_config()
    database = get_db()

    if fetch_remote:
        # 1. Fetch GitHub releases concurrently
        repos = config.get("github_repositories", [])
        if repos:
            gh_crawler = GitHubReleasesCrawler()
            gh_releases = await gh_crawler.fetch_all(repos)
            for rel in gh_releases:
                database.save_release(rel)

        # 2. Fetch RSS feeds concurrently
        feeds = config.get("rss_feeds", [])
        if feeds:
            rss_crawler = RSSCrawler()
            feed_items = await rss_crawler.fetch_all(feeds, limit_per_feed=2)
            for item in feed_items:
                database.save_release(item)

    # 3. Retrieve unreviewed releases from DB
    releases = database.get_unreviewed_releases(limit=25)
    if not releases:
        return "🛰 **Radar Status:** All tracked updates have already been evaluated and reviewed. No new items found."

    profile = database.get_user_profile()
    feedback_history = database.get_recent_feedback(limit=20)

    # 4. Score releases
    evaluations = [
        ReleaseEvaluator.evaluate(rel, profile, feedback_history)
        for rel in releases
    ]
    # Sort by score descending
    evaluations.sort(key=lambda e: e.score, reverse=True)
    top_evals = evaluations[:limit]

    # 5. Format human- and agent-friendly output
    lines = [
        f"## 🛰 Adaptive Tech Radar — Evaluated {len(releases)} updates",
        f"> Profile: `{', '.join(profile.preferred_tools)}` | Learned decisions in memory: `{len(feedback_history)}`",
        "",
    ]

    for ev in top_evals:
        score_emoji = "🟢" if ev.score >= 7.0 else ("🟡" if ev.score >= 4.5 else "⚪")
        lines.extend([
            f"### {score_emoji} [{ev.recommended_action}] {ev.title} (Score: {ev.score}/10)",
            f"- **Release ID:** `{ev.release_id}`",
            f"- **URL:** {ev.url}",
            f"- **Token ROI:** {ev.token_roi_summary}",
            f"- **Safety Verdict:** `{ev.safety_verdict}`",
            f"- **Rationale:** {ev.rationale}",
        ])
        if ev.context7_query:
            lines.append(f"- **Suggested Context7 Check:** `query-docs` for `{ev.context7_query}`")
        lines.append("")

    lines.extend([
        "---",
        "💡 **Active Learning Training:** Use `radar_record_feedback(release_id, decision, reason)` to approve/reject any item. Your decisions will refine future ratings.",
    ])

    return "\n".join(lines)


@mcp.tool()
def radar_record_feedback(release_id: str, decision: str, reason: str) -> str:
    """Record developer's decision (ACCEPTED, REJECTED, OBSERVED) to train active learning memory.
    
    Args:
        release_id: The unique ID of the release (e.g. 'gh:pydantic/pydantic-ai:v2.65.0').
        decision: One of 'ACCEPTED', 'REJECTED', 'OBSERVED'.
        reason: Why you approved or rejected it (e.g. 'We need structured outputs', 'Too complex, prefer standard SDK').
    """
    import re
    decision_clean = decision.upper().strip()
    if decision_clean not in ["ACCEPTED", "REJECTED", "OBSERVED"]:
        return f"Error: decision must be one of ACCEPTED, REJECTED, OBSERVED (got: {decision})"

    database = get_db()
    clean_id = re.sub(r"^(?:gh|rss|atom|custom):", "", release_id)
    project_or_repo = clean_id.split(":")[0]

    record = FeedbackRecord(
        release_id=release_id,
        project_or_repo=project_or_repo,
        decision=DecisionType(decision_clean),
        reason=reason.strip(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    database.record_feedback(record)

    return f"✅ Feedback recorded successfully for `{release_id}`. Decision: **{decision_clean}**. Active learning weights updated."


@mcp.tool()
def radar_set_stack_profile(keywords: List[str], preferred_tools: List[str], banned_patterns: List[str]) -> str:
    """Update user developer profile and architectural focus.
    
    Args:
        keywords: Domain keywords (e.g. ['python', 'trading', 'quant', 'mcp']).
        preferred_tools: Target tools/libraries (e.g. ['pydantic', 'fastapi', 'litellm']).
        banned_patterns: Disliked or unsafe patterns (e.g. ['eval', 'unbounded loops', 'heavy wrappers']).
    """
    database = get_db()
    profile = UserStackProfile(
        keywords=[k.strip().lower() for k in keywords],
        preferred_tools=[t.strip().lower() for t in preferred_tools],
        banned_patterns=[b.strip().lower() for b in banned_patterns],
        notes="Updated via MCP tool",
    )
    database.set_user_profile(profile)
    return f"✅ Stack profile updated: {len(profile.keywords)} keywords, {len(profile.preferred_tools)} preferred tools."


@mcp.tool()
def radar_ingest_custom(title: str, body: str, source_url: str = "") -> str:
    """Manually ingest a changelog post, article, or release note into the radar database.
    
    Args:
        title: Title or headline of the update.
        body: Body text or description.
        source_url: Optional source link.
    """
    content_raw = f"{title}:{body}"
    content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()
    release_id = f"custom:{content_hash[:12]}"

    release = TechRelease(
        release_id=release_id,
        source_type=SourceType.MANUAL_INGEST,
        project_or_repo=title.split(":")[0].strip(),
        version=None,
        title=title,
        body=body,
        url=source_url or "custom-input",
        published_at=datetime.now(timezone.utc).isoformat(),
        content_hash=content_hash,
    )
    database = get_db()
    saved = database.save_release(release)
    if not saved:
        return f"ℹ️ Update already exists in database (release_id: `{release_id}`)."

    return f"✅ Ingested custom release: `{release_id}` ('{title}'). Ready for evaluation via `radar_check_updates()`."


def main():
    """Run FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
