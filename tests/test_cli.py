#!/usr/bin/env python3
"""Tests for skilltrust.cli."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from skilltrust.cli import format_human_output, main
from skilltrust.core import ScanResult, SkillInventory, TrustSettings, TokenInfo, RiskMarkers


def _inv(roots=None):
    """Build a SkillInventory from a {name: (count, scripts)} spec."""
    roots = roots or {}
    return SkillInventory(roots={
        name: (c, s, [f"{name}-script{i}" for i in range(s)])
        for name, (c, s) in roots.items()
    })


def test_format_human_output():
    """Test the human-readable output formatting."""
    # Create a sample result
    inventories = _inv({"Claude Code": (5, 2), "Codex": (3, 0), "Hermes": (10, 1)})
    trust = TrustSettings(
        hermes_trusted_paths=["/path/to/project1", "/path/to/project2"],
        hermes_trusted_count=2,
        hermes_parse_error=False,
        quarantine_count=3,
        claude_hooks_present=True,
        project_local_skills=[("myproject", 1)],
    )
    tokens = TokenInfo(
        scopes="'repo', 'workflow', 'delete_repo'",
        gh_available=True,
        overbroad_scopes=["workflow", "delete_repo"],
    )
    risk_markers = RiskMarkers(
        skills_with_scripts=3,  # 2 + 0 + 1
        hooks_present=True,
        trust_list_size=2,
        trusted_paths=["/path/to/project1", "/path/to/project2"],
        overbroad_token_scopes=["workflow", "delete_repo"],
    )
    result = ScanResult(
        date="2026-10-09",
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action="narrow the gh token scope (5 min)",
    )
    result.inventories.project_local_count = 1
    result.inventories.project_local_names = ["myproject"]

    output = format_human_output(result)
    # Check that key components are present
    assert "AIエージェント信頼面スキャン — 2026-10-09" in output
    assert "[スキル在庫]" in output
    assert "Claude Code" in output and "5 skills (スクリプト同梱 2)" in output
    assert "Codex" in output and "3 skills (スクリプト同梱 0)" in output
    assert "Hermes" in output and "10 skills (スクリプト同梱 1)" in output
    assert "プロジェクト直下: 1 件 (myproject)" in output
    assert "[信頼設定]" in output
    assert "Hermes trust済みrepo: 2 件 (/path/to/project1, /path/to/project2)" in output
    assert "隔離(quarantine): 3 件" in output
    assert "Claude hooks: あり" in output
    assert "[トークン]" in output
    assert "workflow (can exfil all repo secrets via CI)" in output
    assert "delete_repo (irreversible)" in output
    assert "[今日やる1つ]" in output
    assert "→ narrow the gh token scope (5 min)" in output


def test_format_human_output_defaults():
    """Test formatting with default/empty values."""
    inventories = _inv({})
    trust = TrustSettings([],0,False,0,False,[])
    tokens = TokenInfo("unavailable", False, [])
    risk_markers = RiskMarkers(0,False,0,[],[])
    result = ScanResult(
        date="2026-10-09",
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action="no action needed this cycle",
    )

    output = format_human_output(result)
    assert "AIエージェント信頼面スキャン — 2026-10-09" in output
    # no roots = no inventory rows (only the header + project line)
    assert "Claude Code" not in output
    assert "Codex" not in output
    assert "プロジェクト直下: 0 件 (なし)" in output
    assert "Hermes trust済みrepo: 0 件 (なし)" in output
    assert "隔離(quarantine): 0 件" in output
    assert "Claude hooks: なし" in output
    assert "gh: unavailable" in output
    assert "→ no action needed this cycle" in output


def test_main_json_output(capsys):
    """Test the CLI with --json flag."""
    # We'll mock the functions that gather data
    with patch("skilltrust.cli.get_real_skill_inventory") as mock_skills, \
         patch("skilltrust.cli.get_real_trust_settings") as mock_trust, \
         patch("skilltrust.cli.get_real_token_info") as mock_tokens:

        # Set up mock return values
        mock_skills.return_value = _inv({"Claude Code": (1, 0), "Codex": (2, 0)})
        mock_trust.return_value = (
            TrustSettings(
                hermes_trusted_paths=[],
                hermes_trusted_count=0,
                hermes_parse_error=False,
                quarantine_count=0,
                claude_hooks_present=False,
                project_local_skills=[],
            ),
            False,  # claude_hooks
            []      # project_local_skills
        )
        mock_tokens.return_value = TokenInfo(
            scopes="unavailable",
            gh_available=False,
            overbroad_scopes=[],
        )

        # Call main with --json
        sys_argv = ["skilltrust", "scan", "--json"]
        with patch("sys.argv", sys_argv):
            main()

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Parse JSON and check structure
        data = json.loads(output)
        roots = data["inventories"]["roots"]
        assert roots["Claude Code"]["count"] == 1
        assert roots["Codex"]["count"] == 2
        assert data["inventories"]["total_skills"] == 3
        assert data["trust"]["hermes_trusted_count"] == 0
        assert data["trust"]["quarantine_count"] == 0
        assert data["tokens"]["gh_available"] is False
        assert data["tokens"]["scopes"] == "unavailable"
        assert data["suggested_action"] == "no action needed this cycle"


def test_main_output_to_file(tmp_path):
    """Test the CLI with --output flag."""
    output_file = tmp_path / "output.txt"

    with patch("skilltrust.cli.get_real_skill_inventory") as mock_skills, \
         patch("skilltrust.cli.get_real_trust_settings") as mock_trust, \
         patch("skilltrust.cli.get_real_token_info") as mock_tokens:

        # Set up mock return values
        mock_skills.return_value = _inv({})
        mock_trust.return_value = (
            TrustSettings([],0,False,0,False,[]),
            False,
            []
        )
        mock_tokens.return_value = TokenInfo("unavailable", False, [])

        # Call main with --output
        sys_argv = ["skilltrust", "scan", "--output", str(output_file)]
        with patch("sys.argv", sys_argv):
            main()

        # Check that file was written
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "AIエージェント信頼面スキャン — 2026-10-09" in content
        assert "→ no action needed this cycle" in content


def test_main_exit_code_io_catastrophe():
    """Test that IO catastrophe returns exit code 1."""
    with patch("skilltrust.cli.get_real_skill_inventory", side_effect=OSError("Disk error")):
        sys_argv = ["skilltrust", "scan"]
        with patch("sys.argv", sys_argv):
            result = main()
            assert result == 1


if __name__ == "__main__":
    # For running the tests directly
    import pytest
    pytest.main([__file__, "-v"])
