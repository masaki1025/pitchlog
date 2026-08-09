---
feature: harness-baseline-merge
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出)
承認: 済(2026-08-10・徳光 尋弥)  # codex_run.py が「済」でないと実行を拒否する
重さ分類: 軽微            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3b793b75e68781b49d01f2ff7ff26ff9
branch: feature/harness-baseline-merge
created: 2026-08-10
---

# 実装計画書: ハーネス確定ベースラインを main へ反映(設計書 6.4 例外追記)

## 1. 背景・目的

- **PO 判断(2026-08-10・会話での方針承認)**: 「ハーネス完成 = 設計書 13 章 Phase 3 完了」と定義し、プロダクト初回リリースに先立つ `develop → main` のベースラインマージを 1 回実施する。本計画書はその決定の成文化(承認欄は当該会話決定を記録)
- 現行の設計書 6.4 は「`develop → main` のマージ = リリース(/release が唯一の入口・要件書 8 章 DoD 8 項目)」と定義しており、このままマージすると自分の規約と矛盾する。**例外の明文化を先行**させる
- 機構上の効果: ci.yml が既定ブランチ main に載ることで **gitleaks 全履歴スキャン(workflow_dispatch)が GitHub Actions から起動可能**になる(github-setup.md 3 章 — 現在はローカル docker 監査で代替中)。push(main) の CI も有効化される
- Notion タスク: https://app.notion.com/p/3b793b75e68781b49d01f2ff7ff26ff9 (優先度 高)

## 2. スコープ

### やること

- 設計書 6.4 に「ハーネス確定ベースラインマージ(1 回限り・リリース非該当)」の例外を追記 + 変更履歴表に追記(**版繰り上げなし** — 7.6-3 の節更新。v1.0 の frontmatter 追加行と同じ扱い)
- develop へのマージ後(本 PR の後工程・コミットなし): `develop → main` ベースライン PR の作成 → CI 全グリーン確認 → **人間が GitHub UI でマージ**(merge commit — squash しない)
- マージ後、main で workflow_dispatch(gitleaks 全履歴)が起動可能なことを確認

### やらないこと

- リリースフロー自体の恒久変更(/release・DoD 8 項目・`vX.Y.Z` タグの体系は不変。例外は実施完了をもって失効)
- ブランチ保護の設定(プラン制約解消後の別タスク — 設計書 10.2)
- タグ付与(ベースラインの標識はマージコミットで足りる。必要になれば PO 判断で別途)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| docs/development/dev-harness-design-2026-08-07.md | 6.4 に 1 回限りのベースラインマージ例外を追記 + 変更履歴表 1.1 行追記(版繰り上げなし) | PR レビュー(7.6-3 の節更新 — アーキテクチャ・要件の改訂ではない日付入り運用例外のため) |
| docs/README.md(索引) | 反映なし(版 1.1・最終更新 2026-08-10 のまま不変) | — |

## 4. 実装方針

- **重さ分類 = 軽微**の根拠: 正本 1 ファイルの節更新+変更履歴のみ・コード変更なし。コア領域 5 領域(core-areas.json)および guard_paths に非接触
- ドキュメントは Claude の役割(設計書 3.1)のため Claude が直接編集し、fast path(6.1)の規約に従い**反対側レビュー(Codex)1 本**を通す。PR 本文には短縮計画(目的/変更/確認方法)を記載

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | 計画書(本ファイル)+ worklog の起票 | 両ファイルが worktree に存在し、frontmatter が /task-start の規約どおり |
| 2 | 設計書 6.4 例外追記 + 変更履歴 1.1 行追記 | `scripts/check_docs_status.py` green・diff が 6.4 節と変更履歴表のみ・/check 相当の検査 green |

## 5. DoD(受け入れ基準)

- [ ] 設計書 6.4 の例外追記 + 変更履歴が PR レビュー経由で develop へマージ済み
- [ ] `develop → main` ベースライン PR: CI 全グリーン + 人間マージ(github-setup.md 2 章の管理手続に従う)
- [ ] マージ後、main(既定ブランチ)で gitleaks 全履歴スキャン(workflow_dispatch)が起動可能なことを確認

## 6. テスト計画

- コード変更なしのため新規テストなし(NFR-019 の実装 PR テスト要件の対象外)。CI 4 ジョブ(secrets / docs-lint / core-guard / harness)を回帰ゲートとして利用する(特に docs-lint = check_docs_status.py + lychee)
