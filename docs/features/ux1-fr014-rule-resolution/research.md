# 調査: TSK-550 の切り出し根拠

- 2026-10-14、Notion のタスク DB と検索、`git worktree list`・関連 branch を照合し、FR-014 安全解決の専用タスク/実装 worktree は見当たらなかった。TSK-539 は U-X1 の計画タスク、TSK-395 は U-G1 の消費側。新規 TSK-550 を起票し、`origin/develop` `b81ae1ac` 起点の専用 worktree を作った。
- [U-X1 設計 §3](../ux1-state-calc/design.md)は FR-014 の読取関数・結付け関数・帰属列を対象計算 T1〜T6 から分離する J-3 案を明記し、TSK-539 の第 1 PR には入れない。[製品認可面 §1-6](../product-authz-surface/design.md)は `rule_sets` と `tournament_rule_assignments` を `function_only` とし、`rule_sets` の帰属列欠如を挙げる。
- [単位分割計画](../product-impl-unit-split/plan.md)の U-X1 帯 4 は凍結中。PO は今回、FR-014 の非対象計算部分だけを先行切り出す方向を裁定した。凍結記述の正式是正・製品着手承認とは別。
- [要件書](../../requirements/requirements-pitchlog-2026-07-22.md) FR-014 と付録 F は優先順位、保存時の規則検証、スナップショットの非遡及を定める。[データモデル](../../design/data-model.md) §6-5/§10-5 は全体既定と大会規則の別を定めるが、帰属列の schema と曖昧な既存行の移行は未確定。
- `backend/src/pitchlog/db/game_state/models.py` に RuleSet/GameTypeRuleDefault/TournamentRuleAssignment の ORM はある。`backend/src/pitchlog/repositories/operation_registration.py` の登録型は tenant_column を必須とする `Select|Insert|Update`、`transaction.py` は登録済み token のみ実行する。制限関数呼出しの安全な登録方法は未確定。直接 Session アクセスを安易に追加しない。
- RG1 作成側 ①〜⑤ は U-G1 の `79e3da4a` で受理済み。具体例外・競合分類・HTTP 写像・operation 登録は TSK-395 ステップ 2 接続前。D4 外部台帳は別裁定であり本タスクの条件ではない。
