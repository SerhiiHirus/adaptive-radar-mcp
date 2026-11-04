"""FastMCP Server for Adaptive Tech Radar: Tools, Resources, Prompts, and Security Gates."""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server import MCPServer as FastMCP

from adaptive_radar_mcp.crawler.github_releases import GitHubReleasesCrawler
from adaptive_radar_mcp.crawler.rss_crawler import RSSCrawler
from adaptive_radar_mcp.evaluator.scoring import ReleaseEvaluator
from adaptive_radar_mcp.evaluator.semver_analyzer import SemVerAnalyzer
from adaptive_radar_mcp.memory.db import RadarDatabase
from adaptive_radar_mcp.models import (
    DecisionType,
    FeedbackRecord,
    SourceType,
    TechRelease,
    UserStackProfile,
)
from adaptive_radar_mcp.sanitizer import ContentSanitizer
from adaptive_radar_mcp.scanner.manifest import ManifestScanner
from adaptive_radar_mcp.scanner.osv_checker import OSVChecker
from adaptive_radar_mcp.scanner.pypi_resolver import PyPIResolver
from adaptive_radar_mcp.sources import SourcesManager

logger = logging.getLogger("adaptive-radar")
mcp = FastMCP("adaptive-radar-mcp")


def get_db() -> RadarDatabase:
    """Return database instance based on active configuration/environment."""
    return RadarDatabase()


def get_sources_manager() -> SourcesManager:
    """Return dynamic sources manager."""
    return SourcesManager()


_gh_crawler: GitHubReleasesCrawler | None = None
_rss_crawler: RSSCrawler | None = None


def get_gh_crawler() -> GitHubReleasesCrawler:
    """Return persistent singleton GitHub crawler instance preserving ETag cache across calls."""
    global _gh_crawler
    if _gh_crawler is None:
        _gh_crawler = GitHubReleasesCrawler()
    return _gh_crawler


def get_rss_crawler() -> RSSCrawler:
    """Return persistent singleton RSS crawler instance."""
    global _rss_crawler
    if _rss_crawler is None:
        _rss_crawler = RSSCrawler()
    return _rss_crawler


# ============================================================================
# 1. MCP RESOURCES (Direct Structured State without Tool Call Overhead)
# ============================================================================

@mcp.resource("radar://profile")
def get_radar_profile_resource() -> str:
    """Read active developer stack profile and preference constraints."""
    db = get_db()
    profile = db.get_user_profile()
    return profile.model_dump_json(indent=2)


@mcp.resource("radar://releases/recent")
def get_recent_releases_resource() -> str:
    """Read recent evaluated releases (Metadata Only: raw body excluded for security)."""
    db = get_db()
    releases = db.get_unreviewed_releases(limit=15)
    # Output only sanitized metadata to prevent context hijacking on auto-load
    metadata_list = [
        {
            "release_id": r.release_id,
            "project_or_repo": r.project_or_repo,
            "version": r.version,
            "title": r.title,
            "url": r.url,
            "published_at": r.published_at,
        }
        for r in releases
    ]
    return json.dumps(metadata_list, indent=2)


@mcp.resource("radar://sources")
def get_sources_resource() -> str:
    """Read active upstream tracking sources and configurations."""
    mgr = get_sources_manager()
    return json.dumps(mgr.load_sources(), indent=2)


# ============================================================================
# 2. MCP PROMPTS (Standardized Guided Workflows)
# ============================================================================

@mcp.prompt("radar-upgrade-audit")
def radar_upgrade_audit_prompt() -> str:
    """Workflow prompt guiding the assistant through workspace dependency audit and verified upgrades."""
    return (
        "You are performing an architectural dependency audit using Adaptive Tech Radar.\n\n"
        "Instructions:\n"
        "1. First, call `radar_scan_workspace(directory='.')` and `radar_audit_security(directory='.')` to inspect local manifests (uv.lock, pyproject.toml, package.json) and flag any CVE vulnerabilities.\n"
        "2. Call `radar_discover_sources_from_workspace(add_to_sources=True)` to map project dependencies to official GitHub repos via PyPI.\n"
        "3. Next, call `radar_check_updates()` to fetch recent verified releases matching your detected libraries.\n"
        "4. For any release marked [HIGH] or [IMPLEMENT], call `radar_prepare_context7_verification(release_id)`.\n"
        "5. Query Context7 MCP with the prepared parameters to verify live API signatures or migration guides.\n"
        "6. Formulate a concise upgrade recommendation showing: Target Library, Current Version, New Version, Migration Risk, Token ROI benefit, and verified code snippet."
    )


# ============================================================================
# 3. MCP TOOLS (Active Operations, Scanning, and Feedback)
# ============================================================================

