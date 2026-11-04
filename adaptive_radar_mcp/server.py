"""FastMCP Server for Adaptive Tech Radar & Active Learning."""

import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.resources
import logging
from pathlib import Path
import re
from typing import List, Optional
import yaml

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server import MCPServer as FastMCP

from adaptive_radar_mcp.crawler.github_releases import GitHubReleasesCrawler
from adaptive_radar_mcp.crawler.rss_crawler import RSSCrawler
from adaptive_radar_mcp.evaluator.scoring import ReleaseEvaluator
from adaptive_radar_mcp.memory.active_learning import ActiveLearningEngine
from adaptive_radar_mcp.memory.db import RadarDatabase
from adaptive_radar_mcp.models import (
    DecisionType,
    FeedbackRecord,
    SourceType,
    TechRelease,
    UserStackProfile,
)
from adaptive_radar_mcp.sanitizer import ContentSanitizer

logger = logging.getLogger("adaptive-radar")
mcp = FastMCP("adaptive-radar-mcp")


def get_db() -> RadarDatabase:
    """Return database instance based on active configuration/environment."""
    return RadarDatabase()


def _load_sources_config() -> dict:
    """Load default sources safely from packaged resources or fallback."""
    try:
        data_file = importlib.resources.files("adaptive_radar_mcp.data").joinpath("default_sources.yaml")
        content = data_file.read_text(encoding="utf-8")
        return yaml.safe_load(content) or {}
    except Exception as e:
        logger.warning("Could not read packaged default_sources.yaml (%s). Using fallback.", e)
        return {
            "github_repositories": ["pydantic/pydantic-ai", "BerriAI/litellm"],
            "rss_feeds": [],
        }


