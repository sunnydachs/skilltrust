#!/usr/bin/env python3
"""Filesystem discovery for skilltrust.

This module contains the only IO-ish parts of the tool, but still uses only
the Python standard library.

Known personal skill roots for the well-known agents (2026-10, verified
against published docs — agensi.io path guide, opencode.ai docs):

    ~/.claude/skills     Claude Code / Claude Desktop (personal)
    ~/.codex/skills      OpenAI Codex CLI
    ~/.openclaw/skills   OpenClaw (SKILL.md format identical)
    ~/.cursor/skills     Cursor
    ~/.opencode/skills   OpenCode
    ~/.agents/skills     cross-agent shared convention
    ~/.hermes/skills     Hermes Agent (category-subdir layout)

Project-scoped roots (<repo>/.claude/skills etc.) load only in trusted repos;
they are inventoried separately by walking ~/projects (see core.py).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set


# (root-relative path, display name) — display order == report order
KNOWN_SKILL_ROOTS: List[Tuple[str, str]] = [
    (os.path.join(".claude", "skills"), "Claude Code"),
    (os.path.join(".codex", "skills"), "Codex"),
    (os.path.join(".openclaw", "skills"), "OpenClaw"),
    (os.path.join(".cursor", "skills"), "Cursor"),
    (os.path.join(".opencode", "skills"), "OpenCode"),
    (os.path.join(".agents", "skills"), ".agents"),
    (os.path.join(".hermes", "skills"), "Hermes"),
]


def get_skill_roots() -> List[Path]:
    """Return the well-known personal skill roots that exist on this machine.

    Missing roots are omitted (never an error). If HOME is not set, return [].
    """
    home = os.getenv("HOME")
    if not home:
        return []
    home_path = Path(home)
    roots = []
    for rel, _name in KNOWN_SKILL_ROOTS:
        p = home_path / rel
        if p.is_dir():
            roots.append(p)
    return roots


def is_skill_dir(path: Path) -> bool:
    """Return True if the directory contains a SKILL.md file or a symlink to one."""
    skill_md = path / "SKILL.md"
    return skill_md.is_file() or skill_md.is_symlink()


def has_executable_scripts(path: Path) -> bool:
    """Return True if the directory contains any executable script files.

    We look for *.py, *.sh, *.js, *.ts anywhere under the directory,
    excluding __pycache__ directories.
    """
    for root, dirs, files in os.walk(path):
        # Modify dirs in-place to skip __pycache__
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if file.endswith((".py", ".sh", ".js", ".ts")):
                return True
    return False


def _iter_skill_dirs(root: Path):
    """Yield skill dirs under one root: the root itself (if it holds SKILL.md),
    immediate subdirs holding SKILL.md, and — for category dirs (a subdir with
    no SKILL.md at its own level) — the category's immediate subdirs (the
    ~/.hermes/skills layout, e.g. devops/my-skill/SKILL.md)."""
    if is_skill_dir(root):
        yield root
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if is_skill_dir(d):
            yield d
        else:
            for s in d.iterdir():
                if s.is_dir() and not s.name.startswith(".") and is_skill_dir(s):
                    yield s


def scan_all_roots() -> Dict[str, Tuple[int, int, List[str]]]:
    """Scan every known root that exists.

    Returns {display_name: (unique count, script-bundled count, script names)}.
    A root with zero skills is omitted from the result (the report shows only
    roots that hold something). Dedup across roots is by real path, so the
    symlinked trio shared between .claude/.agents/.codex counts once — under
    the first root that holds it.
    """
    out: Dict[str, Tuple[int, int, List[str]]] = {}
    global_seen: Set[Path] = set()
    home = os.getenv("HOME")
    if not home:
        return out
    home_path = Path(home)
    for rel, name in KNOWN_SKILL_ROOTS:
        root = home_path / rel
        if not root.is_dir():
            continue
        unique = 0
        scripts = 0
        unique_names: List[str] = []
        for sd in _iter_skill_dirs(root):
            real_path = sd.resolve()
            if real_path in global_seen:
                continue
            global_seen.add(real_path)
            unique += 1
            if has_executable_scripts(sd):
                scripts += 1
                unique_names.append(sd.name)
        if unique:
            out[name] = (unique, scripts, unique_names)
    return out


if __name__ == "__main__":
    # For debugging
    for name, (count, scripts, names) in scan_all_roots().items():
        print(f"{name}: {count} skills ({scripts} with scripts)")
        if names:
            print(f"  scripts: {', '.join(names[:6])}")
