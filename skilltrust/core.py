#!/usr/bin/env python3
"""Core logic for skilltrust.

This module contains the pure logic for the skilltrust tool, fully testable
without touching the filesystem or making subprocess calls (those are handled
by dependency injection or mocking in tests).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    """Trust-related settings from various sources."""
    hermes_trusted_paths: List[str]
    hermes_trusted_count: int
    hermes_parse_error: bool
    quarantine_count: int
    claude_hooks_present: bool
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
    claude_hooks_present: bool,
) -> RiskMarkers:
    """Compute derived risk markers."""
    return RiskMarkers(
        skills_with_scripts=inventories.total_scripts,
        hooks_present=claude_hooks_present,
        trust_list_size=trust.hermes_trusted_count,
        trusted_paths=trust.hermes_trusted_paths,
        overbroad_token_scopes=tokens.overbroad_scopes,
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
    # Default
    return "no action needed this cycle"


def build_scan_result(
    inventories: SkillInventory,
    trust: TrustSettings,
    tokens: TokenInfo,
    claude_hooks_present: bool,
    project_local_skills: List[Tuple[str, int]],
) -> ScanResult:
    """Build the final ScanResult."""
    risk_markers = compute_risk_markers(
        inventories, trust, tokens, claude_hooks_present
    )
    suggested_action = determine_suggested_action(risk_markers, inventories)

    return ScanResult(
        date=date.today().isoformat(),
        inventories=inventories,
        trust=trust,
        tokens=tokens,
        risk_markers=risk_markers,
        suggested_action=suggested_action,
    )


def parse_hermes_config(config_path: Path) -> Tuple[List[str], bool]:
    """Parse ~/.hermes/config.yaml with a minimal stdlib subset parser.

    Returns:
        Tuple of (trusted_project_dirs, parse_error)
    """
    trusted_paths = []
    parse_error = False

    try:
        content = config_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Look for the pattern:
        # skills:
        #   trusted_project_dirs:
        #     - item1
        #     - item2
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            if line.lstrip() == "skills:":
                # Found skills: line
                i += 1
                # Look for trusted_project_dirs: with 2-space indent
                while i < len(lines):
                    line = lines[i].rstrip()
                    # Check for 2-space indent and the key
                    if line.startswith("  ") and line.lstrip() == "trusted_project_dirs:":
                        # Found trusted_project_dirs: line with correct indent
                        i += 1
                        # Now parse list items with 4-space indent
                        while i < len(lines):
                            line = lines[i].rstrip()
                            # If the line does not start with 4 spaces, we've left the list
                            if not line.startswith("    "):
                                break
                            # Now, after the 4 spaces, we expect a dash and a space
                            if len(line) >= 6 and line[4] == '-' and line[5] == ' ':
                                # List item with correct indent
                                item = line[6:].strip()
                                if item:
                                    trusted_paths.append(item)
                                i += 1
                            else:
                                # It's indented but not a list item, skip this line and continue
                                i += 1
                        break  # Break out of trusted_project_dirs search
                    elif not line.startswith(" ") and ":" in line:
                        # We've left the skills block (hit another top-level key)
                        break
                    else:
                        i += 1
                break  # Break out of skills: search
            elif not line.startswith(" ") and ":" in line:
                # Skip to next line for top-level keys
                i += 1
            else:
                i += 1
    except Exception:
        parse_error = True

    return trusted_paths, parse_error


def get_hermes_trust_settings(
    hermes_config_path: Path,
    hermes_quarantine_path: Path,
) -> TrustSettings:
    """Get Hermes trust settings."""
    trusted_paths, parse_error = parse_hermes_config(hermes_config_path)

    quarantine_count = 0
    try:
        if hermes_quarantine_path.is_dir():
            quarantine_count = len([p for p in hermes_quarantine_path.iterdir() if p.is_file()])
    except OSError:
        # If we can't access the quarantine directory, treat as empty
        pass

    return TrustSettings(
        hermes_trusted_paths=trusted_paths,
        hermes_trusted_count=len(trusted_paths),
        hermes_parse_error=parse_error,
        quarantine_count=quarantine_count,
        claude_hooks_present=False,  # Will be set separately
        project_local_skills=[],     # Will be set separately
    )


def get_claude_hooks_present(claude_settings_path: Path) -> bool:
    """Check if ~/.claude/settings.json has hooks key."""
    try:
        if not claude_settings_path.is_file():
            return False
        data = json.loads(claude_settings_path.read_text(encoding="utf-8"))
        return "hooks" in data
    except (json.JSONDecodeError, OSError):
        return False


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


def get_real_trust_settings() -> Tuple[TrustSettings, bool, List[Tuple[str, int]]]:
    """Get trust settings by actually checking the filesystem."""
    home = os.getenv("HOME")
    if not home:
        home_path = Path()
    else:
        home_path = Path(home)

    hermes_config = home_path / ".hermes" / "config.yaml"
    hermes_quarantine = home_path / ".hermes" / "skills" / ".hub" / "quarantine"
    claude_settings = home_path / ".claude" / "settings.json"

    trust = get_hermes_trust_settings(hermes_config, hermes_quarantine)
    claude_hooks = get_claude_hooks_present(claude_settings)

    # Project-local skills
    projects_dir = home_path / "projects"
    project_local_skills = get_project_local_skills(projects_dir)

    return trust, claude_hooks, project_local_skills


def get_real_token_info() -> TokenInfo:
    """Get token info by actually running gh auth status."""
    return get_token_scopes()


if __name__ == "__main__":
    # For debugging - run a real scan
    inventories = get_real_skill_inventory()
    trust, claude_hooks, project_local_skills = get_real_trust_settings()
    tokens = get_real_token_info()

    result = build_scan_result(
        inventories, trust, tokens, claude_hooks, project_local_skills
    )

    print(json.dumps(result.__dict__, indent=2, default=str))
