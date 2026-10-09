# skilltrust

**Audit your AI-agent trust surface in one command: skill inventories, trust settings, and token scopes — deterministic, offline, stdlib-only. It never judges skill content; it inventories facts so you can decide by provenance and permissions.**

English | [日本語](README.ja.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![CI](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml/badge.svg)](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml)

## Why it exists

Agent skills (Claude Code `SKILL.md`, OpenClaw, Hermes skills) are prompt-payload packages: a skill's text IS an instruction to your agent, inherited alongside your shell, filesystem, and stored credentials. Research in 2026 quantified the risk — a 42,447-skill study (USENIX Security '26, "Do Not Mention This to the User") found 26.1% carry at least one vulnerability and 5.2% show clearly malicious behavior, and Snyk's ToxicSkills scan found 36% of marketplace skills defective with 76 outright malicious payloads. The ClawHavoc campaign planted 1,200+ malicious skills in a marketplace distributing a credential stealer.

The common advice — "read every skill before you use it" — does not scale and, worse, does not work: a skill that reads as safe can still be an attack, because the text you are reviewing is itself the payload. Static scanners have the same blind spot for natural-language intent. The workable defense is not reading, it is **provenance and blast radius**: know what is installed, where it came from, what it is trusted to do, and which of your tokens it could reach.

`skilltrust` is the one-command version of that inventory. It answers, for the machine it runs on:

- What agent skills are installed across the well-known agents (Claude Code, Codex, OpenClaw, Cursor, OpenCode, the shared `.agents` convention, Hermes), and which ones bundle executable scripts — the marker with a measured 2.12x higher vulnerability rate
- Which project directories are trusted to load project-local skills, and how many are quarantined
- Whether Claude Code hooks (pre-session code execution) are configured
- What scopes your GitHub token carries, flagging `workflow` and `delete_repo` as overbroad (a `workflow`-scoped token can rewrite CI to read every repo secret)
- One single suggested action for this cycle

It reads. It lists. It never judges skill text, never calls a model, never touches the network, and never prints token values.

## Quick Start

```bash
pip install -e .
skilltrust scan
```

Example output (real machine):

```
AIエージェント信頼面スキャン — 2026-10-09

[スキル在庫]
  Claude Code : 12 skills (スクリプト同梱 2)
  共用 .agents : 12 skills (スクリプト同梱 2)
  Hermes      : 84 skills (スクリプト同梱 9)
  プロジェクト直下: 0 件 (なし)

[信頼設定]
  Hermes trust済みrepo: 1 件 (/home/you/projects/example)
  隔離(quarantine): 0 件
  Claude hooks: なし

[トークン]
  gh: 'delete_repo', 'gist', 'read:org', 'workflow'  ← workflow, delete_repo が広すぎ

[今日やる1つ]
  → narrow the gh token scope (5 min)
```

## Usage

```bash
skilltrust scan                # human-readable one-screen report (Japanese)
skilltrust scan --json         # machine-readable, for diffing between runs
skilltrust scan --output FILE  # write the report to a file (monthly diff workflow)
```

Run it monthly, keep the `--json` outputs, and diff them: "what changed since last month" — new skills, new script-bundled skills, trust-list growth — is the entire recurring practice. Findings are reported with exit code 0; only an environment catastrophe (e.g. `HOME` unset) exits 1.

## What it checks

| Surface | Source | Notes |
|---|---|---|
| Skill inventory | `~/.claude/skills`, `~/.codex/skills`, `~/.openclaw/skills`, `~/.cursor/skills`, `~/.opencode/skills`, `~/.agents/skills`, `~/.hermes/skills` | Known agents' personal roots; missing roots are omitted, symlinked roots deduplicated by real path, Hermes category-subdir layout supported |
| Script-bundled skills | `*.py/sh/js/ts` under each skill dir | `__pycache__` excluded |
| Project-local skills | `~/projects/*/.hermes/skills`, `~/projects/*/.agents/skills` | These load only in trusted repos — count and project list |
| Hermes trust list | `~/.hermes/config.yaml` → `skills.trusted_project_dirs` | Minimal stdlib yaml-subset parser; a parse problem is reported, never crashes |
| Quarantine | `~/.hermes/skills/.hub/quarantine/` | Skills blocked by the hub scanner |
| Claude Code hooks | `~/.claude/settings.json` → `hooks` key | Hooks run code at session start |
| GitHub token scopes | `gh auth status` | `workflow` and `delete_repo` flagged as overbroad with reasons |

## Limitations

- It inventories; it does not detect. A "clean" report means your trust surface is *visible*, not that every skill is *safe*.
- The Hermes community-origin count is not derivable from the filesystem alone; the JSON exposes the field but the human report shows script counts instead.
- Reading `gh auth status` requires the `gh` CLI on PATH; without it the token section reports `unavailable`.

## Origin

Built as Phase 1 of the a personal problem-discovery pipeline pipeline (mining real user pain from public sources, validating demand, shipping the smallest useful artifact). Demand validation for this theme: HIGH=5 / MEDIUM=14 across Hacker News and GitHub, verdict GO — see the the problem-discovery pipeline weekly reports. The pivot from an earlier "personal leak-checklist" theme followed the pipeline's own finding that free static content in that space is saturated, while the re-formed artifact class (an audit of the user's own machine) is not copyable by static content.

## License

MIT