@mcp.tool()
async def radar_check_updates(fetch_remote: bool = True, limit: int = 5) -> str:
    """Fetch and score recent AI/LLMOps tech updates against developer preferences and cost metrics.
    
    Args:
        fetch_remote: If True, queries tracked GitHub releases and RSS feeds before scoring.
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
                # Sanitize release content before persisting
                rel.title = ContentSanitizer.sanitize_text(rel.title, max_length=150)
                rel.body = ContentSanitizer.sanitize_text(rel.body, max_length=1000)
                database.save_release(rel)

        # 2. Fetch RSS feeds concurrently
        feeds = config.get("rss_feeds", [])
        if feeds:
            rss_crawler = RSSCrawler()
            feed_items = await rss_crawler.fetch_all(feeds, limit_per_feed=2)
            for item in feed_items:
                item.title = ContentSanitizer.sanitize_text(item.title, max_length=150)
                item.body = ContentSanitizer.sanitize_text(item.body, max_length=1000)
                database.save_release(item)

    # 3. Retrieve unreviewed releases from DB
    releases = database.get_unreviewed_releases(limit=25)
    if not releases:
        return "Radar Status: All tracked updates have already been evaluated and reviewed. No new items found."

    profile = database.get_user_profile()
    feedback_history = database.get_recent_feedback(limit=20)

    # 4. Score releases
    evaluations = [
        ReleaseEvaluator.evaluate(rel, profile, feedback_history)
        for rel in releases
    ]
    evaluations.sort(key=lambda e: e.score, reverse=True)
    top_evals = evaluations[:limit]

    # 5. Format human- and agent-friendly output with sanitized summaries
    lines = [
        f"## Adaptive Tech Radar — Evaluated {len(releases)} updates",
        f"> Stack: `{', '.join(profile.preferred_tools)}` | Decisions in memory: `{len(feedback_history)}`",
        "",
    ]

    for ev in top_evals:
        priority = "HIGH" if ev.score >= 7.0 else ("MEDIUM" if ev.score >= 4.5 else "LOW")
        lines.extend([
            f"### [{priority}] [{ev.recommended_action}] {ev.title} (Score: {ev.score}/10)",
            f"- **Release ID:** `{ev.release_id}`",
            f"- **URL:** {ev.url}",
            f"- **Token Cost Signal:** {ev.token_roi_summary}",
            f"- **Safety Verdict:** `{ev.safety_verdict}`",
            f"- **Evaluation Rationale:** {ev.rationale}",
        ])
        if ev.context7_query:
            lines.append(f"- **Context7 Verification Tool:** Call `radar_prepare_context7_verification('{ev.release_id}')`")
        lines.append("")

    lines.extend([
        "---",
        "Active Learning: Use `radar_record_feedback(release_id, decision, reason)` to approve/reject any item and train preferences.",
    ])

    return "\n".join(lines)


@mcp.tool()
def radar_prepare_context7_verification(release_id: str) -> dict:
    """Prepares structured parameters to verify the selected release via Context7 MCP.
    
    Args:
        release_id: The unique ID of the release to verify.
    Returns:
        Structured dictionary specifying library_id and target queries for Context7.
    """
    database = get_db()
    with database._get_connection() as conn:
        row = conn.execute("SELECT * FROM releases WHERE release_id = ?", (release_id,)).fetchone()
        if not row:
            return {"error": f"Release not found for ID: {release_id}"}

    project = row["project_or_repo"].split("/")[-1].lower()
    version = row["version"] or ""
    title = row["title"]

    return {
        "status": "READY_FOR_CONTEXT7_INSPECTION",
        "library_id": project,
        "suggested_actions": [
            {
                "tool": "resolve-library-id",
                "arguments": {"query": project}
            },
            {
                "tool": "query-docs",
                "arguments": {
                    "library_id": project,
                    "query": f"{version} new features API syntax".strip()
                }
            }
        ],
        "verification_objective": f"Verify official API interface and stability for {project} {version} ({title}) before generating code."
    }


@mcp.tool()
def radar_record_feedback(release_id: str, decision: str, reason: str) -> str:
    """Record developer's decision (ACCEPTED, REJECTED, OBSERVED) to train active learning memory.
    
    Args:
        release_id: The unique ID of the release (e.g. 'gh:pydantic/pydantic-ai:v2.65.0').
        decision: One of 'ACCEPTED', 'REJECTED', 'OBSERVED'.
        reason: Why you approved or rejected it (e.g. 'We need structured outputs', 'Too complex, prefer standard SDK').
    """
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
        reason=ContentSanitizer.sanitize_text(reason, max_length=200),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    database.record_feedback(record)

    return f"Recorded feedback for `{release_id}`. Decision: {decision_clean}. Preference weights updated."


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
    return f"Stack profile updated: {len(profile.keywords)} keywords, {len(profile.preferred_tools)} preferred tools."


@mcp.tool()
def radar_ingest_custom(title: str, body: str, source_url: str = "") -> str:
    """Manually ingest a changelog post, article, or release note into the radar database.
    
    Args:
        title: Title or headline of the update.
        body: Body text or description.
        source_url: Optional source link.
    """
    clean_title = ContentSanitizer.sanitize_text(title, max_length=150)
    clean_body = ContentSanitizer.sanitize_text(body, max_length=2000)

    content_raw = f"{clean_title}:{clean_body}"
    content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()
    release_id = f"custom:{content_hash[:12]}"

    release = TechRelease(
        release_id=release_id,
        source_type=SourceType.MANUAL_INGEST,
        project_or_repo=clean_title.split(":")[0].strip(),
        version=None,
        title=clean_title,
        body=clean_body,
        url=source_url or "custom-input",
        published_at=datetime.now(timezone.utc).isoformat(),
        content_hash=content_hash,
    )
    database = get_db()
    saved = database.save_release(release)
    if not saved:
        return f"Update already exists in database (release_id: `{release_id}`)."

    return f"Ingested custom release: `{release_id}` ('{clean_title}'). Ready for evaluation via `radar_check_updates()`."


def main():
    """Run FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
