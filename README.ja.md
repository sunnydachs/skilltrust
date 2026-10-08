# skilltrust

**冗長なAIコーディング回答を、決定論的に「結論・最小コード・検証方法」へ整理します。オフラインで動作し、コードは書き換えません。**

[English](README.md) | 日本語

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

## なぜ必要か

AIコーディングアシスタントは、学習者が必要とする以上に長い説明文を返すことがあります。長い文章を読み返す時間は学習の妨げになります。「簡潔に」という指示は事前に設定する必要があり、無視されることもあります。短い回答を求めて別ラウンドのやり取りをする必要もあります。

`concise`は、回答が生成された後に使う、決定論的でオフラインのフィルターです。スパイク023で検証済みのルールベース方式を採用しています。プログラミングコミュニティでは、RedditのスレッドやHacker Newsの項目49254381など、文章量の多さに関する議論が繰り返し見られます。

## クイックスタート

```bash
pip install -e .
echo '# Example\n\nThe standard approach is simple.\n\n```python\nprint("hello")\n```\n\nRun it and check the output.' | concise -
```

## 使い方

```bash
concise answer.md
concise - < answer.md
concise answer.md --json
concise answer.md --language ja
```

`-`で標準入力を読みます。`--json`は`input_lines`、`output_lines`、`conclusion`、`code_blocks`、`verify`を持つ安定したオブジェクトを出力します。`--language`には`auto`、`en`、`ja`を指定できます。自動判定では本文中の日本語文字を使います。

## 仕組み

エンジンはMarkdownを見出し区切りのセクションに分割し、コードフェンスは本文から分離します。その後、学習しやすい3つの構造を出力します。

| ルール | 動作 |
|---|---|
| 短い入力 | フェンス外の本文が10行未満でコードブロックが1個以下の場合はほぼそのまま出力 |
| 結論 | 結論マーカーを含む文を優先し、なければ最初の本文の文を使用 |
| コード | コードをそのまま保持し、重複を除き、通常例を反例より優先し、3ブロック・各25行に制限 |
| 検証 | 検証の見出し、マーカー文、言語に応じた既定文の順で選択 |
| 言語 | 既定は英語。本文の日本語文字が30%以上の場合は日本語の見出し |

## 制限

- Markdownは完全なパーサーではなく、標準ライブラリによる保守的なルールで解析します。
- コードフェンスはトリプルバッククォートで始まる行として認識します。内部のコードは書き換えません。
- 文と言語の判定はヒューリスティックです。言語が混在する回答には適さない場合があります。
- 反例ブロックは削除せず後回しにするため、優先される例の後に現れることがあります。

## ライセンス

MIT
