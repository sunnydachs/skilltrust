# skilltrust

**Audit your AI-agent trust surface in one command: skill inventories, trust settings, and token scopes — deterministic, offline, stdlib-only. It never judges skill content; it inventories facts so you can decide by provenance and permissions.**

English | [日本語](README.ja.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![CI](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml/badge.svg)](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml)

## Why it exists

Agent skills (Claude Code `SKILL.md`, OpenClaw) are prompt-payload packages: a skill's text IS an instruction to your agent, inherited alongside your shell, filesystem, and stored credentials. Research in 2026 quantified the risk — the study behind NVIDIA's SkillSpector ("Agent Skills in the Wild", Liu et al.) analyzed 31,132 of 42,447 collected skills and found 26.1% carry at least one vulnerability and 5.2% show likely malicious intent; the USENIX Security '26 paper "Do Not Mention This to the User" behaviorally confirmed 157 of 98,380 analyzed skills as malicious. Snyk's ToxicSkills scan found 36.8% of 3,984 marketplace skills defective, 76 of them outright malicious payloads. An audit of the ClawHavoc campaign confirmed 341 malicious skills distributing the Atomic Stealer credential stealer. Primary sources: [SkillSpector research background](https://github.com/nvidia/skillspector) · [USENIX Security '26](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yi) · [Snyk ToxicSkills](https://research.snyk.io/blog/agent-skills-threat-landscape/) · [ClawHavoc audit](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html)

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

Example output (illustrative — counts depend on the machine it runs on):

```
AI-agent trust-surface scan — 2026-10-09

[Skill inventory]
  Claude Code : 12 skills (2 script-bundled)
  .agents     : 10 skills (2 script-bundled)
  Hermes      : 84 skills (9 script-bundled)
  Project-local: 0 (none)

[Trust settings]
  Trusted project dirs: 1 (/home/you/projects/example)
  Quarantined: 0
  Claude hooks: no

[Tokens]
  gh: 'delete_repo', 'gist', 'read:org', 'workflow'  ← workflow, delete_repo overbroad

[Do this one thing]
  → narrow the gh token scope (5 min)
```

## Usage

```bash
skilltrust scan                    # human-readable one-screen report (locale-aware)
skilltrust scan --lang en|ja|auto  # force the display language (default: auto from locale)
skilltrust scan --json             # machine-readable, for diffing between runs
skilltrust scan --output FILE      # write the report to a file (monthly diff workflow)
```

The human-readable report follows your locale (`LC_ALL` / `LC_MESSAGES` / `LANG`) and defaults to English when none is set; `--lang` overrides it. The `--json` output stays language-neutral on purpose — the `suggested_action` is always the canonical English string, so a monthly diff is stable no matter where it runs.

Run it monthly, keep the `--json` outputs, and diff them: "what changed since last month" — new skills, new script-bundled skills, trust-list growth — is the recurring safety net. The primary cadence is event-driven, not calendar-driven: run `skilltrust scan` right after any event that can change your trust surface — installing or updating a skill (`hermes skills install`, a marketplace install, a manual drop into `~/.claude/skills`), a `git pull` in a trusted repo that can bring new skills in, or re-issuing a token. The scan costs under a second and never calls a model, so there is no reason to defer it; the monthly diff exists only to catch the events you forgot. Findings are reported with exit code 0; only an environment catastrophe (e.g. `HOME` unset) exits 1.

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

Built as the first artifact of a personal problem-discovery pipeline (mine real user pain from public sources, validate demand, ship the smallest useful artifact). Demand for this theme was validated as GO across Hacker News and GitHub before any code was written. The pivot away from an earlier "personal leak-checklist" theme followed the pipeline's own finding that free static content in that space is saturated, while this artifact class (an audit of the user's own machine) is not copyable by static content.

## License

MIT
