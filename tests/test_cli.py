#!/usr/bin/env python3
"""Tests for skilltrust.cli."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from skilltrust.cli import format_human_output, main, detect_lang, localize_action
from skilltrust.core import (
    ScanResult, SkillInventory, TrustSettings, TokenInfo, RiskMarkers,
    build_scan_result, get_real_trust_settings,
)


def _inv(roots=None):
    """Build a SkillInventory from a {name: (count, scripts)} spec."""
    roots = roots or {}
    return SkillInventory(roots={
        name: (c, s, [f"{name}-script{i}" for i in range(s)])
        for name, (c, s) in roots.items()
    })


def _sample_result():
    inventories = _inv({"Claude Code": (5, 2), "Codex": (3, 0), "Hermes": (10, 1)})
    inventories.project_local_count = 1
    inventories.project_local_names = ["myproject"]
    trust = TrustSettings(
        hermes_trusted_paths=["/path/to/project1", "/path/to/project2"],
        hermes_trusted_count=2,
        hermes_config_state="present",
        quarantine_count=3,
        quarantine_state="present",
        claude_hooks_state="present",
        project_local_skills=[("myproject", 1)],
    )
    tokens = TokenInfo(
        scopes="'repo', 'workflow', 'delete_repo'",
        gh_available=True,
        overbroad_scopes=["workflow", "delete_repo"],
    )
    risk_markers = RiskMarkers(
        skills_with_scripts=3,
        hooks_present=True,
        trust_list_size=2,
        trusted_paths=["/path/to/project1", "/path/to/project2"],
        overbroad_token_scopes=["workflow", "delete_repo"],
    )
    return ScanResult(
        date="2026-10-09",
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action="narrow the gh token scope (5 min)",
    )


def test_format_human_output_ja():
    """Japanese human output (explicit --lang ja)."""
    output = format_human_output(_sample_result(), lang="ja")
    assert "AIエージェント信頼面スキャン — 2026-10-09" in output
    assert "[スキル在庫]" in output
    assert "Claude Code" in output and "5 skills (スクリプト同梱 2)" in output
    assert "Codex" in output and "3 skills (スクリプト同梱 0)" in output
    assert "Hermes" in output and "10 skills (スクリプト同梱 1)" in output
    assert "プロジェクト直下: 1 件 (myproject)" in output
    assert "[信頼設定]" in output
    assert "Trust済みプロジェクト: 2 件 (/path/to/project1, /path/to/project2)" in output
    assert "隔離(quarantine): 3 件" in output
    assert "Claude hooks: あり" in output
    assert "[トークン]" in output
    assert "workflow (CI経由で全repoのsecretsを抜ける)" in output
    assert "delete_repo (取り消し不能)" in output
    assert "[今日やる1つ]" in output
    assert "→ ghトークンのスコープを絞る (5分)" in output


def test_format_human_output_en():
    """English human output (explicit --lang en)."""
    output = format_human_output(_sample_result(), lang="en")
    assert "AI-agent trust-surface scan — 2026-10-09" in output
    assert "[Skill inventory]" in output
    assert "5 skills (2 script-bundled)" in output
    assert "Project-local: 1 (myproject)" in output
    assert "[Trust settings]" in output
    assert "Trusted project dirs: 2 (/path/to/project1, /path/to/project2)" in output
    assert "Quarantined: 3" in output
    assert "Claude hooks: yes" in output
    assert "[Tokens]" in output
    assert "workflow (can exfil all repo secrets via CI)" in output
    assert "delete_repo (irreversible)" in output
    assert "[Do this one thing]" in output
    assert "→ narrow the gh token scope (5 min)" in output


def test_format_human_output_defaults_ja():
    """Empty-state formatting, Japanese."""
    inventories = _inv({})
    trust = TrustSettings(
        hermes_trusted_paths=[], hermes_trusted_count=0,
        hermes_config_state="absent", quarantine_count=0,
        quarantine_state="absent", claude_hooks_state="absent",
        project_local_skills=[],
    )
    tokens = TokenInfo("unavailable", False, [])
    risk_markers = RiskMarkers(0, False, 0, [], [])
    result = ScanResult(
        date="2026-10-09",
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action="no action needed this cycle",
    )
    output = format_human_output(result, lang="ja")
    # no roots = no inventory rows
    assert "Claude Code" not in output
    assert "プロジェクト直下: 0 件 (なし)" in output
    assert "Trust済みプロジェクト: 0 件 (なし)" in output
    assert "隔離(quarantine): 0 件" in output
    assert "Claude hooks: なし" in output
    assert "gh: unavailable" in output
    assert "→ 今サイクルは対応不要" in output


def test_format_human_output_defaults_en():
    """Empty-state formatting, English."""
    inventories = _inv({})
    trust = TrustSettings(
        hermes_trusted_paths=[], hermes_trusted_count=0,
        hermes_config_state="absent", quarantine_count=0,
        quarantine_state="absent", claude_hooks_state="absent",
        project_local_skills=[],
    )
    tokens = TokenInfo("unavailable", False, [])
    risk_markers = RiskMarkers(0, False, 0, [], [])
    result = ScanResult(
        date="2026-10-09",
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action="no action needed this cycle",
    )
    output = format_human_output(result, lang="en")
    assert "Project-local: 0 (none)" in output
    assert "Trusted project dirs: 0 (none)" in output
    assert "Claude hooks: no" in output
    assert "→ no action needed this cycle" in output


def test_format_human_output_unreadable_legs():
    """An unreadable leg prints "not checked", never a clean negative."""
    inventories = _inv({})
    trust = TrustSettings(
        hermes_trusted_paths=[], hermes_trusted_count=0,
        hermes_config_state="unreadable", quarantine_count=0,
        quarantine_state="unreadable", claude_hooks_state="unreadable",
        project_local_skills=[],
    )
    tokens = TokenInfo("unavailable", False, [])
    risk_markers = RiskMarkers(
        0, False, 0, [], [],
        unreadable_legs=["claude settings", "hermes config", "quarantine dir"],
    )
    result = ScanResult(
        date="2026-10-09",
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action="resolve the not checked rows before trusting a clean scan",
    )
    output = format_human_output(result, lang="en")
    assert "Trusted project dirs: not checked (unreadable config.yaml)" in output
    assert "Quarantined: not checked (unreadable quarantine dir)" in output
    assert "Claude hooks: not checked (unreadable settings.json)" in output
    assert "Trusted project dirs: 0 (none)" not in output
    assert "  Claude hooks: no\n" not in output  # "no" ≠ prefix of "not checked"
    assert "→ resolve the not checked rows before trusting a clean scan" in output

    output_ja = format_human_output(result, lang="ja")
    assert "Trust済みプロジェクト: 確認できず (config.yamlを読み取れず)" in output_ja
    assert "隔離(quarantine): 確認できず (quarantineディレクトリを読み取れず)" in output_ja
    assert "Claude hooks: 確認できず (settings.jsonを読み取れず)" in output_ja
    assert "確認できず(not checked)の行を解決してからクリーン判定を信頼してください" in output_ja


def test_real_wiring_hooks_display_matches_action(tmp_path, monkeypatch):
    """End-to-end over the REAL trust wiring — no injected trust values.

    Regression test for the 0.1.0 finding: the trust row printed a
    hardcoded False while the action fired on the real value, so the
    report said "Claude hooks: no" right above "review
    ~/.claude/settings.json hooks".
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    # key's-own-indent spelling: valid YAML that 0.1.0 read as zero
    (tmp_path / ".hermes" / "config.yaml").write_text(
        "skills:\n  trusted_project_dirs:\n"
        "  - /proj/one\n  - /proj/two\n  - /proj/three\n  - /proj/four\n")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        '{"hooks": {"PreToolUse": []}}')

    inventories = _inv({})  # no skill roots in the fake HOME
    trust, project_local = get_real_trust_settings()
    tokens = TokenInfo("unavailable", False, [])
    result = build_scan_result(inventories, trust, tokens)

    assert result.trust.claude_hooks_state == "present"
    assert result.risk_markers.hooks_present is True
    assert result.suggested_action == "review ~/.claude/settings.json hooks"
    output = format_human_output(result, lang="en")
    assert "Claude hooks: yes" in output
    assert "Trusted project dirs: 4 (/proj/one, /proj/two, /proj/three, /proj/four)" in output
    # the display and the action must never contradict again
    assert "Claude hooks: no" not in output


