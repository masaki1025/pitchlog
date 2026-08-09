---
date: 2026-08-10
topic: ハーネス確定ベースラインを main へ反映(設計書 6.4 例外追記)
branch: feature/harness-baseline-merge
---

# 作業ログ: 2026-08-10 ハーネス確定ベースラインを main へ反映

## やったこと

- /task-start: Notion タスク起票(優先度 高・DoD 3 点)→ `feature/harness-baseline-merge` ブランチ + worktree 作成(origin/develop 起点)→ 計画書・本 worklog 作成
- ステップ 1〜2 をコミット(計画書・worklog 起票 → 設計書 6.4 例外追記)。check_docs_status.py green・diff は宣言範囲のみ
- 反対側レビュー 1 周目(review normal・terra max): **P0×0 / P1×2 / P2×1 — 判定「要修正」**。全件採用して反映(ステップ 3)
- /finalize-doc 開始。確定ゲート敵対レビュー 1 周目(review adversarial・sol xhigh): **否決 — P0×0 / P1×3**(アンカー欠落〔Phase 3 後・v1.2 統合前の develop 更新が対象に混入し得る〕/「改めて PO 判断」がゲート外の再発行経路/対象 SHA の worklog 記録が実行不能〔記録コミット自体が develop を進めて条件を自壊〕)。全件採用して 6.4 の統制を改稿
- 敵対レビュー 2 周目: **否決 — P0×0 / P1×2**(1 周目反映 3 件は「正しく反映済み」と検証 — アンカー実在・merge-base・索引整合まで実機確認)。新規指摘 = 統合後〜main マージ前の未使用失効が未定義(復活余地)/計画書のタグ文言が PO 単独経路。全件採用して反映
- 敵対レビュー 3 周目: **否決 — P0×0 / P1×2 / P2×2**(2 周目反映は解消済みと確認)。新規 = 未使用失効後の終端が /task-done と矛盾(「取り下げ」が「完了」へ上書きされる)/ main・PR base が失効条件から漏れ。P2 = 次の一歩・失効要約の旧文言。全件採用して反映

## 決定

- **PO 判断(2026-08-10)**: 「ハーネス完成 = 設計書 13 章 Phase 3 完了」と定義。プロダクト初回リリースに先立ち `develop → main` のベースラインマージを 1 回実施する(**リリース非該当** — /release・DoD 8 項目・vX.Y.Z タグは適用外。実施完了または未使用失効条件の成立をもって例外は失効)
- 実施順: 6.4 の例外追記が develop へマージされてから main への PR を作る(規約と矛盾した状態でマージしない)
- 当初の「版繰り上げなしの 1.1 追記(7.6-3 の節更新)」方針は**撤回**(反対側レビュー P1-1 採用): fast path は「正本への影響なし」(6.1)が条件で不適用・v1.0 の frontmatter 追加行は「本文の内容変更なし」のため先例にならない → **v1.2 への版繰り上げ + 確定ゲート(7.3・/finalize-doc)** へ切替(frontmatter・索引を in-review 化)
- **対象 SHA の固定と失効**(反対側レビュー P1-2 + 敵対レビュー 1〜2 周目採用): ハーネス完成アンカー = Phase 3 統合 `ce100aac97a625d6eab3559a522075b8557c041f`。対象は v1.2 統合マージコミット 1 点で**第一親 = アンカー**が成立条件。**未使用失効は即時・不可逆**(main マージ前の第一親不一致 or `origin/develop`・PR head の変化 → マージ禁止・PR クローズ・Notion「取り下げ」・実測 SHA 記録。検証責任者 = PR 作成者とマージ実施者・復活不可)。当該 PR 1 件のマージで失効し、再実施・対象変更は **v1.3 以降の版繰り上げ + 7.3 確定ゲート必須**(PO 判断のみでは不可)。**タグは付与しない**(後日の vX.Y.Z は /release のみ・別種標識も版繰り上げ+確定ゲート必須)。実施証跡の正は**ベースライン PR 本文 + Notion**(worklog への事後追記は任意の別 feature PR — 記録コミットが develop を進めて条件を自壊させないため)
- **main 側の固定と終端手続**(敵対レビュー 3 周目 P1×2 採用): main 側アンカー = `f06e2f2dd7fd19e05ad828115bbe6b7fd603f7ba` を固定し、`origin/main`・PR base の変化も即時・不可逆の未使用失効条件に追加(マージ直前に head/base を再照合・使用済み証跡でマージコミットの両親 = main 側アンカー・対象 SHA を検証)。未使用失効の終端 = Notion「取り下げ」維持(「完了」へ上書きしない・/task-done の Notion 遷移なし)+ worktree 除去は Git 手順準拠
- 機構上の狙い: ci.yml が既定ブランチ main に載ることで gitleaks 全履歴スキャン(workflow_dispatch)が Actions から起動可能になる(現在はローカル docker 監査で代替中 — github-setup.md 4 章〔参照節の訂正 = レビュー P2〕)

## 未決・次の一歩

- 確定ゲートの収束確認(実質的な新規指摘が出なくなるまで敵対レビューを繰り返す)→ PO 承認(採用/不採用一覧の提示)→ approved 化 → /pr
- develop マージ後: v1.2 統合マージコミットの**第一親 = develop 側アンカー**を確認 → その SHA を head、main 側アンカーを base とする `develop → main` ベースライン PR(本文に対象 SHA・両アンカーを記録)→ CI 確認 → **マージ直前に develop/main・PR の head/base の不変を再照合**(逸脱していれば未使用失効処理: PR クローズ・Notion「取り下げ」維持・実測 SHA 記録・worktree 除去は Git 手順準拠)→ 人間マージ → main 側マージコミット SHA(両親 = main 側アンカー・対象 SHA を検証)を PR 本文・Notion に記録 → workflow_dispatch 起動確認 → /task-done
