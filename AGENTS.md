# Working agreement for this repository

Short rules for anyone — human or agent — changing `skilltrust`.

## What this tool is

A deterministic, offline, stdlib-only Python CLI that audits a developer machine's AI-agent trust surface: installed agent skills, trust settings, and token scopes. It does NOT judge skill content (no LLM, no pattern scanning) — it inventories facts so a human can review provenance and permissions.

## Ground rules

- **Deterministic and offline.** The tool must not call a network service or a model at run time. If a change needs one, it belongs in a separate tool.
- **Never rewrite code inside fenced blocks.** Fenced code blocks and their contents are passed through byte-for-byte; only the surrounding prose is reduced.
- **Tests come with the change.** `python -m pytest -q` must pass, and a new behaviour needs a test that fails without it.
- **No secrets in Git**, and no absolute paths in code, tests or docs — a clone must run anywhere.
- **Do not bypass the secret scan.** `git commit --no-verify` is never a fix for a gitleaks hit; rotate the credential and rewrite the commit.
- **The README is a promise.** Every documented command must work on a fresh clone, and a badge must point at CI rather than hardcode a test count.

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