def test_main_json_refuses_clean_when_unreadable(capsys):
    """--json: the clean action is refused while a leg is unreadable, and
    the legacy booleans read null (unknown), never false (= absent)."""
    with patch("skilltrust.cli.get_real_skill_inventory") as mock_skills, \
         patch("skilltrust.cli.get_real_trust_settings") as mock_trust, \
         patch("skilltrust.cli.get_real_token_info") as mock_tokens:

        mock_skills.return_value = _inv({})
        mock_trust.return_value = (
            TrustSettings(
                hermes_trusted_paths=[], hermes_trusted_count=0,
                hermes_config_state="absent", quarantine_count=0,
                quarantine_state="absent", claude_hooks_state="unreadable",
                project_local_skills=[],
            ),
            [],
        )
        mock_tokens.return_value = TokenInfo("unavailable", False, [])

        with patch("sys.argv", ["skilltrust", "scan", "--json"]):
            main()

        data = json.loads(capsys.readouterr().out)
    assert data["trust"]["claude_hooks_state"] == "unreadable"
    # null = unknown, false = checked-and-absent: a boolean-only consumer
    # must not be able to read unreadable as absent
    assert data["trust"]["claude_hooks_present"] is None
    assert data["risk_markers"]["hooks_present"] is None
    assert data["risk_markers"]["unreadable_legs"] == ["claude settings"]
    assert data["suggested_action"] == \
        "resolve the not checked rows before trusting a clean scan"


