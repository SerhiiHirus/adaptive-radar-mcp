"""Test for Context7 verification payload generator."""

from adaptive_radar_mcp.memory.db import RadarDatabase
from adaptive_radar_mcp.models import SourceType, TechRelease
from adaptive_radar_mcp.server import radar_prepare_context7_verification


def test_prepare_context7_verification_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_STORAGE_DIR", str(tmp_path))
    db = RadarDatabase()
    rel = TechRelease(
        release_id="gh:pydantic/pydantic-ai:v2.65.0",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="pydantic/pydantic-ai",
        version="v2.65.0",
        title="PydanticAI v2.65.0",
        body="Added dynamic thinking effort",
        url="https://github.com/pydantic/pydantic-ai",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_pydantic_test",
    )
    db.save_release(rel)

    payload = radar_prepare_context7_verification("gh:pydantic/pydantic-ai:v2.65.0")
    assert payload["status"] == "READY_FOR_CONTEXT7_INSPECTION"
    assert payload["library_id"] == "pydantic-ai"
    assert any(a["tool"] == "query-docs" for a in payload["suggested_actions"])
