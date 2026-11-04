"""Unit tests for PyPI repository discovery and URL parsing."""

import httpx
import pytest

from adaptive_radar_mcp.scanner.pypi_resolver import PyPIResolver


def test_extract_github_repo_from_url():
    assert PyPIResolver._extract_github_repo_from_url("https://github.com/tiangolo/fastapi") == "tiangolo/fastapi"
    assert PyPIResolver._extract_github_repo_from_url("https://github.com/pydantic/pydantic.git") == "pydantic/pydantic"
    assert PyPIResolver._extract_github_repo_from_url("https://github.com/vercel/next.js/") == "vercel/next.js"
    assert PyPIResolver._extract_github_repo_from_url("https://evil.com/fake/repo") is None
    assert PyPIResolver._extract_github_repo_from_url("https://github.com/../traversal") is None


@pytest.mark.asyncio
async def test_resolve_package_mocked():
    mock_payload = {
        "info": {
            "version": "0.115.0",
            "project_urls": {
                "Source": "https://github.com/tiangolo/fastapi",
                "Homepage": "https://fastapi.tiangolo.com/",
            },
            "summary": "FastAPI framework, high performance, easy to learn.",
        }
    }

    def custom_handler(request: httpx.Request):
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(custom_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await PyPIResolver.resolve_package(client, "fastapi")
        assert res is not None
        assert res["package_name"] == "fastapi"
        assert res["latest_version"] == "0.115.0"
        assert res["github_repo"] == "tiangolo/fastapi"