def test_main_json_nulls_every_meaningless_field_on_unreadable(capsys):
    """Horizontal sweep: EVERY field that means nothing on an unreadable
    leg is null — the two booleans, the counts, and the path lists — so no
    zero-value can be read as a clean negative."""
    with patch("skilltrust.cli.get_real_skill_inventory") as mock_skills, \
         patch("skilltrust.cli.get_real_trust_settings") as mock_trust, \
         patch("skilltrust.cli.get_real_token_info") as mock_tokens:

        mock_skills.return_value = _inv({})
        mock_trust.return_value = (
            TrustSettings(
                hermes_trusted_paths=[], hermes_trusted_count=0,
                hermes_config_state="unreadable", quarantine_count=0,
                quarantine_state="unreadable", claude_hooks_state="unreadable",
                project_local_skills=[],
            ),
            [],
        )
        mock_tokens.return_value = TokenInfo("unavailable", False, [])

        with patch("sys.argv", ["skilltrust", "scan", "--json"]):
            main()

        data = json.loads(capsys.readouterr().out)
    t = data["trust"]
    assert t["hermes_trusted_paths"] is None
    assert t["hermes_trusted_count"] is None
    assert t["quarantine_count"] is None
    assert t["claude_hooks_present"] is None
    rm = data["risk_markers"]
    assert rm["hooks_present"] is None
    assert rm["trust_list_size"] is None
    assert rm["trusted_paths"] is None
    # the states and the unreadable list carry the truth
    assert t["hermes_config_state"] == "unreadable"
    assert rm["unreadable_legs"] == ["claude settings", "hermes config", "quarantine dir"]


def test_detect_lang():
    """Locale detection: explicit flag > LC_ALL > LC_MESSAGES > LANG > en."""
    # explicit wins
    with patch.dict("os.environ", {"LANG": "ja_JP.UTF-8"}, clear=True):
        assert detect_lang("en") == "en"
        assert detect_lang("ja") == "ja"
        assert detect_lang("auto") == "ja"
    # LANG=ja -> ja
    with patch.dict("os.environ", {"LANG": "ja_JP.UTF-8"}, clear=True):
        assert detect_lang("auto") == "ja"
    # LC_ALL overrides LANG
    with patch.dict("os.environ", {"LANG": "ja_JP.UTF-8", "LC_ALL": "C.UTF-8"}, clear=True):
        assert detect_lang("auto") == "en"
    # no locale vars -> en
    with patch.dict("os.environ", {}, clear=True):
        assert detect_lang("auto") == "en"


