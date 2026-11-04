"""Tests for SSRF validation and source formatting defenses."""

import pytest
from adaptive_radar_mcp.crawler.validator import SourceValidator


def test_github_repo_validation():
    assert SourceValidator.validate_github_repo("fastapi/fastapi") == "fastapi/fastapi"
    assert SourceValidator.validate_github_repo("pydantic/pydantic-ai") == "pydantic/pydantic-ai"

    with pytest.raises(ValueError) as exc:
        SourceValidator.validate_github_repo("https://github.com/evil/repo")
    assert "Expected format: 'owner/repo'" in str(exc.value)

    with pytest.raises(ValueError):
        SourceValidator.validate_github_repo("../../etc/passwd")


def test_rss_ssrf_blocking():
    # Reject non-https
    with pytest.raises(ValueError) as exc:
        SourceValidator.validate_rss_url("http://insecure-site.com/feed.xml")
    assert "Only HTTPS" in str(exc.value)

    # Reject localhost
    with pytest.raises(ValueError) as exc:
        SourceValidator.validate_rss_url("https://localhost/feed.xml")
    assert "SSRF Protection" in str(exc.value)

    # Reject cloud metadata IP
    with pytest.raises(ValueError) as exc:
        SourceValidator.validate_rss_url("https://169.254.169.254/latest/meta-data")
    assert "SSRF Protection" in str(exc.value)

    # Reject private 127.0.0.1
    with pytest.raises(ValueError) as exc:
        SourceValidator.validate_rss_url("https://127.0.0.1:8080/feed")
    assert "SSRF Protection" in str(exc.value)
