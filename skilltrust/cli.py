#!/usr/bin/env python3
"""Command-line interface for skilltrust."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from skilltrust.core import (
    get_real_skill_inventory,
    get_real_trust_settings,
    get_real_token_info,
    build_scan_result,
)

# ---------------------------------------------------------------------------
# i18n: human-readable output only. The JSON output keeps the canonical
# English action string so machine consumers and the monthly diff stay stable
# regardless of the display language.
# ---------------------------------------------------------------------------

MESSAGES = {
    "en": {
        "title": "AI-agent trust-surface scan — {date}",
        "sec_skills": "[Skill inventory]",
        "row": "  {name:<12}: {count} skills ({scripts} script-bundled)",
        "project_local": "  Project-local: {count} {names}",
        "none": "(none)",
        "root_names": {"共用 .agents": "Shared .agents"},
        "sec_trust": "[Trust settings]",
        "hermes_trusted": "  Hermes trusted repos: {count} {paths}",
        "quarantine": "  Quarantined: {count}",
        "hooks": "  Claude hooks: {value}",
        "yes": "yes",
        "no": "no",
        "sec_tokens": "[Tokens]",
        "gh": "  gh: {scopes}",
        "overbroad_suffix": "  ← {items} overbroad",
        "sec_action": "[Do this one thing]",
        "action": "  → {action}",
    },
    "ja": {
        "title": "AIエージェント信頼面スキャン — {date}",
        "sec_skills": "[スキル在庫]",
        "row": "  {name:<12}: {count} skills (スクリプト同梱 {scripts})",
        "project_local": "  プロジェクト直下: {count} 件 {names}",
        "none": "(なし)",
        "root_names": {},
        "sec_trust": "[信頼設定]",
        "hermes_trusted": "  Hermes trust済みrepo: {count} 件 {paths}",
        "quarantine": "  隔離(quarantine): {count} 件",
        "hooks": "  Claude hooks: {value}",
        "yes": "あり",
        "no": "なし",
        "sec_tokens": "[トークン]",
        "gh": "  gh: {scopes}",
        "overbroad_suffix": "  ← {items} が広すぎ",
        "sec_action": "[今日やる1つ]",
        "action": "  → {action}",
    },
}

# Canonical (English) action -> localized template.
_ACTION_JA = {
    "narrow the gh token scope (5 min)": "ghトークンのスコープを絞る (5分)",
    "review ~/.claude/settings.json hooks": "~/.claude/settings.json の hooks を確認",
    "prune trusted_project_dirs": "trusted_project_dirs を整理",
    "no action needed this cycle": "今サイクルは対応不要",
}
_ACTION_JA_SCRIPT_RE = re.compile(r"confirm provenance of the (\d+) script-bundled skills")


def detect_lang(explicit: str | None = None) -> str:
    """Resolve the display language: explicit flag, else the locale, else 'en'.

    POSIX precedence: the first SET variable wins (LC_ALL > LC_MESSAGES > LANG),
    regardless of whether it names a Japanese locale.
    """
    if explicit and explicit != "auto":
        return explicit
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "ja" if value.startswith("ja") else "en"
    return "en"


def localize_action(action: str, lang: str) -> str:
    """Translate the canonical English action string for display."""
    if lang != "ja":
        return action
    if action in _ACTION_JA:
        return _ACTION_JA[action]
    m = _ACTION_JA_SCRIPT_RE.match(action)
    if m:
        return f"スクリプト同梱{m.group(1)}件のスキルの由来を確認"
    return action


def _overbroad_item(scope: str, lang: str) -> str:
    """Localized reason for one overbroad scope."""
    if scope == "workflow":
        return ("workflow (can exfil all repo secrets via CI)" if lang != "ja"
                else "workflow (CI経由で全repoのsecretsを抜ける)")
    if scope == "delete_repo":
        return ("delete_repo (irreversible)" if lang != "ja"
                else "delete_repo (取り消し不能)")
    return scope


def format_human_output(result, lang: str = "en") -> str:
    """Format the scan result as human-readable text in the given language.

    One row per agent root that EXISTS and holds at least one skill; roots
    without skills are omitted (absence is not an error).
    """
    msg = MESSAGES.get(lang, MESSAGES["en"])
    lines = []

    # Header with date
    lines.append(msg["title"].format(date=result.date))
    lines.append("")

    # Skill inventory
    lines.append(msg["sec_skills"])
    root_names = msg.get("root_names", {})
    for name, (count, scripts, _names) in result.inventories.roots.items():
        display_name = root_names.get(name, name)
        lines.append(msg["row"].format(name=display_name, count=count, scripts=scripts))
    if result.inventories.project_local_names:
        proj_names = "(" + ", ".join(result.inventories.project_local_names) + ")"
    else:
        proj_names = msg["none"]
    lines.append(msg["project_local"].format(
        count=result.inventories.project_local_count, names=proj_names))
    lines.append("")

    # Trust settings
    lines.append(msg["sec_trust"])
    if result.trust.hermes_trusted_paths:
        trusted_list = "(" + ", ".join(result.trust.hermes_trusted_paths) + ")"
    else:
        trusted_list = msg["none"]
    lines.append(msg["hermes_trusted"].format(
        count=result.trust.hermes_trusted_count, paths=trusted_list))
    lines.append(msg["quarantine"].format(count=result.trust.quarantine_count))
    hooks_value = msg["yes"] if result.trust.claude_hooks_present else msg["no"]
    lines.append(msg["hooks"].format(value=hooks_value))
    lines.append("")

    # Tokens
    lines.append(msg["sec_tokens"])
    if result.tokens.gh_available:
        scopes_display = result.tokens.scopes
        if result.tokens.overbroad_scopes:
            items = ", ".join(
                _overbroad_item(s, lang) for s in result.tokens.overbroad_scopes
            )
            scopes_display += msg["overbroad_suffix"].format(items=items)
    else:
        scopes_display = "unavailable"
    lines.append(msg["gh"].format(scopes=scopes_display))
    lines.append("")

    # Single action
    lines.append(msg["sec_action"])
    lines.append(msg["action"].format(
        action=localize_action(result.suggested_action, lang)))

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a developer machine's AI-agent trust surface"
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Run the trust surface scan")
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text"
    )
    scan_parser.add_argument(
        "--output",
        type=Path,
        help="Write report to FILE instead of stdout"
    )
    scan_parser.add_argument(
        "--lang",
        choices=("auto", "en", "ja"),
        default="auto",
        help="human-readable output language (default: auto from locale)",
    )

    args = parser.parse_args()

    if args.command != "scan":
        parser.print_help()
        return 1

    try:
        # Gather data
        inventories = get_real_skill_inventory()
        trust_settings, claude_hooks, project_local_skills = get_real_trust_settings()
        token_info = get_real_token_info()

        inventories.project_local_count = sum(n for _p, n in project_local_skills)
        inventories.project_local_names = [p for p, _n in project_local_skills]
        trust_settings.project_local_skills = project_local_skills

        # Build result
        result = build_scan_result(
            inventories, trust_settings, token_info, claude_hooks, project_local_skills
        )

        # Format output
        if args.json:
            # JSON is language-neutral: the action stays the canonical English
            # string so the monthly diff is stable across locales.
            output_data = {
                "date": result.date,
                "inventories": {
                    "roots": {
                        name: {"count": c, "script_bundled": s, "script_names": n}
                        for name, (c, s, n) in result.inventories.roots.items()
                    },
                    "total_skills": result.inventories.total_skills,
                    "total_script_bundled": result.inventories.total_scripts,
                    "project_local_count": result.inventories.project_local_count,
                    "project_local_names": result.inventories.project_local_names,
                },
                "trust": {
                    "hermes_trusted_paths": result.trust.hermes_trusted_paths,
                    "hermes_trusted_count": result.trust.hermes_trusted_count,
                    "hermes_parse_error": result.trust.hermes_parse_error,
                    "quarantine_count": result.trust.quarantine_count,
                    "claude_hooks_present": result.trust.claude_hooks_present,
                    "project_local_skills": result.trust.project_local_skills,
                },
                "tokens": {
                    "scopes": result.tokens.scopes,
                    "gh_available": result.tokens.gh_available,
                    "overbroad_scopes": result.tokens.overbroad_scopes,
                },
                "risk_markers": {
                    "skills_with_scripts": result.risk_markers.skills_with_scripts,
                    "hooks_present": result.risk_markers.hooks_present,
                    "trust_list_size": result.risk_markers.trust_list_size,
                    "trusted_paths": result.risk_markers.trusted_paths,
                    "overbroad_token_scopes": result.risk_markers.overbroad_token_scopes,
                },
                "suggested_action": result.suggested_action,
            }
            output_text = json.dumps(output_data, indent=2, ensure_ascii=False)
        else:
            output_text = format_human_output(result, lang=detect_lang(args.lang))

        # Write output
        if args.output:
            args.output.write_text(output_text + "\n", encoding="utf-8")
        else:
            print(output_text)

        return 0

    except Exception as e:
        # IO catastrophe - exit code 1
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
