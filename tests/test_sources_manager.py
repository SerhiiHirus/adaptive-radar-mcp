"""Tests for dynamic sources manager."""

from adaptive_radar_mcp.sources import SourcesManager


def test_sources_crud(tmp_path):
    mgr = SourcesManager(config_dir=tmp_path)
    initial = mgr.load_sources()
    assert "github_repositories" in initial

    # Add GitHub repo
    res = mgr.add_github_repo("encode/httpx")
    assert "Successfully added" in res
    assert "encode/httpx" in mgr.load_sources()["github_repositories"]

    # Remove source
    assert mgr.remove_source("encode/httpx") is True
    assert "encode/httpx" not in mgr.load_sources()["github_repositories"]
