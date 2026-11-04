"""Tests for native MCP Resources and Prompts."""

import json
from adaptive_radar_mcp.memory.db import RadarDatabase
from adaptive_radar_mcp.models import SourceType, TechRelease
from adaptive_radar_mcp.server import (
    get_radar_profile_resource,
    get_recent_releases_resource,
    get_sources_resource,
    radar_upgrade_audit_prompt,
)


def test_mcp_resources_and_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_STORAGE_DIR", str(tmp_path))
    db = RadarDatabase()

    rel = TechRelease(
        release_id="gh:test/pkg:v1",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="test/pkg",
        version="v1.0",
        title="Test Package v1.0",
        body="Secret malicious directive that must not be in resource body",
        url="https://github.com/test/pkg",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_iso_test",
    )
    db.save_release(rel)

    # 1. Profile Resource
    profile_json = get_radar_profile_resource()
    assert "preferred_tools" in profile_json

    # 2. Releases Resource
    releases_json = get_recent_releases_resource()
    releases_data = json.loads(releases_json)
    assert len(releases_data) >= 1
    # STRICT SECURITY CHECK: Ensure body is NOT exposed in resource metadata
    assert "body" not in releases_data[0]
    assert "Secret malicious directive" not in releases_json

    # 3. Sources Resource
    sources_json = get_sources_resource()
    assert "github_repositories" in sources_json

    # 4. Prompt
    prompt_text = radar_upgrade_audit_prompt()
    assert "radar_scan_workspace" in prompt_text
    assert "Context7" in prompt_text