def test_localize_action():
    """The canonical English action localizes; unknown strings pass through."""
    assert localize_action("no action needed this cycle", "ja") == "今サイクルは対応不要"
    assert localize_action("confirm provenance of the 3 script-bundled skills", "ja") \
        == "スクリプト同梱3件のスキルの由来を確認"
    assert localize_action("no action needed this cycle", "en") == "no action needed this cycle"
    assert localize_action("resolve the not checked rows before trusting a clean scan", "ja") \
        == "確認できず(not checked)の行を解決してからクリーン判定を信頼してください"
    assert localize_action("some future action", "ja") == "some future action"


def test_main_json_output(capsys):
    """--json stays language-neutral (canonical English action)."""
    with patch("skilltrust.cli.get_real_skill_inventory") as mock_skills, \
         patch("skilltrust.cli.get_real_trust_settings") as mock_trust, \
         patch("skilltrust.cli.get_real_token_info") as mock_tokens:

        mock_skills.return_value = _inv({"Claude Code": (1, 0), "Codex": (2, 0)})
        mock_trust.return_value = (
            TrustSettings(
                hermes_trusted_paths=[], hermes_trusted_count=0,
                hermes_config_state="present", quarantine_count=0,
                quarantine_state="present", claude_hooks_state="absent",
                project_local_skills=[],
            ),
            [],
        )
        mock_tokens.return_value = TokenInfo("unavailable", False, [])
        with patch("sys.argv", ["skilltrust", "scan", "--json"]):
            main()

        data = json.loads(capsys.readouterr().out)
        roots = data["inventories"]["roots"]
        assert roots["Claude Code"]["count"] == 1
        assert roots["Codex"]["count"] == 2
        assert data["inventories"]["total_skills"] == 3
        assert data["trust"]["hermes_trusted_count"] == 0
        assert data["trust"]["quarantine_count"] == 0
        assert data["trust"]["hermes_config_state"] == "present"
        assert data["trust"]["claude_hooks_state"] == "absent"
        assert data["trust"]["claude_hooks_present"] is False  # absent is false, not null
        assert data["tokens"]["gh_available"] is False
        assert data["tokens"]["scopes"] == "unavailable"
        assert data["suggested_action"] == "no action needed this cycle"


def test_main_output_to_file_ja(tmp_path):
    """--output writes the localized report to a file."""
    output_file = tmp_path / "output.txt"

    with patch("skilltrust.cli.get_real_skill_inventory") as mock_skills, \
         patch("skilltrust.cli.get_real_trust_settings") as mock_trust, \
         patch("skilltrust.cli.get_real_token_info") as mock_tokens:

        mock_skills.return_value = _inv({})
        mock_trust.return_value = (
            TrustSettings(
                hermes_trusted_paths=[], hermes_trusted_count=0,
                hermes_config_state="present", quarantine_count=0,
                quarantine_state="present", claude_hooks_state="absent",
                project_local_skills=[],
            ),
            [],
        )
        mock_tokens.return_value = TokenInfo("unavailable", False, [])

        with patch("sys.argv",
                   ["skilltrust", "scan", "--output", str(output_file), "--lang", "ja"]):
            main()

        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        # cli.py stamps date.today() — assert against today, not a baked-in date
        from datetime import date as _date
        assert f"AIエージェント信頼面スキャン — {_date.today().isoformat()}" in content
        assert "→ 今サイクルは対応不要" in content


def test_main_exit_code_io_catastrophe():
    """IO catastrophe returns exit code 1."""
    with patch("skilltrust.cli.get_real_skill_inventory", side_effect=OSError("Disk error")):
        with patch("sys.argv", ["skilltrust", "scan"]):
            assert main() == 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
