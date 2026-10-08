#!/usr/bin/env python3
"""Filesystem discovery for skilltrust.

This module contains the only IO-ish parts of the tool, but still uses only
the Python standard library.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple, Set


def get_skill_roots() -> List[Path]:
    """Return the three skill root directories to scan.

    These are:
        ~/.claude/skills
        ~/.agents/skills
        ~/.hermes/skills

    If HOME is not set, return an empty list.
    """
    home = os.getenv("HOME")
    if not home:
        return []
    home_path = Path(home)
    return [
        home_path / ".claude" / "skills",
        home_path / ".agents" / "skills",
        home_path / ".hermes" / "skills",
    ]


def is_skill_dir(path: Path) -> bool:
    """Return True if the directory contains a SKILL.md file or a symlink to one."""
    # Check for SKILL.md file
    if (path / "SKILL.md").is_file():
        return True
    # Check for symlink to SKILL.md
    skill_md = path / "SKILL.md"
    if skill_md.is_symlink() and skill_md.exists():
        return True
    return False


def has_executable_scripts(path: Path) -> bool:
    """Return True if the directory contains any executable script files.

    We look for *.py, *.sh, *.js, *.ts anywhere under the directory,
    excluding __pycache__ directories.
    """
    # We'll walk the directory and check file extensions.
    # We exclude __pycache__ by skipping any directory with that name.
    for root, dirs, files in os.walk(path):
        # Modify dirs in-place to skip __pycache__
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if file.endswith((".py", ".sh", ".js", ".ts")):
                return True
    return False


def scan_skills() -> Tuple[int, int, List[str]]:
    """Scan the skill roots and return:
        - total unique skill count (by real path)
        - count of skills that bundle executable scripts
        - list of skill names (the directory name) for skills with scripts
    """
    roots = get_skill_roots()
    seen_real_paths: Set[Path] = set()
    skills_with_scripts: List[str] = []

    for root in roots:
        if not root.is_dir():
            continue
        # We look one level deep for category dirs.
        # So we iterate over items in root, and if it's a directory, we check it.
        # Also, we check the root itself? The spec says "and their subdirs one level deep".
        # It doesn't explicitly say to check the root itself, but we'll check both.
        # We'll treat the root as a depth-0 directory and its immediate subdirs as depth-1.
        # We'll check the root and then each immediate subdir.
        # We'll avoid double-counting by using real paths.
        candidates = [root] if root.is_dir() else []
        if root.is_dir():
            candidates.extend([root / d for d in root.iterdir() if (root / d).is_dir()])
        for skill_dir in candidates:
            if not skill_dir.is_dir():
                continue
            if is_skill_dir(skill_dir):
                real_path = skill_dir.resolve()
                if real_path not in seen_real_paths:
                    seen_real_paths.add(real_path)
                    if has_executable_scripts(skill_dir):
                        skills_with_scripts.append(skill_dir.name)

    total_skills = len(seen_real_paths)
    script_skill_count = len(skills_with_scripts)
    return total_skills, script_skill_count, skills_with_scripts


if __name__ == "__main__":
    # For debugging
    total, script_count, script_names = scan_skills()
    print(f"Total skills: {total}")
    print(f"Skills with scripts: {script_count}")
    print(f"Script skill names: {script_names}")
