#!/usr/bin/env python3
"""Tests for skilltrust.core."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from skilltrust.core import (
    parse_hermes_config,
    get_hermes_trust_settings,
    get_claude_hooks_present,
    get_project_local_skills,
    get_token_scopes,
    compute_risk_markers,
    determine_suggested_action,
    build_scan_result,
    SkillInventory,
    TrustSettings,
    TokenInfo,
    RiskMarkers,
    ScanResult,
)


def test_parse_hermes_config_happy_path():
    """Test parsing a normal hermes config."""
    config_content = """skills:
  trusted_project_dirs:
    - /path/to/project1
    - /path/to/project2
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, parse_error = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == ["/path/to/project1", "/path/to/project2"]
    assert parse_error is False


def test_parse_hermes_config_missing_skills_key():
    """Test parsing when skills key is missing."""
    config_content = """other_key: value
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, parse_error = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert parse_error is False


def test_parse_hermes_config_malformed_line():
    """Test parsing when there's a malformed line (should not crash)."""
    config_content = """skills:
  trusted_project_dirs:
    - /path/to/project1
    not a list item
    - /path/to/project2
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, parse_error = parse_hermes_config(Path("/fake/config.yaml"))
    # We only pick up lines that start with "    - "
    assert trusted_paths == ["/path/to/project1", "/path/to/project2"]
    assert parse_error is False


def test_parse_hermes_config_empty_file():
    """Test parsing an empty file."""
    config_content = ""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, parse_error = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert parse_error is False


def test_get_hermes_trust_settings(tmp_path):
    """Trust settings from Hermes config and quarantine."""
    # Create a temporary config file
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""skills:
  trusted_project_dirs:
    - / trusted/project
""")
    # Create a temporary quarantine directory with two files
    quarantine_dir = tmp_path / "quarantine"
    quarantine_dir.mkdir()
    (quarantine_dir / "file1").touch()
    (quarantine_dir / "file2").touch()

    trust = get_hermes_trust_settings(
        hermes_config_path=config_file,
        hermes_quarantine_path=quarantine_dir,
    )
    assert trust.hermes_trusted_paths == ["/ trusted/project"]
    assert trust.hermes_trusted_count == 1
    assert trust.hermes_parse_error is False
    assert trust.quarantine_count == 2


def test_get_claude_hooks_present():
    """Check for hooks in Claude settings."""
    # Case 1: hooks present
    settings_with_hooks = '{"hooks": {"pre-command": []}, "other": "value"}'
    with patch.object(Path, 'read_text', return_value=settings_with_hooks):
        with patch.object(Path, 'is_file', return_value=True):
            assert get_claude_hooks_present(Path("/fake/settings.json")) is True

    # Case 2: hooks absent
    settings_without_hooks = '{"other": "value"}'
    with patch.object(Path, 'read_text', return_value=settings_without_hooks):
        with patch.object(Path, 'is_file', return_value=True):
            assert get_claude_hooks_present(Path("/fake/settings.json")) is False

    # Case 3: invalid JSON
    with patch.object(Path, 'read_text', return_value="invalid json"):
        with patch.object(Path, 'is_file', return_value=True):
            assert get_claude_hooks_present(Path("/fake/settings.json")) is False


def test_get_project_local_skills(tmp_path):
    """Walk project directories for local skills."""
    # Create a temporary directory structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Project A: has .hermes/skills with 2 skills, .agents/skills with 1 skill
    proj_a = projects_dir / "projectA"
    (proj_a / ".hermes" / "skills").mkdir(parents=True)
    (proj_a / ".hermes" / "skills" / "skill1").mkdir()
    (proj_a / ".hermes" / "skills" / "skill2").mkdir()
    (proj_a / ".agents" / "skills").mkdir(parents=True)
    (proj_a / ".agents" / "skills" / "skill3").mkdir()

    # Project B: no skills
    proj_b = projects_dir / "projectB"
    proj_b.mkdir()

    # Project C: only .agents/skills with 1 skill
    proj_c = projects_dir / "projectC"
    (proj_c / ".agents" / "skills").mkdir(parents=True)
    (proj_c / ".agents" / "skills" / "skill4").mkdir()

    # Now call the function with the temporary projects_dir
    result = get_project_local_skills(projects_dir)

    # We expect two entries: projectA with 3 skills, projectC with 1 skill
    assert set(result) == {("projectA", 3), ("projectC", 1)}


def test_get_token_scopes_gh_unavailable():
    """Test when gh is not available or fails."""
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        token_info = get_token_scopes()
    assert token_info.gh_available is False
    assert token_info.scopes == "unavailable"
    assert token_info.overbroad_scopes == []


