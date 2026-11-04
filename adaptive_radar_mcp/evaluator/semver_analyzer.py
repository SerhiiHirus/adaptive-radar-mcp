"""SemVer diff analysis and breaking change risk classification for library upgrades."""

import logging
import re
from typing import Any

from packaging.version import InvalidVersion, Version

logger = logging.getLogger("adaptive-radar.semver")

BREAKING_KEYWORDS = [
    r"\bbreaking\s+changes?\b",
    r"\bbackwards?\s+incompatible\b",
    r"\bmigration\s+guide\b",
    r"\bdeprecated\b",
    r"\bremoved\s+in\s+v",
]


class SemVerAnalyzer:
    """Classifies upgrade diffs and estimates migration risk based on semantic versioning."""

    @classmethod
    def _clean_version_string(cls, raw: str) -> str:
        """Strip prefixes like 'v' or 'release-' to normalize into standard SemVer."""
        cleaned = raw.strip().lstrip("vV")
        if cleaned.startswith("release-"):
            cleaned = cleaned[len("release-"):]
        # Remove any leading/trailing non-version chars
        match = re.search(r"(\d+(?:\.\d+)*(?:[a-zA-Z0-9\.\-\+_]*))", cleaned)
        return match.group(1) if match else cleaned

    @classmethod
    def analyze_version_diff(
        cls, current_version: str | None, new_version: str | None, changelog_text: str = ""
    ) -> dict[str, Any]:
        """Compare current and new versions to evaluate change magnitude and risk.
        
        Returns:
            dict containing diff_type (MAJOR, MINOR, PATCH, or UNKNOWN),
            risk_level (HIGH, MEDIUM, LOW), and actionable migration guidance.
        """
        if not current_version or not new_version:
            return {
                "diff_type": "UNKNOWN",
                "risk_level": "LOW",
                "requires_migration_guide": False,
                "summary": "Version diff unavailable; treat as standard update.",
            }

        cur_str = cls._clean_version_string(current_version)
        new_str = cls._clean_version_string(new_version)

        # Detect breaking change mentions in changelog text
        has_breaking_keywords = False
        lower_changelog = changelog_text.lower()
        for pattern in BREAKING_KEYWORDS:
            if re.search(pattern, lower_changelog):
                has_breaking_keywords = True
                break

        try:
            cur_v = Version(cur_str)
            new_v = Version(new_str)

            if new_v <= cur_v:
                return {
                    "diff_type": "NO_OP",
                    "risk_level": "LOW",
                    "requires_migration_guide": False,
                    "summary": f"Target version {new_str} is already satisfied by current version {cur_str}.",
                }

            if new_v.major > cur_v.major:
                diff_type = "MAJOR"
                risk_level = "HIGH"
                requires_migration_guide = True
                summary = (
                    f"Major version bump ({cur_str} -> {new_str}): Breaking changes likely. "
                    "Verify API signatures via Context7 before upgrading."
                )
            elif new_v.minor > cur_v.minor:
                diff_type = "MINOR"
                risk_level = "MEDIUM" if has_breaking_keywords else "LOW"
                requires_migration_guide = has_breaking_keywords
                summary = (
                    f"Minor version bump ({cur_str} -> {new_str}): New features and optimizations. "
                    + ("Breaking notes detected in changelog." if has_breaking_keywords else "Backwards-compatible.")
                )
            else:
                diff_type = "PATCH"
                risk_level = "LOW"
                requires_migration_guide = False
                summary = f"Patch update ({cur_str} -> {new_str}): Bugfixes and security patches. Safe upgrade."

            return {
                "diff_type": diff_type,
                "risk_level": risk_level,
                "requires_migration_guide": requires_migration_guide,
                "current_version": str(cur_v),
                "new_version": str(new_v),
                "summary": summary,
            }
        except (InvalidVersion, Exception) as e:
            logger.debug("SemVer parse failed for '%s' -> '%s': %s", current_version, new_version, e)
            risk_level = "HIGH" if has_breaking_keywords else "LOW"
            return {
                "diff_type": "UNKNOWN",
                "risk_level": risk_level,
                "requires_migration_guide": has_breaking_keywords,
                "summary": f"Custom version scheme ({current_version} -> {new_version}). "
                + ("Breaking notes detected." if has_breaking_keywords else "Inspect changelog."),
            }
