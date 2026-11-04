"""Tests for AI Radar CLI execution."""

import subprocess
import sys


def test_cli_execution_with_text(tmp_path):
    cmd = [
        sys.executable,
        "adaptive_radar_mcp/main.py",
        "--text",
        "• PydanticAI v2.65.0: added thinking effort controls and prompt caching support",
        "--output-dir",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert "Report successfully generated" in result.stdout
    assert "PydanticAI" in result.stdout
