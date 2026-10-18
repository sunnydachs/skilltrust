#!/usr/bin/env python3
"""Tests for skilltrust.core."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from skilltrust.core import (
    parse_hermes_config,
    get_claude_hooks_state,
    get_real_trust_settings,
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
    """Test parsing a normal hermes config (documented 4-space block form)."""
    config_content = """skills:
  trusted_project_dirs:
    - /path/to/project1
    - /path/to/project2
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == ["/path/to/project1", "/path/to/project2"]
    assert state == "present"


def test_parse_hermes_config_items_at_key_own_indent():
    """Items at the key's own indent are valid YAML and must read the same.

    Regression test for the 0.1.0 finding: this spelling read as zero
    trusted dirs, so the prune action could never fire on a machine whose
    list was spelled this way.
    """
    config_content = """skills:
  trusted_project_dirs:
  - /proj/one
  - /proj/two
  - /proj/three
  - /proj/four
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == ["/proj/one", "/proj/two", "/proj/three", "/proj/four"]
    assert state == "present"


def test_parse_hermes_config_flow_form():
    """The flow form is valid YAML and must read the same."""
    config_content = "skills:\n  trusted_project_dirs: [/proj/one, /proj/two]\n"
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == ["/proj/one", "/proj/two"]
    assert state == "present"


def test_parse_hermes_config_strips_trailing_comments():
    """Trailing YAML comments must not end up inside the paths."""
    config_content = """skills:
  trusted_project_dirs:
    - /proj/one          # documented block form
    - /proj/two
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == ["/proj/one", "/proj/two"]
    assert state == "present"


def test_parse_hermes_config_missing_file_is_absent_not_error():
    """No config file = nothing configured (absent), not an error."""
    with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert state == "absent"


def test_parse_hermes_config_unreadable_file():
    """A file that exists but cannot be read must never print as zero."""
    with patch.object(Path, 'read_text', side_effect=OSError("permission denied")):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert state == "unreadable"


def test_parse_hermes_config_non_list_value_is_unreadable():
    """A value shape we cannot parse is refused, not read as zero."""
    config_content = """skills:
  trusted_project_dirs:
    one: /proj/a
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert state == "unreadable"


def test_parse_hermes_config_missing_skills_key():
    """Test parsing when skills key is missing."""
    config_content = """other_key: value
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert state == "present"


def test_parse_hermes_config_malformed_line_refuses():
    """A non-item line at item depth is not a flat list we can read.

    The 0.1.0 parser silently skipped such lines and kept collecting the
    rest — an undercount that prints as a clean negative. The tri-state
    rule: refuse the whole leg instead.
    """
    config_content = """skills:
  trusted_project_dirs:
    - /path/to/project1
    not a list item
    - /path/to/project2
"""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert state == "unreadable"


def test_parse_hermes_config_empty_file():
    """Test parsing an empty file."""
    config_content = ""
    with patch.object(Path, 'read_text', return_value=config_content):
        trusted_paths, state = parse_hermes_config(Path("/fake/config.yaml"))
    assert trusted_paths == []
    assert state == "present"


def test_get_real_trust_settings_reads_all_legs(tmp_path, monkeypatch):
    """get_real_trust_settings assembles the real tri-state of every leg.

    This is the wiring the 0.1.0 tests never walked: no injected values,
    a fake HOME with real files.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    (tmp_path / ".hermes" / "config.yaml").write_text(
        "skills:\n  trusted_project_dirs:\n    - /trusted/project\n")
    quarantine = tmp_path / ".hermes" / "skills" / ".hub" / "quarantine"
    quarantine.mkdir(parents=True)
    (quarantine / "file1").touch()
    (quarantine / "file2").touch()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"hooks": {}}')

    trust, project_local = get_real_trust_settings()

    assert trust.hermes_trusted_paths == ["/trusted/project"]
    assert trust.hermes_trusted_count == 1
    assert trust.hermes_config_state == "present"
    assert trust.quarantine_count == 2
    assert trust.quarantine_state == "present"
    assert trust.claude_hooks_state == "present"
    assert project_local == []


def test_get_claude_hooks_state():
    """Tri-state read of the Claude settings file."""
    # Case 1: hooks present
    settings_with_hooks = '{"hooks": {"pre-command": []}, "other": "value"}'
    with patch.object(Path, 'read_text', return_value=settings_with_hooks):
        with patch.object(Path, 'is_file', return_value=True):
            assert get_claude_hooks_state(Path("/fake/settings.json")) == "present"

    # Case 2: hooks absent
    settings_without_hooks = '{"other": "value"}'
    with patch.object(Path, 'read_text', return_value=settings_without_hooks):
        with patch.object(Path, 'is_file', return_value=True):
            assert get_claude_hooks_state(Path("/fake/settings.json")) == "absent"

    # Case 3: invalid JSON — unreadable, never the same line as "absent"
    with patch.object(Path, 'read_text', return_value="invalid json"):
        with patch.object(Path, 'is_file', return_value=True):
            assert get_claude_hooks_state(Path("/fake/settings.json")) == "unreadable"

    # Case 4: no file at all
    with patch.object(Path, 'is_file', return_value=False):
        assert get_claude_hooks_state(Path("/fake/settings.json")) == "absent"


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
    """Test when gh auth status succeeds and returns scopes (single-line Token: form)."""
    # Case 1: with overbroad scopes — the real gh 2.x single-line form
    gh_output = (
        "github.com\n"
        "  \u2713 Logged in to github.com account testuser (/home/you/.config/gh/hosts.yml)\n"
        "  - Active account: true\n"
        "  - Git operations protocol: https\n"
        "  - Token: gho_************************************\n"
        "  - Token scopes: 'admin:org', 'delete_repo', 'repo', 'workflow'\n"
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = gh_output
        token_info = get_token_scopes()
    assert token_info.gh_available is True
    assert "workflow" in token_info.scopes and "delete_repo" in token_info.scopes
    assert set(token_info.overbroad_scopes) == {"workflow", "delete_repo"}
    # token value must never leak into the parsed scopes
    assert "gho_" not in token_info.scopes and "****" not in token_info.scopes

    # Case 2: no overbroad scopes
    gh_output2 = "  - Token scopes: 'repo', 'admin:org'\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = gh_output2
        token_info = get_token_scopes()
    assert token_info.gh_available is True
    assert "admin:org" in token_info.scopes
    assert token_info.overbroad_scopes == []


def test_get_token_scopes_scopes_on_stderr():
    """Some gh versions print scopes to stderr."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "github.com\n  \u2713 Logged in\n"
        mock_run.return_value.stderr = "  - Token scopes: 'repo', 'workflow'\n"
        token_info = get_token_scopes()
    assert token_info.gh_available is True
    assert set(token_info.overbroad_scopes) == {"workflow"}


