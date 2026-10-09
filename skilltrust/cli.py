#!/usr/bin/env python3
"""Command-line interface for skilltrust."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from skilltrust.core import (
    get_real_skill_inventory,
    get_real_trust_settings,
    get_real_token_info,
    build_scan_result,
)


def format_human_output(result) -> str:
    """Format the scan result as human-readable text (Japanese-first).

    One row per agent root that EXISTS and holds at least one skill; roots
    without skills are omitted (absence is not an error).
    """
    lines = []

    # Header with date
    lines.append(f"AIエージェント信頼面スキャン — {result.date}")
    lines.append("")

    # [スキル在庫]
    lines.append("[スキル在庫]")
    for name, (count, scripts, _names) in result.inventories.roots.items():
        lines.append(f"  {name:<12}: {count} skills (スクリプト同梱 {scripts})")
    if result.inventories.project_local_names:
        proj_list = "(" + ", ".join(result.inventories.project_local_names) + ")"
    else:
        proj_list = "(なし)"
    lines.append(f"  プロジェクト直下: {result.inventories.project_local_count} 件 {proj_list}")
    lines.append("")

    # [信頼設定]
    lines.append("[信頼設定]")
    if result.trust.hermes_trusted_paths:
        trusted_list = "(" + ", ".join(result.trust.hermes_trusted_paths) + ")"
    else:
        trusted_list = "(なし)"
    lines.append(f"  Hermes trust済みrepo: {result.trust.hermes_trusted_count} 件 {trusted_list}")
    lines.append(f"  隔離(quarantine): {result.trust.quarantine_count} 件")
    hooks_text = "あり" if result.trust.claude_hooks_present else "なし"
    lines.append(f"  Claude hooks: {hooks_text}")
    lines.append("")

    # [トークン]
    lines.append("[トークン]")
    if result.tokens.gh_available:
        scopes_display = result.tokens.scopes
        if result.tokens.overbroad_scopes:
            overbroad_with_reason = []
            for scope in result.tokens.overbroad_scopes:
                if scope == "workflow":
                    overbroad_with_reason.append("workflow (can exfil all repo secrets via CI)")
                elif scope == "delete_repo":
                    overbroad_with_reason.append("delete_repo (irreversible)")
                else:
                    overbroad_with_reason.append(scope)
            scopes_display += "  ← " + ", ".join(overbroad_with_reason) + " が広すぎ"
    else:
        scopes_display = "unavailable"
    lines.append(f"  gh: {scopes_display}")
    lines.append("")

    # [今日やる1つ]
    lines.append("[今日やる1つ]")
    lines.append(f"  → {result.suggested_action}")

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
            # Convert to dict for JSON serialization
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
            output_text = format_human_output(result)

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
