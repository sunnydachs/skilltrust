#!/usr/bin/env python3
"""Tests for skilltrust.cli."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from skilltrust.cli import format_human_output, main
from skilltrust.core import ScanResult, SkillInventory, TrustSettings, TokenInfo, RiskMarkers


def test_format_human_output():
    """Test the human-readable output formatting."""
    # Create a sample result
    inventories = SkillInventory(
        claude_count=5,
        claude_scripts=2,
        agents_count=3,
        agents_scripts=0,
        hermes_count=10,
        hermes_scripts=1,
        hermes_community=2,
        project_local_count=1,
        project_local_names=["myproject"],
    )
    trust = TrustSettings(
        hermes_trusted_paths=["/path/to/project1", "/path/to/project2"],
        hermes_trusted_count=2,
        hermes_parse_error=False,
        quarantine_count=3,
        claude_hooks_present=True,
        project_local_skills=[("myproject", 1)],
    )
    tokens = TokenInfo(
        scopes="repo, workflow, delete_repo",
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
    
    output = format_human_output(result)
    # Check that key components are present
    assert "AIエージェント信頼面スキャン — 2026-10-09" in output
    assert "[スキル在庫]" in output
    assert "Claude Code : 5 skills (スクリプト同梱 2)" in output
    assert "共用 .agents : 3 skills (スクリプト同梱 0)" in output
    assert "Hermes      : 10 skills (スクリプト同梱 1)" in output
    assert "プロジェクト直下: 1 件 (myproject)" in output
    assert "[信頼設定]" in output
    assert "Hermes trust済みrepo: 2 件 (/path/to/project1, /path/to/project2)" in output
    assert "隔離(quarantine): 3 件" in output
    assert "Claude hooks: あり" in output
    assert "[トークン]" in output
    assert "gh: repo, workflow, delete_repo  ← workflow (can exfil all repo secrets via CI), delete_repo (irreversible) 理由付きで指摘" in output
    assert "[今日やる1つ]" in output
    assert "→ narrow the gh token scope (5 min)" in output


def test_format_human_output_defaults():
    """Test formatting with default/empty values."""
    inventories = SkillInventory(0,0,0,0,0,0,0,0,[])
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
    assert "Claude Code : 0 skills (スクリプト同梱 0)" in output
    assert "共用 .agents : 0 skills (スクリプト同梱 0)" in output
    assert "Hermes      : 0 skills (スクリプト同梱 0)" in output
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
        mock_skills.return_value = SkillInventory(
            claude_count=1, claude_scripts=0,
            agents_count=2, agents_scripts=0,
            hermes_count=3, hermes_scripts=0,
            hermes_community=0,
            project_local_count=0,
            project_local_names=[],
        )
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
        assert data["date"] == "2026-10-09"  # today's date
        assert data["inventories"]["claude_count"] == 1
        assert data["inventories"]["agents_count"] == 2
        assert data["inventories"]["hermes_count"] == 3
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
        mock_skills.return_value = SkillInventory(0,0,0,0,0,0,0,0,[])
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
            # Should return 1 (we can't easily check exit code from main() without SystemExit)
            # But we can check that it doesn't raise an exception when called
            try:
                main()
                # If we get here, it didn't raise, but it should have returned 1
                # Actually, main() returns the exit code, so we can check it
                pass
            except SystemExit as e:
                assert e.code == 1
            else:
                # If no SystemExit, we assume it returned normally (but it should exit via sys.exit)
                # Let's just call it and check the return value
                result = main()
                assert result == 1


if __name__ == "__main__":
    # For running the tests directly
    import pytest
    pytest.main([__file__, "-v"])
