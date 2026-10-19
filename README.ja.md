# skilltrust

**AIエージェントの信頼面を1コマンドで棚卸しします: スキル在庫・信頼設定・トークンスコープ。決定論的・オフライン・標準ライブラリのみ。スキルの中身の危険判定は一切せず、来歴と権限で判断するための事実だけを出します。**

[English](README.md) | 日本語

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![CI](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml/badge.svg)](https://github.com/sunnydachs/skilltrust/actions/workflows/ci.yml)

## なぜ必要か

エージェントスキル(Claude Codeの`SKILL.md`、OpenClaw)は、プロンプトそのものを配布するパッケージです。スキルの文章はエージェントへの指示文であり、あなたのシェル・ファイルシステム・保存済み認証情報と同じ権限を継承します。2026年の研究はこの危険を定量化しました — NVIDIA SkillSpectorの基盤研究(Liu et al.「Agent Skills in the Wild」)は42,447件を収集して31,132件を分析し、26.1%に脆弱性、5.2%に悪意らしい高深刻度パターンを確認。USENIX Security '26の論文「Do Not Mention This to the User」は98,380件中157件を「明確に悪意あり」と確認しました。SnykのToxicSkillsでは3,984件中36.8%に欠陥、うち76件が悪意あるペイロード。ClawHavocキャンペーンの監査では341件の悪意スキルが確認され、認証情報を盗むAtomic Stealerを配布していました。一次情報: [SkillSpector研究背景](https://github.com/nvidia/skillspector) ・ [USENIX Security '26](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yi) ・ [Snyk ToxicSkills](https://research.snyk.io/blog/agent-skills-threat-landscape/) ・ [ClawHavoc監査](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html)

よくあるアドバイス「使う前に全部読め」はスケールしないうえ、実は効きません。安全に読めるスキルでも攻撃になりうるからです — レビューしている文章そのものがペイロードだからです。静的スキャナも自然言語の意図に対して同じ弱点を持ちます。実効的な防御は「読むこと」ではなく**来歴と被害半径**です: 何が入っているか、どこから来たか、何を信頼されているか、どのトークンに届きうるかを知ること。

`skilltrust`はその棚卸しを1コマンドにしたものです。動作するマシンについて次を答えます:

- 有名エージェント(Claude Code、Codex、OpenClaw、Cursor、OpenCode、`.agents`規約、Hermes)にインストール済みのエージェントスキルと、実行スクリプトを同梱しているもの — 脆弱性発生率が実測で2.12倍高いマーカー
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

実行例(説明用。件数は実行するマシンの環境によって変わります):

```
AIエージェント信頼面スキャン — 2026-10-09

[スキル在庫]
  Claude Code : 12 skills (スクリプト同梱 2)
  .agents     : 12 skills (スクリプト同梱 2)
  Hermes      : 84 skills (スクリプト同梱 9)
  プロジェクト直下: 0 件 (なし)

[信頼設定]
  Trust済みプロジェクト: 1 件 (/home/you/projects/example)
  隔離(quarantine): 0 件
  Claude hooks: なし

[トークン]
  gh: 'delete_repo', 'gist', 'read:org', 'workflow'  ← workflow, delete_repo が広すぎ

[今日やる1つ]
  → narrow the gh token scope (5 min)
```

## 使い方

```bash
skilltrust scan                    # 1画面のレポート(ロケール自動)
skilltrust scan --lang en|ja|auto  # 表示言語を指定(既定はロケールから自動)
skilltrust scan --json             # 機械可読。実行間のdiff用
skilltrust scan --output FILE      # レポートをファイルに書き出す(月次diff運用)
```

人間向けレポートはロケール(`LC_ALL` / `LC_MESSAGES` / `LANG`)に従い、未設定なら英語です。`--lang` で上書きできます。`--json` は意図的に言語非依存 — `suggested_action` は常に正規の英語文字列なので、どこで実行しても月次diffが安定します。読めなかった項目はJSONでは `null` になります — diffが「確認済みの否定」と読み間違えうるゼロや `false` は決して出さず、tri-stateは `*_state` フィールドと `risk_markers.unreadable_legs` が運びます。

月1回実行して`--json`の出力を保存し、diffしてください。「先月から何が変わったか」— 増えたスキル、新しくスクリプト同梱になったスキル、trustリストの増減 — が定期の保険です。主たる契機はカレンダーではなくイベント駆動: 信頼面が変わりうる操作の直後に `skilltrust scan` を打ってください — スキルのインストール/更新(`hermes skills install`、マーケットプレイス経由、`~/.claude/skills`への手動配置)、新スキルを持ち込みうるtrust済みrepoでの `git pull`、トークンの再発行。スキャンは1秒未満・モデル呼び出しゼロなので後回しにする理由がありません。月次diffは、打ち忘れたイベントを拾うためだけに存在します。指摘があってもexit codeは0です。exit 1は環境破壊(HOME未設定など)のみです。

## 何をチェックするか

| 対象 | ソース | 備考 |
|---|---|---|
| スキル在庫 | `~/.claude/skills`、`~/.codex/skills`、`~/.openclaw/skills`、`~/.cursor/skills`、`~/.opencode/skills`、`~/.agents/skills`、`~/.hermes/skills` | 有名エージェントの個人ルート。ないルートは省略、symlinkルートは実パスで重複排除、Hermesのカテゴリ階層対応 |
| スクリプト同梱 | スキルdir配下の`*.py/sh/js/ts` | `__pycache__`は除外 |
| プロジェクトローカル | `~/projects/*/.hermes/skills`、`~/projects/*/.agents/skills` | trust済みrepoでのみロードされる。件数とプロジェクト名 |
| Hermes trustリスト | `~/.hermes/config.yaml` → `skills.trusted_project_dirs` | 最小限のstdlib yamlサブセットパーサ。block・key同インデント・flowの3綴りすべてを読む。読めなかった項目は「確認できず(not checked)」と表示され、クリーンな否定として印刷されない |
| 隔離 | `~/.hermes/skills/.hub/quarantine/` | hubスキャナがブロックしたスキル |
| Claude Code hooks | `~/.claude/settings.json` → `hooks` | hooksはセッション開始時にコードを実行する。読み取れないファイルは「確認できず」と表示され、クリーン判定は拒否される |
| GitHubトークン | `gh auth status` | `workflow`と`delete_repo`を理由付きで指摘 |

## 限界

- 棚卸しであって検出ではない。「クリーン」なレポートは信頼面が可視化されたことを意味し、全スキルが安全なことを意味しない。
- Hermesのコミュニティ由来数はファイルシステムのみからは導出できない。JSONにはフィールドがあるが、人間向け出力はスクリプト数を表示する。
- `gh auth status`の読み取りにはPATH上の`gh` CLIが必要。なければトークン欄は`unavailable`になる。

## 出自

個人向けの課題発見パイプライン(公開ソースから実ユーザーの困りごとを収集し、需要を検証し、最小の有用な成果物を出す)の最初の成果物として構築。コードを書く前に、このテーマの需要はHacker NewsとGitHub横断でGOと検証済みです。以前の「個人向け漏えいチェックリスト」テーマからの転換は、パイプライン自身の調査結果(その空間の無料静的コンテンツは飽和、一方この成果物クラス=自分のマシンの監査は静的コンテンツがコピーできない)に従ったものです。

## ライセンス

MIT
