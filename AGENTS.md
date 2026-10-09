# Working agreement for this repository

Short rules for anyone — human or agent — changing `skilltrust`.

## What this tool is

A deterministic, offline, stdlib-only Python CLI that audits a developer machine's AI-agent trust surface: installed agent skills, trust settings, and token scopes. It does NOT judge skill content (no LLM, no pattern scanning) — it inventories facts so a human can review provenance and permissions.

## Ground rules

- **Deterministic and offline.** The tool must not call a network service or a model at run time. If a change needs one, it belongs in a separate tool.
- **Tests come with the change.** `python -m pytest -q` must pass, and a new behaviour needs a test that fails without it.
- **No secrets in Git**, and no absolute paths in code, tests or docs — a clone must run anywhere.
- **Do not bypass the secret scan.** `git commit --no-verify` is never a fix for a gitleaks hit; rotate the credential and rewrite the commit.
- **The README is a promise.** Every documented command must work on a fresh clone, and a badge must point at CI rather than hardcode a test count.

## Personal-environment non-disclosure (HARDLINE)

This repo is public; it must not reveal the author's machine, accounts or
setup. The rule covers every surface — code, comments, docstrings, test
fixtures, commit messages — because an agent can leak through any of them.

Never commit, in any form:

- The local OS username as a bare word, or any absolute path containing it
  (`/home/<user>/…`, `/Users/<user>/…`, `/mnt/c/Users/<user>/…`).
- A personal (non-noreply) email address — use the provider's noreply alias.
- The names or counts of the agents/tools/models the author personally runs.
  An example block must be labelled illustrative (`Example output (illustrative
  — counts depend on the machine it runs on)`) with invented numbers, and a
  docstring must use a generic path (`devops/my-skill/SKILL.md`), never the
  author's real one.
- Names of the author's private projects, or a personal notes-vault path.

The fleet pre-commit / commit-msg / pre-push hooks and this repo's
`.gitleaks.toml` block the mechanical cases; they are a backstop, not a
substitute for judgement. When a string is sometimes a legitimate subject of
the tool (an agent being audited, a supported path), allowlist it deliberately
— do not weaken the shared rule.

## Checks that must pass

```
pip install -e ".[dev]"
python -m pytest -q
```

## Non-goals (write into AGENTS.md)

- No content scanning/pattern matching/LLM calls — the tool never judges skill text
- No network — no fetching anything, ever
- No writes outside `--output FILE`
- No token values in output, ever
