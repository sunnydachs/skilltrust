# skilltrust

**AIエージェントの信頼面を1コマンドで棚卸しします: スキル在庫・信頼設定・トークンスコープ。決定論的・オフライン・標準ライブラリのみ。スキルの中身の危険判定は一切せず、来歴と権限で判断するための事実だけを出します。**

[English](README.md) | 日本語

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![CI](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml/badge.svg)](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml)

## なぜ必要か

エージェントスキル(Claude Codeの`SKILL.md`、OpenClaw、Hermes skills)は、プロンプトそのものを配布するパッケージです。スキルの文章はエージェントへの指示文であり、あなたのシェル・ファイルシステム・保存済み認証情報と同じ権限を継承します。2026年の研究はこの危険を定量化しました — 42,447件のスキル分析(USENIX Security '26 "Do Not Mention This to the User")では26.1%に脆弱性、5.2%に明確な悪意ある挙動を確認。SnykのToxicSkillsではマーケットプレイスのスキルの36%に欠陥、76件が悪意あるペイロードでした。ClawHavocキャンペーンは1,200本超の悪意スキルをマーケットプレイスに植え付け、credential stealerを配布しました。

よくあるアドバイス「使う前に全部読め」はスケールしないうえ、実は効きません。安全に読めるスキルでも攻撃になりうるからです — レビューしている文章そのものがペイロードだからです。静的スキャナも自然言語の意図に対して同じ弱点を持ちます。実効的な防御は「読むこと」ではなく**来歴と被害半径**です: 何が入っているか、どこから来たか、何を信頼されているか、どのトークンに届きうるかを知ること。

`skilltrust`はその棚卸しを1コマンドにしたものです。動作するマシンについて次を答えます:

- インストール済みのエージェントスキル(Claude Code、共用`.agents`、Hermes)と、実行スクリプトを同梱しているもの — 脆弱性発生率が実測で2.12倍高いマーカー
- プロジェクトローカルスキルの読み込みを許した(trust済み)ディレクトリと、隔離されたスキル数
- Claude Codeのhooks(セッション開始時のコード実行)が設定されているか
- GitHubトークンのスコープ。`workflow`と`delete_repo`は広すぎとして指摘(workflowスコープのトークンはCIを書き換えて全repoのsecretsを読める)
- 今サイクルでやるべき1つのアクション

読むだけ。列挙するだけ。スキル文章の判定も、モデル呼び出しも、ネットワークも、トークン値の出力も一切しません。

## クイックスタート

```bash
pip install -e .
skilltrust scan
```

実行例(実機):

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

## 使い方

```bash
skilltrust scan                # 1画面の読み取りやすいレポート(日本語)
skilltrust scan --json         # 機械可読。実行間のdiff用
skilltrust scan --output FILE  # レポートをファイルに書き出す(月次diff運用)
```

月1回実行して`--json`の出力を保存し、diffしてください。「先月から何が変わったか」— 増えたスキル、新しくスクリプト同梱になったスキル、trustリストの増減 — それが継続運用のすべてです。指摘があってもexit codeは0です。exit 1は環境破壊(HOME未設定など)のみです。

## 何をチェックするか

| 対象 | ソース | 備考 |
|---|---|---|
| スキル在庫 | `~/.claude/skills`、`~/.agents/skills`、`~/.hermes/skills` | Hermesのカテゴリ階層対応。symlinkルートは実パスで重複排除 |
| スクリプト同梱 | スキルdir配下の`*.py/sh/js/ts` | `__pycache__`は除外 |
| プロジェクトローカル | `~/projects/*/.hermes/skills`、`~/projects/*/.agents/skills` | trust済みrepoでのみロードされる。件数とプロジェクト名 |
| Hermes trustリスト | `~/.hermes/config.yaml` → `skills.trusted_project_dirs` | 最小限のstdlib yamlサブセットパーサ。パース失敗は報告され、クラッシュしない |
| 隔離 | `~/.hermes/skills/.hub/quarantine/` | hubスキャナがブロックしたスキル |
| Claude Code hooks | `~/.claude/settings.json` → `hooks` | hooksはセッション開始時にコードを実行する |
| GitHubトークン | `gh auth status` | `workflow`と`delete_repo`を理由付きで指摘 |

## 限界

- 棚卸しであって検出ではない。「クリーン」なレポートは信頼面が可視化されたことを意味し、全スキルが安全なことを意味しない。
- Hermesのコミュニティ由来数はファイルシステムのみからは導出できない。JSONにはフィールドがあるが、人間向け出力はスクリプト数を表示する。
- `gh auth status`の読み取りにはPATH上の`gh` CLIが必要。なければトークン欄は`unavailable`になる。

## 出自

a personal problem-discovery pipelineパイプライン(公開ソースから実ユーザーの困りごとを収集し、需要を検証し、最小の有用な成果物を出す)のPhase 1として構築。このテーマの需要検証はHIGH=5 / MEDIUM=14(Hacker NewsとGitHub)、判定GO。以前の「個人向け漏えいチェックリスト」テーマからの転換は、パイプライン自身の調査結果(その空間の無料静的コンテンツは飽和、一方この成果物クラス=自分のマシンの監査は静的コンテンツがコピーできない)に従ったものです。

## ライセンス

MIT
