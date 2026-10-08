# skilltrust

**Turn verbose AI coding answers into a deterministic conclusion, minimal code, and verification steps—offline and without rewriting code.**

English | [日本語](README.ja.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

## Why it exists

AI coding assistants often answer with more prose than a learner needs. Re-reading long explanations slows down practice, while instructions such as “be concise” must be set in advance and can be ignored. Asking for a shorter answer creates another round-trip.

`concise` is a post-hoc, deterministic, offline filter. It fills that gap after an answer is produced, using the validated rule-based approach from spike 023. The demand is visible in recurring verbosity discussions on programming communities, including Reddit threads and the Hacker News item 49254381.

## Quick Start

```bash
pip install -e .
echo '# Example\n\nThe standard approach is simple.\n\n```python\nprint("hello")\n```\n\nRun it and check the output.' | concise -
```

## Usage

```bash
concise answer.md
concise - < answer.md
concise answer.md --json
concise answer.md --language ja
```

Use `-` for stdin. `--json` emits a stable object with `input_lines`, `output_lines`, `conclusion`, `code_blocks`, and `verify`. `--language` accepts `auto`, `en`, or `ja`; automatic detection uses Japanese characters in prose.

## How it works

The engine parses Markdown into heading-delimited sections while keeping fenced code blocks separate. It then emits the requested learning structure.

| Rule | Behavior |
|---|---|
| Short input | Passthrough when prose is under 10 non-fence lines and there are at most one code block |
| Conclusion | Prefer a sentence containing a conclusion marker; otherwise use the first prose sentence |
| Code | Keep blocks verbatim, deduplicate them, prefer normal examples over anti-patterns, and limit output to 3 blocks of 25 lines |
| Verification | Prefer a verification heading, then marker sentences, then a language-appropriate default |
| Language | Use English headings by default and Japanese headings when prose is at least 30% Japanese |

The supported conclusion markers include `tl;dr`, `in short`, `bottom line`, `to summarize`, `summary:`, `the standard approach`, `結論`, `要するに`, `まとめ`, `つまり`, `標準`, and `標準的`. Verification markers include `verify`, `expect`, `run it`, `run the`, `check`, `confirm`, `test`, `検証`, `確認`, `実行`, `テスト`, and `動作`.

## Limitations

- Markdown is parsed with conservative stdlib rules, not a full Markdown parser.
- Code fences are recognized by lines beginning with triple backticks; code inside them is never rewritten.
- Sentence and language detection are heuristic and may not handle every mixed-language answer.
- Anti-pattern blocks are deferred rather than deleted, so they can still appear after preferred examples.

## License

MIT
