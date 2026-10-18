#!/usr/bin/env python3
"""Core logic for skilltrust.

This module contains the pure logic for the skilltrust tool, fully testable
without touching the filesystem or making subprocess calls (those are handled
by dependency injection or mocking in tests).

Every read leg carries a tri-state (present / absent / unreadable) since
2026-10-18: a leg that could not be read must never print as a clean
negative — "checked and absent" and "could not read" are different findings.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PRESENT = "present"
ABSENT = "absent"
UNREADABLE = "unreadable"


@dataclass
class SkillInventory:
    """Results from scanning skill directories.

    ``roots`` is the per-agent inventory: {display_name: (count, scripts, names)}
    for every known root that holds at least one skill (missing/empty roots are
    omitted — the report shows only what exists). ``total_skills`` and
    ``total_scripts`` dedupe the symlinked roots by real path.
    """
    roots: Dict[str, Tuple[int, int, List[str]]] = field(default_factory=dict)
    project_local_count: int = 0
    project_local_names: List[str] = field(default_factory=list)

    @property
    def total_skills(self) -> int:
        return sum(c for c, _s, _n in self.roots.values())

    @property
    def total_scripts(self) -> int:
        return sum(s for _c, s, _n in self.roots.values())


@dataclass
class TrustSettings:
    """Trust-related settings from various sources.

    Each leg's ``*_state`` is present / absent / unreadable. An unreadable
    leg means the report did NOT check that surface, and the clean action
    is refused while any leg is unreadable.
    """
    hermes_trusted_paths: List[str]
    hermes_trusted_count: int
    hermes_config_state: str      # present | absent | unreadable
    quarantine_count: int
    quarantine_state: str         # present | absent | unreadable
    claude_hooks_state: str       # present | absent | unreadable
    project_local_skills: List[Tuple[str, int]]  # (project_name, skill_count)


@dataclass
class TokenInfo:
    """GitHub token scopes and related info."""
    scopes: str
    gh_available: bool
    overbroad_scopes: List[str] = field(default_factory=list)


@dataclass
class RiskMarkers:
    """Derived risk markers (not content-judged)."""
    skills_with_scripts: int
    hooks_present: bool
    trust_list_size: int
    trusted_paths: List[str]
    overbroad_token_scopes: List[str]
    unreadable_legs: List[str] = field(default_factory=list)


@dataclass
class ScanResult:
    """Complete result of a skilltrust scan."""
    date: str
    inventories: SkillInventory
    trust: TrustSettings
    tokens: TokenInfo
    risk_markers: RiskMarkers
    suggested_action: str


def compute_risk_markers(
    inventories: SkillInventory,
    trust: TrustSettings,
    tokens: TokenInfo,
) -> RiskMarkers:
    """Compute derived risk markers.

    All markers derive from ``trust`` — there is no second channel for the
    hooks state, so the displayed trust row and the action can never
    disagree (the 0.1.0 bug: the display leg read a hardcoded False while
    the action leg read the real value).
    """
    unreadable = []
    if trust.claude_hooks_state == UNREADABLE:
        unreadable.append("claude settings")
    if trust.hermes_config_state == UNREADABLE:
        unreadable.append("hermes config")
    if trust.quarantine_state == UNREADABLE:
        unreadable.append("quarantine dir")
    return RiskMarkers(
        skills_with_scripts=inventories.total_scripts,
        hooks_present=trust.claude_hooks_state == PRESENT,
        trust_list_size=trust.hermes_trusted_count,
        trusted_paths=trust.hermes_trusted_paths,
        overbroad_token_scopes=tokens.overbroad_scopes,
        unreadable_legs=unreadable,
    )


def determine_suggested_action(
    risk_markers: RiskMarkers,
    inventories: SkillInventory,
) -> str:
    """Determine the single suggested action based on priority."""
    # Priority 1: overbroad token scope
    if risk_markers.overbroad_token_scopes:
        return "narrow the gh token scope (5 min)"
    # Priority 2: hooks present
    if risk_markers.hooks_present:
        return "review ~/.claude/settings.json hooks"
    # Priority 3: scripts-bundled skill count > 0
    if inventories.total_scripts > 0:
        return f"confirm provenance of the {inventories.total_scripts} script-bundled skills"
    # Priority 4: trust list > 3
    if risk_markers.trust_list_size > 3:
        return "prune trusted_project_dirs"
    # A leg we could not read must refuse the clean verdict: "no action
    # needed" is only honest when everything was actually checked.
    if risk_markers.unreadable_legs:
        return "resolve the not checked rows before trusting a clean scan"
    # Default
    return "no action needed this cycle"


def build_scan_result(
    inventories: SkillInventory,
    trust: TrustSettings,
    tokens: TokenInfo,
) -> ScanResult:
    """Build the final ScanResult."""
    risk_markers = compute_risk_markers(inventories, trust, tokens)
    suggested_action = determine_suggested_action(risk_markers, inventories)

    return ScanResult(
        date=date.today().isoformat(),
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action=suggested_action,
    )


def _strip_comment(item: str) -> str:
    """Drop a trailing YAML comment (" # ...") from a scalar list item."""
    i = item.find(" #")
    return (item[:i].rstrip() if i != -1 else item).strip()


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def parse_hermes_config(config_path: Path) -> Tuple[List[str], str]:
    """Read skills.trusted_project_dirs from ~/.hermes/config.yaml.

    A valid trust list must never read as zero, so the subset parser
    accepts every spelling YAML allows for this shape:

      - items deeper than the key (the documented 4-space block form)
      - items at the key's own indent (also valid YAML)
      - the flow form ``trusted_project_dirs: [a, b]``
      - blank lines, full-line comments and trailing item comments

    Returns (trusted_paths, state) where state is:

      "present"    — the config was read; the key may or may not exist
      "absent"     — no config file (nothing configured)
      "unreadable" — the file exists but could not be read, or its value
                     has a shape this parser cannot read (never a silent 0)
    """
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], ABSENT  # no config file — nothing configured
    except (OSError, UnicodeDecodeError):
        return [], UNREADABLE

    # locate the top-level "skills:" key
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "skills:" and _indent_of(line) == 0:
            break
        i += 1
    else:
        return [], PRESENT  # no skills: block — nothing configured

    # find the trusted_project_dirs child key (any indent > 0)
    j = i + 1
    key_indent = None
    while j < n:
        line = lines[j]
        s = line.strip()
        if not s or s.startswith("#"):
            j += 1
            continue
        if _indent_of(line) == 0:
            return [], PRESENT  # left the skills: block
        if s == "trusted_project_dirs:" or s.startswith("trusted_project_dirs:"):
            key_indent = _indent_of(line)
            break
        j += 1
    if key_indent is None:
        return [], PRESENT  # no trusted_project_dirs key — none configured

    key_line = lines[j].strip()
    if key_line != "trusted_project_dirs:":
        # value on the key line: the flow form, a trailing comment, or a
        # shape we cannot read
        value = _strip_comment(key_line.split(":", 1)[1]).strip()
        if not value:
            return [], PRESENT  # explicitly empty — nothing configured
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            paths = [_strip_comment(x.strip().strip("'\""))
                     for x in inner.split(",") if x.strip()]
            return paths, PRESENT
        return [], UNREADABLE  # non-list scalar we cannot parse

    # block form: collect items at indent >= key_indent
    trusted_paths: List[str] = []
    seen_item = False
    k = j + 1
    while k < n:
        line = lines[k]
        s = line.strip()
        if not s or s.startswith("#"):
            k += 1
            continue
        indent = _indent_of(line)
        if indent < key_indent:
            break  # dedented out of the key's block
        if s.startswith("- "):
            trusted_paths.append(_strip_comment(s[2:]))
            seen_item = True
        elif indent == key_indent:
            break  # sibling key — the list ended
        else:
            # non-item content deeper than the key, before or inside the
            # list: a value shape we cannot parse — refuse rather than
            # print an undercount
            return [], UNREADABLE
        k += 1
    return trusted_paths, PRESENT


def get_claude_hooks_state(claude_settings_path: Path) -> str:
    """Tri-state read of the Claude settings file.

    "present"   — file parsed, hooks key exists
    "absent"    — no file, or a parsed file without a hooks key
    "unreadable" — the file exists but could not be read or parsed; this
                   must never print the same line as "absent"
    """
    try:
        if not claude_settings_path.is_file():
            return ABSENT
        data = json.loads(claude_settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return UNREADABLE
    return PRESENT if "hooks" in data else ABSENT


def _quarantine_facts(quarantine_path: Path) -> Tuple[int, str]:
    """Count quarantined files, tri-state."""
    try:
        if not quarantine_path.is_dir():
            return 0, ABSENT
        return len([p for p in quarantine_path.iterdir() if p.is_file()]), PRESENT
    except OSError:
        return 0, UNREADABLE


def get_project_local_skills(
    projects_dir: Path,
) -> List[Tuple[str, int]]:
    """Walk ~/projects/*/.hermes/skills and ~/projects/*/.agents/skills.

    Returns list of (project_name, skill_count) tuples.
    """

    results: List[Tuple[str, int]] = []

    try:
        if not projects_dir.is_dir():
            return results

        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            skill_count = 0
            # Check .hermes/skills
            hermes_skills = project_dir / ".hermes" / "skills"
            try:
                if hermes_skills.is_dir():
                    skill_count += sum(1 for p in hermes_skills.iterdir() if p.is_dir())
            except OSError:
                pass

            # Check .agents/skills
            agents_skills = project_dir / ".agents" / "skills"
            try:
                if agents_skills.is_dir():
                    skill_count += sum(1 for p in agents_skills.iterdir() if p.is_dir())
            except OSError:
                pass

            if skill_count > 0:
                results.append((project_dir.name, skill_count))
    except OSError:
        # If we can't access the projects directory, return empty list
        pass

    return results


def get_token_scopes(gh_timeout: int = 10) -> TokenInfo:
    """Run gh auth status and parse scopes.

    Returns TokenInfo with scopes and overbroad flags. Never reads or emits
    token values — the scopes fragment is parsed from the line that carries it
    (stdout or stderr, single-line Token: form or a Scopes: line), and the
    masked token value itself is dropped from the parsed scope list.
    """
    scopes = "unavailable"
    gh_available = False
    overbroad_scopes: List[str] = []

    try:
        env = os.environ.copy()
        env["GH_PAGER"] = "cat"
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=gh_timeout,
            env=env,
        )
        output = (result.stdout if isinstance(result.stdout, str) else "") \
            + "\n" + (result.stderr if isinstance(result.stderr, str) else "")
        if result.returncode == 0 or "scopes:" in output.lower():
            gh_available = True
            scopes_part = None
            for line in output.splitlines():
                if "scopes:" in line.lower():
                    scopes_part = line.split(":", 1)[1].strip()
                    break
            if scopes_part:
                scopes = scopes_part
                # parse scope names: strip quotes, drop the masked token value
                scopes_list = [
                    s.strip().strip("'\"").strip()
                    for s in scopes_part.split(",")
                ]
                scopes_list = [
                    s for s in scopes_list
                    if s and not s.startswith("gh") and "****" not in s
                ]
                if "workflow" in scopes_list:
                    overbroad_scopes.append("workflow")
                if "delete_repo" in scopes_list:
                    overbroad_scopes.append("delete_repo")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        gh_available = False
        scopes = "unavailable"

    return TokenInfo(
        scopes=scopes,
        gh_available=gh_available,
        overbroad_scopes=overbroad_scopes,
    )


# Helper functions for actual filesystem/subprocess calls (to be used in cli.py)
def get_real_skill_inventory() -> SkillInventory:
    """Get skill inventory by actually scanning the filesystem.

    Uses scan_paths.scan_all_roots: every known agent root that exists and
    holds at least one skill, deduped by real path across symlinked roots
    (e.g. the hyperframes trio symlinked into ~/.claude, ~/.agents AND
    ~/.hermes counts once, under the first root that holds it).
    """
    from skilltrust.scan_paths import scan_all_roots

    roots = scan_all_roots()

    # Project-local skills will be handled separately
    return SkillInventory(roots=roots)


def get_real_trust_settings() -> Tuple[TrustSettings, List[Tuple[str, int]]]:
    """Read all trust legs from the real filesystem and build the record.

    This is the one place that knows all three source paths, so the
    TrustSettings it returns carries the real tri-state of every leg —
    there is no "set separately" placeholder left to forget (the 0.1.0
    wiring bug: the hooks value was handed to the risk markers but never
    written into the trust record the human output prints).
    """
    home = os.getenv("HOME")
    home_path = Path(home) if home else Path()

    hermes_config = home_path / ".hermes" / "config.yaml"
    hermes_quarantine = home_path / ".hermes" / "skills" / ".hub" / "quarantine"
    claude_settings = home_path / ".claude" / "settings.json"

    trusted_paths, config_state = parse_hermes_config(hermes_config)
    quarantine_count, quarantine_state = _quarantine_facts(hermes_quarantine)
    hooks_state = get_claude_hooks_state(claude_settings)

    projects_dir = home_path / "projects"
    project_local_skills = get_project_local_skills(projects_dir)

    trust = TrustSettings(
        hermes_trusted_paths=trusted_paths,
        hermes_trusted_count=len(trusted_paths),
        hermes_config_state=config_state,
        quarantine_count=quarantine_count,
        quarantine_state=quarantine_state,
        claude_hooks_state=hooks_state,
        project_local_skills=project_local_skills,
    )
    return trust, project_local_skills


def get_real_token_info() -> TokenInfo:
    """Get token info by actually running gh auth status."""
    return get_token_scopes()


if __name__ == "__main__":
    # For debugging - run a real scan
    inventories = get_real_skill_inventory()
    trust, project_local_skills = get_real_trust_settings()
    tokens = get_real_token_info()

    result = build_scan_result(inventories, trust, tokens)

    print(json.dumps(result.__dict__, indent=2, default=str))
