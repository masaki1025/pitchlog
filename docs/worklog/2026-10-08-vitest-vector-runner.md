---
date: 2026-10-08
topic: (α) ベクタ契約の Vitest 側 runner を実装する(TSK-455)
branch: feature/vitest-vector-runner
---

# 作業ログ: 2026-10-08 (α) ベクタ契約の Vitest 側 runner を実装する(TSK-455)

## やったこと

### /task-start(2026-10-08・455 タブ)

- Notion TSK-455 を 進行中 へ。ブランチ `feature/vitest-vector-runner`(起点 develop `1fdf1eec`)
- 申し送り元: 469 master(進行管理)。鎖 = TSK-455 マージ → TSK-236 PR #4 の開始条件 → ADR-003 段階 1 完了 → U-X1 解禁
- 実測: Python 側 runner `backend/src/pitchlog/domaincheck/runners/vectors.py` は develop に実在。Vitest 側 runner は実体なし
- 実測: `contracts/state-transition/` の (α) 契約 schema 群(30 ファイル超)は TSK-236 worktree のローカルにのみ存在。origin/feature/appendix-e-golden-vectors には input_axes_descriptor の 2 ファイルだけ(ローカル HEAD `d76e2cf5` が origin より 961 コミット先行)。TSK-236 の PR は #81 の 1 本(OPEN)

### 236 タブの回答(2026-10-08)と原典での裏取り

- (α) schema は凍結扱い: TSK-236 の全 110 ステップはコミット済み。`state_transition_contract_schema_v1.json` の最終変更 `1ea9b7cb`(10-07)を 236 worktree で確認。残る変動要因は人間のコア領域逐行確認による差し戻しだけ。マージ前に #81 の diff で最終形を取り直す
- PR は #81 の 1 本(draft)。#1〜#4 への分割計画はない。961 コミットは通常の push で上げる予定(force は不要)
- runner が消費する形(`appendix_e_consumer_handoff_v1.json` で確認): `caseFieldMapping` で expected が非対称(状況遷移 `/expected`、終了判定 `/decision` → `/expected`)。`tags` は契約側に無い(`availability: "absent"`)。`executionPaths[]` の vitest 経路は `runnerRevision: "pending"`・3 ID が null・`resolutionStage: "stage-2"`
- 未確定: `receiverTaskId` は null。`dependencies[]` に TSK-455 は入っていない(runner のパスが決まったら 236 へ伝える)
- **位置づけの食い違い**: TSK-236 の plan.md 1-2 節「打ち切り前に是正した 3 件」の #2 と 1-3 節は、TSK-455 を「**段階 2 の依存**」としている。カードと申し送りにある「TSK-455 マージ → PR #4 開始 → 段階 1 完了」という鎖は、計画書の現行版と合わない(PR #4 も存在しない)

### /investigate(2026-10-08)

- spec-checker・decision-tracer・Explore の 3 本を並列で実行し、`docs/features/vitest-vector-runner/research.md` に統合した。決定的な主張 6 件は原典で確認した(vectors.py:190-202 の同値投入、collect_layers.py:44、generated/ が .gitkeep のみ、domaingen に normaliz が 0 件、core-areas.json:182・229、両契約の additionalProperties と expected の有無)
- 要旨: いま作れるのは消費エンジンと読み込み層まで。実契約の全件消費は段階 2(TS の生成済み正規化と計算がない)。Python の run_vectors は ADR の条件を一部しか満たしていない(schemaVersion を読まない・最初の 1 件で止まる・経路一致が自明)

## 決定

- TSK-455 の位置づけ: 段階 1 を止めるタスクではなく、段階 2 の依存(469 master が原典 plan.md:67・:77・:276 で確認し、申し送りの鎖を撤回)。タスクは要る(ADR-003「(α) は両 runner が全件消費」)が、急ぎ度は下がる。カードのタイトル・本文にある「PR #4」の訂正は、469 master から山田さんへ上げる

- 2026-10-08 人間の裁定(U-1〜U-4。research.md 末尾にも記録):
  - U-1: **Vitest は Python `run_vectors` の現状に揃える**。schemaVersion・トップレベル検査・全件列挙といった ADR の未充足分は、両側とも段階 2 受取タスクへ送る。カードの「やること 3」(schemaVersion 不一致の fail)とずれるので、計画書で明示し、カードも直す
  - U-2: 経路一致は Python と同じ形にする(同じ実値を 2 経路に入れる。①=② が自明であることを明記する)。本物の 2 経路は段階 2
  - U-3: 共通の適合ベクタ(合成契約の正例・負例)を `tests/fixtures/` に置き、pytest と Vitest の両方に流して判定の一致を検査する
  - U-4: 証跡は `VectorRunReport` に相当する報告オブジェクトまで。JSON 証跡と収集器の拡張は、ADR:251 の「検査基盤の実装タスク」へ送る

## 未決・次の一歩

- 236 タブへ照会中: (a) (α) 契約 schema は凍ったか (b) PR 分割の有無・#81 のマージ見込み・ローカル先行分の push 予定
- schema が未凍結なら /plan まで進めて実装は待つ
