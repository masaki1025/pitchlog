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
- 機構上の効果: ci.yml が既定ブランチ main に載ることで **gitleaks 全履歴スキャン(workflow_dispatch)が GitHub Actions から起動可能**になる(github-setup.md 4 章 — 現在はローカル docker 監査で代替中)。push(main) の CI も有効化される
- Notion タスク: https://app.notion.com/p/3b793b75e68781b49d01f2ff7ff26ff9 (優先度 高)

## 2. スコープ

### やること

- 設計書 6.4 に「ハーネス確定ベースラインマージ(1 回限り・リリース非該当)」の例外を追記 + 変更履歴表に **v1.2 行**を追記し、**確定ゲート(7.3・/finalize-doc)で approved 化**する(反対側レビュー 1 周目 P1-1 を採用 — 当初の「版繰り上げなしの節更新〔7.6-3〕」方針は撤回)
- 統制: ハーネス完成アンカー = Phase 3 統合 `ce100aac97a625d6eab3559a522075b8557c041f`。ベースラインの対象は**本改訂の develop 統合マージコミット SHA 1 点**(**第一親 = アンカー**が成立条件)。**未使用失効は即時・不可逆**: main マージ完了前に第一親不一致、または `origin/develop`・ベースライン PR の head が対象 SHA から変化 → マージせず PR クローズ・Notion「取り下げ」・実測 SHA 記録(検証責任者 = PR 作成者とマージ実施者。復活不可)。対象 SHA・アンカーは**ベースライン PR 本文と Notion に記録**(実施証跡の正 — worklog 事後追記は任意の別 feature PR)。当該 PR 1 件のマージで失効し、再実施・対象変更は版繰り上げ + 確定ゲート必須
- develop へのマージ後(本 PR の後工程・コミットなし): 対象 SHA を head とする `develop → main` ベースライン PR → CI 全グリーン確認 → **人間が GitHub UI でマージ**(merge commit — squash しない)
- マージ後、main で workflow_dispatch(gitleaks 全履歴)が起動可能なことを確認

### やらないこと

- リリースフロー自体の恒久変更(/release・DoD 8 項目・`vX.Y.Z` タグの体系は不変。例外は実施完了をもって失効)
- ブランチ保護の設定(プラン制約解消後の別タスク — 設計書 10.2)
- タグ付与 — 本例外ではタグを付与しない(標識はマージコミットで足りる)。後日の `vX.Y.Z` は通常の `/release` 必須・別種の標識を設ける場合も版繰り上げ + 7.3 確定ゲート必須(**PO 判断のみでは不可** — 敵対レビュー 2 周目 P1-2)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| docs/development/dev-harness-design-2026-08-07.md | 6.4 に 1 回限りのベースラインマージ例外を追記(SHA 固定・失効条件付き)+ 変更履歴表 v1.2 行(in-review 起案 → ゲート通過で approved) | finalize-doc(7.3 確定ゲート — リリースフローの例外新設は構造的変更〔反対側レビュー 1 周目 P1-1〕) |
| docs/README.md(索引) | 設計書行を in-review(v1.2)へ現行化 → ゲート通過後に approved(v1.2)へ | PR レビュー(索引の現行化) |

## 4. 実装方針

- **重さ分類 = 軽微**の根拠: 正本 1 ファイルの節更新+変更履歴のみ・コード変更なし。コア領域 5 領域(core-areas.json)および guard_paths に非接触
- ドキュメントは Claude の役割(設計書 3.1)のため Claude が直接編集する。**fast path(6.1)は適用外**(条件「正本への影響なし」を満たさない — 反対側レビュー 1 周目 P1-1)。正本の例外新設として **7.3 の確定ゲート**(敵対レビュー → 人間承認 → approved 化)を経てから /pr する

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | 計画書(本ファイル)+ worklog の起票 | 両ファイルが worktree に存在し、frontmatter が /task-start の規約どおり |
| 2 | 設計書 6.4 例外追記 + 変更履歴追記 | `scripts/check_docs_status.py` green・diff が 6.4 節と変更履歴表のみ・/check 相当の検査 green |
| 3 | 反対側レビュー 1 周目(P1×2/P2×1)の反映 — 6.4 統制強化(SHA 固定・失効)・v1.2 起案(frontmatter/索引の in-review 化)・参照節の訂正 | `scripts/check_docs_status.py` green・diff が宣言範囲のみ |
| 4 | 確定ゲート(/finalize-doc): 敵対レビュー収束(周回ごとに指摘反映をコミット)→ PO 承認 → approved 化 + 索引現行化 | 指摘の全処理(採用/不採用一覧の提示)・PO 承認の記録・`scripts/check_docs_status.py` green |

## 5. DoD(受け入れ基準)

- [ ] 設計書 6.4 の例外追記が確定ゲート(7.3)を通過(approved v1.2)し、PR 経由で develop へマージ済み
- [ ] `develop → main` ベースライン PR(対象 = v1.2 統合マージコミット SHA・第一親 = アンカー `ce100aa`): CI 全グリーン + 人間マージ + 対象 SHA・アンカー・PR URL・main 側マージコミット SHA を **PR 本文と Notion に記録**(github-setup.md 2 章の管理手続に従う)
- [ ] マージ後、main(既定ブランチ)で gitleaks 全履歴スキャン(workflow_dispatch)が起動可能なことを確認

代替終端(未使用失効時): 6.4 の失効条件が成立した場合は、マージせず PR クローズ・Notion「取り下げ」・実測 SHA の記録をもって本タスクを終端する(上記 DoD 2〜3 は非適用。再実施は v1.3 以降の版繰り上げ + 確定ゲートの別タスク)

## 6. テスト計画

- コード変更なしのため新規テストなし(NFR-019 の実装 PR テスト要件の対象外)。CI 4 ジョブ(secrets / docs-lint / core-guard / harness)を回帰ゲートとして利用する(特に docs-lint = check_docs_status.py + lychee)
