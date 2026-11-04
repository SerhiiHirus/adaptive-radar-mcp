"""Unit tests for OSV vulnerability checker."""

import httpx
import pytest

from adaptive_radar_mcp.scanner.osv_checker import OSVChecker


@pytest.mark.asyncio
async def test_osv_vulnerability_detected():
    mock_payload = {
        "vulns": [
            {
                "id": "GHSA-v5qg-5rhg-m288",
                "aliases": ["CVE-2024-24762"],
                "summary": "multipart form data DoS vulnerability in starlette",
            }
        ]
    }

    def custom_handler(request: httpx.Request):
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(custom_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await OSVChecker.check_package_vulnerability(client, "starlette", "0.27.0")
        assert res["has_vulnerabilities"] is True
        assert res["vulns_count"] == 1
        assert res["vulns"][0]["cve"] == "CVE-2024-24762"


@pytest.mark.asyncio
async def test_osv_no_vulnerabilities():
    def custom_handler(request: httpx.Request):
        return httpx.Response(200, json={"vulns": []})

    transport = httpx.MockTransport(custom_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await OSVChecker.check_package_vulnerability(client, "pydantic", "2.9.2")
        assert res["has_vulnerabilities"] is False
        assert res["vulns_count"] == 0
        assert len(res["vulns"]) == 0
