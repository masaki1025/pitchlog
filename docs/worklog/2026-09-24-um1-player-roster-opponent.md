---
date: 2026-09-24
topic: U-M1 選手・在籍・対戦相手チーム(TSK-393)
branch: feature/um1-player-roster-opponent
---

# 作業ログ: 2026-09-24 U-M1 選手・在籍・対戦相手チーム(TSK-393)

## やったこと

- **着手**(/task-start)。`origin/develop` = `bf8ba5b` 起点で worktree を作成。TSK-393 は担当者・プロジェクトが揃っていたため起票せず、進行中への遷移とブランチ名のコメント記録のみ
- 依存 U-T1(TSK-390)が**完了**済みであることを Notion で確認

## 追記: 計画段階の調査(/investigate)

調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列委任し、
**結論に効く事実はすべて当方が原典で再実測**して [research.md](../features/um1-player-roster-opponent/research.md) へ統合した。
並行して進行管理セッションから検証済みの申し送りを受領し、**相互に原典で突き合わせた**(2 件の相互訂正が発生)。

### 判明した重大事項

1. **U-T1 の公開面は空で、U-M1 は現時点で DB に到達できない** — operation registry・製品 capability・
   越境関数 registry・`TenantContext` 製品 allowlist がすべて空(実測)。埋める所有者は **TSK-424**。
   **依存は正本上「U-T1」だけだが実効的に TSK-424 を含む**
2. **マージは TSK-344 待ち** — 12-4 ゲートの通過条件①(RLS DDL の実スキーマ適用)が未充足
   (`backend/migrations` に該当 DDL 0 件 — 実測)
3. **コア判定はカードより正本が新しい** — 機械判定でコア確定・**降格条件は消えている**。
   **TSK-394 でも同一の古い記述を確認**(葉 6 本が同型と見られる)
4. **TB004 が `change_roster_status` / `roster_status_change` を禁止**(`base-allowlist.json:196`)—
   在籍区分変更を主所有する U-M1 の自然な命名に直撃する。識別子設計に先に効く
5. **U-01 は「型」までで「中身」は葉に残されている** — ページサイズの上限・`limit` の既定値・
   カーソル書式は U-M1 が決める側。TSK-346 従属の暫定規約として記録する(U-00 の前例に倣う)

### 相互訂正(原典で裁定した)

- 当方の「U-M1 の一覧は U-01 の型に乗る」→ **不正確**。型は確定・中身は葉(`u01-dto-base/design.md:150`・`:152`)
- 進行管理側の「降格は 6.3 の確定ゲートでしか起きない」→ **撤回**。降格条件は既に消滅(`product-impl-unit-split/plan.md:313`)

### 扱わないと決めたもの

旧資料間の矛盾 3 件(`game_lineup_snapshot` の有無ほか)は、裁定 `RQ-07`(`data-model.md:2634`)が
「存在しなければ移行 0 件で終わるだけ」として処理済みのため **U-M1 では扱わない**。

## 未決・次の一歩

- **人間の判断が要る 4 件**(research.md 末尾): ① TSK-424 への実効依存をどう扱うか
  ② TSK-344 待ちのマージ条件 ③ FR-018 を切り出すか(**条文の抵触ではなく実装可能性の問題**。FR-018 は Should)
  ④ Notion カードの陳腐化(葉 6 本)への対応
- 上記の方針が決まってから /plan で計画書を起草する