def test_get_token_scopes_gh_success():
    """Test when gh auth status succeeds and returns scopes."""
    # Case 1: with overbroad scopes
    gh_output = """
GitHub CLI auth
  • accounts: github.com
    - user: testuser (✓ Logged in)
    - token: oho__*** (not shown)
  • scopes: repo, workflow, delete_repo
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = gh_output
        token_info = get_token_scopes()
    assert token_info.gh_available is True
    assert token_info.scopes == "repo, workflow, delete_repo"
    assert set(token_info.overbroad_scopes) == {"workflow", "delete_repo"}

    # Case 2: no overbroad scopes
    gh_output2 = """
  • scopes: repo, admin:org
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = gh_output2
        token_info = get_token_scopes()
    assert token_info.gh_available is True
    assert token_info.scopes == "repo, admin:org"
    assert token_info.overbroad_scopes == []


def test_compute_risk_markers():
    """Test computation of risk markers."""
    inventories = SkillInventory(
        claude_count=10,
        claude_scripts=2,
        agents_count=5,
        agents_scripts=1,
        hermes_count=3,
        hermes_scripts=0,
        hermes_community=0,
        project_local_count=0,
        project_local_names=[],
    )
    trust = TrustSettings(
        hermes_trusted_paths=["/path1", "/path2"],
        hermes_trusted_count=2,
        hermes_parse_error=False,
        quarantine_count=0,
        claude_hooks_present=True,
        project_local_skills=[],
    )
    tokens = TokenInfo(
        scopes="repo",
        gh_available=True,
        overbroad_scopes=[],
    )
    risk_markers = compute_risk_markers(inventories, trust, tokens, claude_hooks_present=True)
    assert risk_markers.skills_with_scripts == 3  # 2 + 1 + 0
    assert risk_markers.hooks_present is True
    assert risk_markers.trust_list_size == 2
    assert risk_markers.trusted_paths == ["/path1", "/path2"]
    assert risk_markers.overbroad_token_scopes == []


def test_determine_suggested_action_priority():
    """Test that the suggested action follows the priority order."""
    # Priority 1: overbroad token scope
    risk_markers = RiskMarkers(
        skills_with_scripts=0,
        hooks_present=False,
        trust_list_size=0,
        trusted_paths=[],
        overbroad_token_scopes=["workflow"],
    )
    inventories = SkillInventory(0,0,0,0,0,0,0,0,[])
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "narrow the gh token scope (5 min)"

    # Priority 2: hooks present
    risk_markers.overbroad_token_scopes = []
    risk_markers.hooks_present = True
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "review ~/.claude/settings.json hooks"

    # Priority 3: scripts-bundled skill count > 0
    risk_markers.hooks_present = False
    inventories = SkillInventory(0,0,0,0,0,0,0,0,[])  # reset
    inventories.claude_scripts = 2
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "confirm provenance of the 2 script-bundled skills"

    # Priority 4: trust list > 3
    risk_markers.skills_with_scripts = 0
    risk_markers.trust_list_size = 4
    # Reset inventories to zero for this test
    inventories = SkillInventory(0,0,0,0,0,0,0,0,[])
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "prune trusted_project_dirs"

    # Default
    risk_markers.trust_list_size = 2
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "no action needed this cycle"


def test_build_scan_result():
    """Test building the full scan result."""
    inventories = SkillInventory(
        claude_count=1,
        claude_scripts=0,
        agents_count=2,
        agents_scripts=0,
        hermes_count=3,
        hermes_scripts=1,
        hermes_community=0,
        project_local_count=1,
        project_local_names=["myproject"],
    )
    trust = TrustSettings(
        hermes_trusted_paths=["/trusted/path"],
        hermes_trusted_count=1,
        hermes_parse_error=False,
        quarantine_count=5,
        claude_hooks_present=False,
        project_local_skills=[("myproject", 1)],
    )
    tokens = TokenInfo(
        scopes="repo",
        gh_available=True,
        overbroad_scopes=[],
    )
    result = build_scan_result(inventories, trust, tokens, claude_hooks_present=False, project_local_skills=[("myproject", 1)])
    assert result.date == "2026-10-09"  # today's date in ISO format
    assert result.inventories.claude_count == 1
    assert result.trust.hermes_trusted_count == 1
    assert result.tokens.gh_available is True
    assert result.risk_markers.skills_with_scripts == 1  # from hermes_scripts
    # With scripts-bundled skills > 0, the suggested action should be to confirm provenance
    assert result.suggested_action == "confirm provenance of the 1 script-bundled skills"


if __name__ == "__main__":
    # For running the tests directly (not recommended, but for debugging)
    import pytest
    pytest.main([__file__, "-v"])
