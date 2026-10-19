---
feature: us1-stop-contract-docs
status: in-review
承認: 済(2026-10-19・山田正輝 — 正本本文/採否と文書提出のみ)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3fb93b75e68781f394d5cda296211a18
branch: feature/us1-stop-contract-docs
created: 2026-10-19
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

## 1. 背景・目的

U-S1停止契約の承認対象9349f893・最終反映21ca7285を、製品候補から分離して文書だけで提出する。POが2026-10-19に本文/採否と通常push/Draft PR作成を明示許可した。正本審査3回/7件全採用/最終P0限定残存0は元featureに帰属し、本提出のカウンタへ移し替えない。

## 2. スコープ

承認済み正本、wire設計、採否/承認記録、関連feature文書と506の固定承認計画を文書1PRへ集約する。正本承認待ちは解消済み。製品挙動の変更、認可・凍結資産・DB、実Port/耐久provider、HTTP公開、各担当受理、人間逐行確認、Draft解除/マージを含めない。元feature/us1-sync-port-surfaceのコード/履歴/退避を保持し、担当/タブは増やさない。

**実装追随（7.6-3 前段・意味規則は不変）**: `scripts/design_relations/sync-protocol.json` は本PRで既に追随済みで、CI の重いフィルタは同ファイルの変更だけで frontend ジョブを起動する。承認済み v0.11 本文（既承認 O5・B7・B3a の文言）に対する**消費側同期のみ**を本PRへ含める — `frontend/src/lib/sync/processingStages.ts` と同 `processingStages.snapshot.json` の3セル文言、および `frontend/src/lib/sync/canonOracle.ts` の射程外 `O5` 行。製品挙動・公開型・新規意味を追加せず、値は承認済み本文から導出したものに限る。`lib/sync` の共有所有は維持し、新規担当/タブは増やさない。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/design/sync-protocol.md` | v0.11の承認本文/採否/履歴と先行済みO5/9-5の承認履歴を保全して統合 | 正式7.3/山田正輝2026-10-19承認済み |
| `docs/README.md` | **反映あり（対象1行のみ）**。sync-protocol 行を `0.9 / 2026-10-18` → `0.11 / 2026-10-19` へ同期。U-R1の索引先行枠は返却記録が無いため、2026-10-19の**POによる対象行限定の編集許可**に基づく。data-model行・他の索引行・正本本文は無変更 | 対象行限定のPO許可（無断編集ではない）。適用値の完全形はhandoff.md |
| `docs/design/data-model.md` | **反映なし**。U-R1先行枠を維持 | — |
| 要件書・ADR・他の正本 | **反映なし** | — |

正本体系外の同一PR対象: scripts/design_relations/sync-protocol.json（既承認O5の非凍結検査マニフェストのみ、2026-10-19のCI解消依頼に追随）、frontend/src/lib/sync/processingStages.ts・processingStages.snapshot.json・canonOracle.ts（承認本文の消費側同期のみ）、docs/features/sync-wire-schema/design.md、docs/features/us1-sync-port-surface/、docs/features/tsk506-sync-http-entry/の固定文書、docs/features/us1-stop-contract-docs/、対応docs/worklog/。認可/凍結派生は変更せず完全値と必要ゲートを別記する。

## 4. 実装方針（文書提出作業のみ）

| ステップ | 内容 | 完了条件 |
| --- | --- | --- |
| 1 | develop起点の文書限定treeへ承認本文/採否/依存受理を保全し、検査・通常push・Draft PR作成 | 製品挙動変更なし。非凍結マニフェストの追随を含む。未通過検査/索引同期/担当受理を明示し、チェックや署名を代記しない |

実装計画を新たに承認したものではなく、すでに許可された文書提出の追跡用メタデータ。製品作業は元featureで別ゲート。

## 5. DoD

正本approvedと承認記録が一致すること。最終回を全文再レビューとしないこと。製品挙動/凍結資産の差分0（非凍結の伝播マニフェストと消費側同期は承認本文に追随し、新規意味を追加しない）、索引の対象1行のみをPO許可範囲で同期、中継先/受入項目と耐久provider未提供の明示、Draftを人間判断まで維持すること。正式受理/派生資産ゲート/人間逐行確認は未完了として提示し、完了を偽装しない。

## 6. テスト計画

docs-status、設計伝播、文書カバレッジ、計画の正本宣言との突合、相対リンク、diff checkと認可/凍結依存検査を行う。索引や未受理の派生に起因するNGは完全値/原因とともにDraftへ示し、正式資産を勝手に更新しない。消費側同期は frontend の eslint / prettier / vue-tsc / depcruise / domain build / build / Vitest で確認し、新規挙動を追加しない。製品バックエンド差分0のため backend テストを合格と代記せず、既存541/98件は元候補の証拠として区別する。
