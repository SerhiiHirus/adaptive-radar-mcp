"""OSV.dev vulnerability scanner to detect known CVEs in installed dependencies."""

import logging
from typing import Any

import httpx

from adaptive_radar_mcp.scanner.manifest import ManifestScanner

logger = logging.getLogger("adaptive-radar.osv")


class OSVChecker:
    """Queries OSV.dev (Open Source Vulnerabilities) API for known security advisories."""

    API_URL = "https://api.osv.dev/v1/query"

    @classmethod
    async def check_package_vulnerability(
        cls, client: httpx.AsyncClient, package_name: str, version: str, ecosystem: str = "PyPI"
    ) -> dict[str, Any]:
        """Query OSV for a package version. Returns list of detected vulnerabilities."""
        clean_name = package_name.strip().lower()
        clean_ver = version.strip()

        if not ManifestScanner._is_safe_package_name(clean_name) or not clean_ver or clean_ver in ("any", "declared"):
            return {"package": clean_name, "version": clean_ver, "has_vulnerabilities": False, "vulns": []}

        payload = {
            "package": {
                "name": clean_name,
                "ecosystem": ecosystem,
            },
            "version": clean_ver,
        }

        try:
            response = await client.post(cls.API_URL, json=payload, timeout=6.0)
            if response.status_code != 200:
                return {"package": clean_name, "version": clean_ver, "has_vulnerabilities": False, "vulns": []}

            data = response.json()
            raw_vulns = data.get("vulns", [])
            vuln_records: list[dict[str, Any]] = []

            for v in raw_vulns:
                vuln_id = v.get("id", "UNKNOWN")
                summary = v.get("summary") or v.get("details", "")
                aliases = v.get("aliases", [])
                cve_alias = next((a for a in aliases if a.startswith("CVE-")), None)

                vuln_records.append({
                    "id": vuln_id,
                    "cve": cve_alias or vuln_id,
                    "summary": str(summary)[:200],
                    "details_url": f"https://osv.dev/vulnerability/{vuln_id}",
                })

            return {
                "package": clean_name,
                "version": clean_ver,
                "has_vulnerabilities": len(vuln_records) > 0,
                "vulns_count": len(vuln_records),
                "vulns": vuln_records,
            }
        except Exception as e:
            logger.debug("OSV query error for %s==%s: %s", clean_name, clean_ver, e)
            return {"package": clean_name, "version": clean_ver, "has_vulnerabilities": False, "vulns": []}

    @classmethod
    async def check_dependencies(
        cls, dependencies: dict[str, str], ecosystem: str = "PyPI"
    ) -> list[dict[str, Any]]:
        """Concurrently check multiple dependencies for vulnerabilities."""
        if not dependencies:
            return []

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            import asyncio
            tasks = [
                cls.check_package_vulnerability(client, pkg, ver, ecosystem=ecosystem)
                for pkg, ver in dependencies.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        flagged: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict) and r.get("has_vulnerabilities"):
                flagged.append(r)

        return flagged