def _inv(roots=None, scripts_total=None):
    """Build a SkillInventory from a simple {name: (count, scripts)} spec."""
    roots = roots or {}
    return SkillInventory(roots={
        name: (c, s, [f"{name}-script{i}" for i in range(s)])
        for name, (c, s) in roots.items()
    })


def test_compute_risk_markers():
    """Test computation of risk markers."""
    inventories = _inv({"Claude Code": (10, 2), ".agents": (5, 1), "Hermes": (3, 0)})
    trust = TrustSettings(
        hermes_trusted_paths=["/path1", "/path2"],
        hermes_trusted_count=2,
        hermes_config_state="present",
        quarantine_count=0,
        quarantine_state="present",
        claude_hooks_state="present",
        project_local_skills=[],
    )
    tokens = TokenInfo(
        scopes="repo",
        gh_available=True,
        overbroad_scopes=[],
    )
    risk_markers = compute_risk_markers(inventories, trust, tokens)
    assert risk_markers.skills_with_scripts == 3  # 2 + 1 + 0
    assert risk_markers.hooks_present is True
    assert risk_markers.trust_list_size == 2
    assert risk_markers.trusted_paths == ["/path1", "/path2"]
    assert risk_markers.overbroad_token_scopes == []
    assert risk_markers.unreadable_legs == []

    # an unreadable leg is surfaced, and hooks_present derives from the state
    trust.claude_hooks_state = "unreadable"
    risk_markers = compute_risk_markers(inventories, trust, tokens)
    assert risk_markers.hooks_present is False
    assert risk_markers.unreadable_legs == ["claude settings"]


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
    inventories = _inv({})
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "narrow the gh token scope (5 min)"

    # Priority 2: hooks present
    risk_markers.overbroad_token_scopes = []
    risk_markers.hooks_present = True
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "review ~/.claude/settings.json hooks"

    # Priority 3: scripts-bundled skill count > 0
    risk_markers.hooks_present = False
    inventories = _inv({"Claude Code": (2, 2)})
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "confirm provenance of the 2 script-bundled skills"

    # Priority 4: trust list > 3
    risk_markers.skills_with_scripts = 0
    risk_markers.trust_list_size = 4
    inventories = _inv({})
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "prune trusted_project_dirs"

    # Default
    risk_markers.trust_list_size = 2
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "no action needed this cycle"

    # An unreadable leg refuses the clean verdict
    risk_markers.unreadable_legs = ["claude settings", "hermes config"]
    action = determine_suggested_action(risk_markers, inventories)
    assert action == "resolve the not checked rows before trusting a clean scan"


def test_build_scan_result():
    """Test building the full scan result."""
    inventories = _inv({"Claude Code": (1, 0), "Codex": (2, 1)})
    trust = TrustSettings(
        hermes_trusted_paths=["/trusted/path"],
        hermes_trusted_count=1,
        hermes_config_state="present",
        quarantine_count=5,
        quarantine_state="present",
        claude_hooks_state="absent",
        project_local_skills=[("myproject", 1)],
    )
    tokens = TokenInfo(
        scopes="repo",
        gh_available=True,
        overbroad_scopes=[],
    )
    result = build_scan_result(inventories, trust, tokens)
    assert result.inventories.total_skills == 3  # 1 + 2
    assert result.inventories.total_scripts == 1  # from Codex
    assert result.trust.hermes_trusted_count == 1
    assert result.tokens.gh_available is True
    assert result.risk_markers.skills_with_scripts == 1
    # With scripts-bundled skills > 0, the suggested action should be to confirm provenance
    assert result.suggested_action == "confirm provenance of the 1 script-bundled skills"


def test_skill_inventory_dedupes_symlinked_roots():
    """total_skills sums per-root unique counts — the scan already dedupes."""
    # the same trio symlinked under two roots: each root reports only its unique part
    inventories = _inv({"Claude Code": (11, 2), "Codex": (0, 0)})
    inventories.roots.pop("Codex")  # zero-skill roots are omitted
    assert inventories.total_skills == 11
    assert inventories.total_scripts == 2


if __name__ == "__main__":
    # For running the tests directly (not recommended, but for debugging)
    import pytest
    pytest.main([__file__, "-v"])