@mcp.tool()
def radar_scan_workspace(directory: str = ".", apply_to_profile: bool = False) -> dict:
    """Safely scan project workspace for dependency manifests (pyproject.toml, requirements.txt, package.json).
    
    Args:
        directory: Target directory within current project boundary (Path traversal is strictly prevented).
        apply_to_profile: If True, automatically merges detected dependencies into preferred tools profile.
    Returns:
        Structured dictionary of detected dependencies and status.
    """
    try:
        allowed_root = Path(os.environ.get("RADAR_WORKSPACE_ROOT", Path.cwd()))
        detected = ManifestScanner.scan_directory(directory, allowed_root=allowed_root)
        applied = False
        if apply_to_profile and detected:
            db = get_db()
            profile = db.get_user_profile()
            merged_tools = sorted(set(profile.preferred_tools + list(detected.keys())))[:30]
            profile.preferred_tools = merged_tools
            db.set_user_profile(profile)
            applied = True

        return {
            "status": "SUCCESS",
            "directory": directory,
            "dependencies_count": len(detected),
            "detected_packages": detected,
            "profile_updated": applied,
            "recommendation": "Dependencies successfully linked to radar preferences." if applied else "Pass apply_to_profile=True to link these packages directly."
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


@mcp.tool()
async def radar_check_updates(fetch_remote: bool = True, limit: int = 5) -> str:
    """Fetch and score recent AI/LLMOps tech updates against developer preferences and cost metrics.
    
    Args:
        fetch_remote: If True, queries tracked GitHub releases and RSS feeds before scoring.
        limit: Maximum number of evaluated recommendations to return.
    """
    mgr = get_sources_manager()
    config = mgr.load_sources()
    database = get_db()

    if fetch_remote:
        # Fetch GitHub releases and RSS feeds concurrently in parallel
        repos = config.get("github_repositories", [])
        feeds = config.get("rss_feeds", [])

        gh_task = get_gh_crawler().fetch_all(repos) if repos else asyncio.sleep(0, result=[])
        rss_task = get_rss_crawler().fetch_all(feeds, limit_per_feed=2) if feeds else asyncio.sleep(0, result=[])

        gh_releases, feed_items = await asyncio.gather(gh_task, rss_task)

        for rel in gh_releases:
            rel.title = ContentSanitizer.sanitize_title(rel.title)
            rel.body = ContentSanitizer.sanitize_text(rel.body, max_length=1000)
            database.save_release(rel)

        for item in feed_items:
            item.title = ContentSanitizer.sanitize_title(item.title)
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

    # 5. Format output
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
    row = database.get_release_by_id(release_id)
    if not row:
        return {"error": f"Release not found for ID: {release_id}"}

    project = row["project_or_repo"].split("/")[-1].lower()
    version = row["version"] or ""
    title = row["title"]
    body_text = row.get("body") or ""

    semver_info = SemVerAnalyzer.analyze_version_diff(
        current_version=None, new_version=version, changelog_text=body_text
    )

    if semver_info.get("requires_migration_guide"):
        doc_query = f"{project} migration guide {version} breaking changes".strip()
    else:
        doc_query = f"{version} new features API syntax".strip()

    risk_warn = " [MIGRATION RISK: HIGH]" if semver_info.get("risk_level") == "HIGH" else ""

    return {
        "status": "READY_FOR_CONTEXT7_INSPECTION",
        "library_id": project,
        "semver_risk": semver_info.get("risk_level", "LOW"),
        "suggested_actions": [
            {
                "tool": "resolve-library-id",
                "arguments": {"query": project}
            },
            {
                "tool": "query-docs",
                "arguments": {
                    "library_id": project,
                    "query": doc_query
                }
            }
        ],
        "verification_objective": f"Verify official API interface and stability for {project} {version} ({title}){risk_warn} before generating code."
    }


@mcp.tool()
async def radar_audit_security(directory: str = ".") -> dict:
    """Audit project dependencies against OSV.dev for known security advisories (CVEs).
    
    Args:
        directory: Target workspace directory to scan.
    Returns:
        Structured audit of detected security vulnerabilities and CVE advisory links.
    """
    try:
        allowed_root = Path(os.environ.get("RADAR_WORKSPACE_ROOT", Path.cwd()))
        detected = ManifestScanner.scan_directory(directory, allowed_root=allowed_root)
        if not detected:
            return {"status": "SUCCESS", "message": "No dependencies detected in directory.", "vulnerabilities": []}

        flagged = await OSVChecker.check_dependencies(detected)
        return {
            "status": "SUCCESS",
            "dependencies_scanned": len(detected),
            "vulnerabilities_found": len(flagged),
            "advisories": flagged,
            "action_required": (
                "CRITICAL: Upgrade vulnerable packages immediately." if flagged else "All packages clear."
            ),
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


@mcp.tool()
async def radar_discover_sources_from_workspace(directory: str = ".", add_to_sources: bool = False) -> dict:
    """Discover official GitHub repositories for workspace dependencies via PyPI JSON API.
    
    [State-Mutating if add_to_sources=True]: Can add discovered repositories to tracked radar sources.
    
    Args:
        directory: Workspace directory to scan for dependencies.
        add_to_sources: If True, automatically adds discovered GitHub repositories to radar monitoring.
    Returns:
        Dictionary mapping dependencies to discovered GitHub repositories and tracking status.
    """
    try:
        allowed_root = Path(os.environ.get("RADAR_WORKSPACE_ROOT", Path.cwd()))
        detected = ManifestScanner.scan_directory(directory, allowed_root=allowed_root)
        if not detected:
            return {"status": "SUCCESS", "message": "No packages found to resolve.", "discovered": {}}

        resolved = await PyPIResolver.resolve_packages(list(detected.keys()))
        discovered: dict[str, Any] = {}
        added: list[str] = []
        mgr = get_sources_manager()

        for pkg_name, info in resolved.items():
            repo = info.get("github_repo")
            if repo:
                discovered[pkg_name] = {
                    "installed_version": detected.get(pkg_name),
                    "latest_pypi_version": info.get("latest_version"),
                    "github_repo": repo,
                }
                if add_to_sources:
                    try:
                        mgr.add_github_repo(repo)
                        added.append(repo)
                    except Exception:
                        pass

        return {
            "status": "SUCCESS",
            "scanned_packages": len(detected),
            "discovered_repositories_count": len(discovered),
            "discovered": discovered,
            "added_to_tracked_sources": added if add_to_sources else [],
            "recommendation": (
                "Tracked sources updated." if added else "Run with add_to_sources=True to monitor these repos."
            ),
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


@mcp.tool()
def radar_add_source(source_type: str, target: str, name: str = "") -> str:
    """Add a new GitHub repository or RSS feed to the radar monitor with strict SSRF defense.
    
    Args:
        source_type: One of 'github' (for GitHub repo owner/name) or 'rss' (for HTTPS RSS/Atom feed).
        target: For 'github', provide 'owner/repo' (e.g. 'fastapi/fastapi'). For 'rss', provide HTTPS URL.
        name: Optional human-readable name for RSS feed.
    """
    mgr = get_sources_manager()
    stype = source_type.lower().strip()
    try:
        if stype == "github":
            return mgr.add_github_repo(target)
        elif stype == "rss":
            feed_name = name.strip() or target
            return mgr.add_rss_feed(feed_name, target)
        else:
            return f"Error: source_type must be 'github' or 'rss' (got: '{source_type}')."
    except Exception as e:
        return f"Source Validation Failed: {e}"


@mcp.tool()
def radar_list_sources() -> dict:
    """List all currently configured upstream tracking sources."""
    mgr = get_sources_manager()
    return mgr.load_sources()


@mcp.tool()
def radar_remove_source(identifier: str) -> str:
    """Remove a tracked source by repository identifier or RSS URL.
    
    Args:
        identifier: 'owner/repo' or RSS URL/Name to remove.
    """
    mgr = get_sources_manager()
    success = mgr.remove_source(identifier.strip())
    if success:
        return f"Successfully removed source '{identifier}'."
    return f"Source '{identifier}' was not found in active configuration."


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
def radar_set_stack_profile(keywords: list[str], preferred_tools: list[str], banned_patterns: list[str]) -> str:
    """Update user developer profile and architectural focus.
    
    Args:
        keywords: Domain keywords (max 30 items, e.g. ['python', 'asyncio', 'mcp']).
        preferred_tools: Target tools/libraries (max 30 items, e.g. ['pydantic', 'fastapi', 'litellm']).
        banned_patterns: Disliked or unsafe patterns (max 30 items, e.g. ['eval', 'unbounded loops']).
    """
    database = get_db()
    clean_keywords = [ContentSanitizer.sanitize_text(k.strip().lower(), max_length=50) for k in keywords[:30]]
    clean_preferred = [ContentSanitizer.sanitize_text(t.strip().lower(), max_length=50) for t in preferred_tools[:30]]
    clean_banned = [ContentSanitizer.sanitize_text(b.strip().lower(), max_length=50) for b in banned_patterns[:30]]

    profile = UserStackProfile(
        keywords=[k for k in clean_keywords if k],
        preferred_tools=[t for t in clean_preferred if t],
        banned_patterns=[b for b in clean_banned if b],
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
    clean_title = ContentSanitizer.sanitize_title(title, max_length=150)
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
