"""Unit tests for SemVer analysis, risk classification, and breaking changes detection."""

from adaptive_radar_mcp.evaluator.semver_analyzer import SemVerAnalyzer


def test_semver_major_upgrade():
    res = SemVerAnalyzer.analyze_version_diff("1.10.2", "2.0.0")
    assert res["diff_type"] == "MAJOR"
    assert res["risk_level"] == "HIGH"
    assert res["requires_migration_guide"] is True
    assert "Major version bump" in res["summary"]


def test_semver_minor_upgrade_clean():
    res = SemVerAnalyzer.analyze_version_diff("0.110.0", "0.115.0")
    assert res["diff_type"] == "MINOR"
    assert res["risk_level"] == "LOW"
    assert res["requires_migration_guide"] is False


def test_semver_minor_upgrade_with_breaking_changes():
    changelog = "This release introduces breaking changes for the legacy auth interface."
    res = SemVerAnalyzer.analyze_version_diff("0.110.0", "0.115.0", changelog_text=changelog)
    assert res["diff_type"] == "MINOR"
    assert res["risk_level"] == "MEDIUM"
    assert res["requires_migration_guide"] is True


def test_semver_patch_upgrade():
    res = SemVerAnalyzer.analyze_version_diff("2.4.1", "2.4.2")
    assert res["diff_type"] == "PATCH"
    assert res["risk_level"] == "LOW"
    assert res["requires_migration_guide"] is False
    assert "Patch update" in res["summary"]


def test_semver_no_op_or_downgrade():
    res = SemVerAnalyzer.analyze_version_diff("3.0.0", "2.9.0")
    assert res["diff_type"] == "NO_OP"
    assert res["risk_level"] == "LOW"


def test_semver_prefix_cleaning():
    res = SemVerAnalyzer.analyze_version_diff("v1.0.0", "release-2.0.0")
    assert res["diff_type"] == "MAJOR"
    assert res["risk_level"] == "HIGH"
