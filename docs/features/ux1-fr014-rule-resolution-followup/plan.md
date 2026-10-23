---
feature: ux1-fr014-rule-resolution-followup
status: active
承認: 済(2026-10-14・山田正輝・TSK-550本体計画と承認済み追補を継承)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f993b75e687810fa2b0e0b6edc228bc
branch: feature/ux1-fr014-rule-resolution-followup
created: 2026-10-22
計画レビュー周回: 4
確定ゲート周回: 3
実行方式: 通常
反映周コミット: 適用
---

# TSK-550 #174 置換ブランチの現在地参照

承認済み実装計画の正本は [本体 plan](../ux1-fr014-rule-resolution/plan.md) とその承認済み追補。#174 は #152 の置換受理単位であり、本表は `feature_status.py` のブランチ・配置対応と既承認の9ステップ番号を維持するための写しである。実装範囲、DoD、個別ゲートを変更しない。旧 #152 の plan、承認、レビュー履歴は保全する。ステップ3の未完了条件は本体 plan と [引継ぎ](../ux1-fr014-rule-resolution/step3-followup-handoff.md) を参照する。

### 実装ステップ

| 番号 | 内容 | 完了条件 |
| --- | --- | --- |
| 1 | 段階Aの実装前接続契約、既存行の出所判断、実規則データ供給と閉じた管理書込、固定登録経路、必要な正本/認可/7.7ゲートの対象・担当・順序を受理記録へ固定 | U-X1独立担当・U-G1・認可面/テナント境界担当が公開関数/型/4失敗、ID+5値、全書込入口の権限/ロック順・保持期間、同一scope、未整備時の拒否を受理。必要な正式正本承認を得て、個別資産差分の7.7受理手順を固定。**未実装の2接続/故障注入は合格条件に含めない**。未受理でもステップ1全体は未完了とし、§6-5確定後のステップ2先行を妨げない |
| 2 | `games.applied_rules` JSONB の単一strict codecと付録F検証・試験 | **着手条件: `data-model.md` §6-5の6-key保存形・旧行拒否が正式7.3で確定すること（`48e8a562`で成立）。** `ruleSetId` + 既存凍結schemaのcamelCase5値をexact-setでencode/decodeし、UUID/型/値域・round-tripを検査。旧 `{}`、5-key、不正な値を拒否する。構造検証済み値はドメイン検証済みsnapshotと型で区別し、単一の付録F-1相関検査を通した値だけを後者に昇格する。規則行の出所はcodecだけで証明せず、後続resolverが保存前に確認する。未検証・矛盾例は保存成功へ進めない。帰属列migration、仮の既定値、保存成功の擬装を加えない |
| 3 | 段階Aの制限読取関数とowner/ACLの既存認可適用器への追加、付録F-2データ配置Alembic、実DBの権限・越境・故障試験 | **正式資産への反映前に**§10-5の出所/割当拒否と相関規則の矛盾、関数owner・RLS・EXECUTE・tenant GUC、配置migrationの出所/衝突/一時RLS/排他/downgrade、認可・移行資産の個別ゲートを確定する。候補実装と隔離試験は承認済み追補の範囲で先行できる。`pitchlog_app` は `rule_sets` と `tournament_rule_assignments` の直接SELECT/書込を拒否し、`game_type_rule_defaults` は既存 `global_read_only` のSELECTを保持して書込だけ拒否する。関数は自テナントの大会割当があれば全体既定へフォールバックせず拒否。親行`FOR UPDATE`後の別SQL割当読取、既定→規則`FOR SHARE`とscope終了までの保持を検証。S0〜S4の各段階を照合し、失敗/結果不明時は作成を非公開にする。データ配置は個別の正式ゲート後にF-2値/出所と既存行衝突拒否を試験し、認可適用器・manifest/凍結資産と必要な7.7受理・基線試験を通す。データ配置が未承認/未着地なら成功を作らず、ステップ3を完了扱いしない |
| 4 | Aで先行統合した共有実行器へ段階A resolverの固定function operationを**1件だけ**登録し、契約試験を行う。必要なrepository-contract改訂は個別受理後 | A統合済み基線とBの正本・認可・凍結資産ゲートを確認。tenant-bound scope以外から呼べず、関数ID・引数/戻り型を固定し、未登録・偽造token・任意SQL・直接Sessionを拒否。既存DML operationの不変条件/bypass検査を維持。U-R1 CのRG1専用2件はBの登録順を待たない |
| 5 | 登録済みscope経由の段階A公開resolver・不変DTO・失敗分類と単体試験 | 安全な全体既定だけを解決して規則ID+5値を返し、大会割当/試合上書きは拒否。候補なし、越境、無効規則、読取失敗とDB競合を受理済み結果へ分類。直接Session、仮規則、T1〜T6複製なし。U-G1へ同一scope保存契約を引き渡す |
| 6 | 実関数・登録済みscopeを通る隔離PostgreSQL二接続/故障注入試験 | 実装済みの全管理書込入口との両順序、ロック保持/rollback、別テナント、故障・競合を実測。未実装入口は未検証と明記し有効化しない。**U-G1の実HTTP・RG1・game INSERTとsnapshotの全取消/非遡及はTSK-395ステップ2**で実測する |
| 7 | `backend/tests/test_rule_resolution.py` の `AREA_PATH_ADDITIONS` 宣言と guard 試験 | tenant-isolation・game-state で新規試験パスが検出される。既存3パスは JSON 基線に残し、`tenant-isolation` 宣言は新規パスだけへ差し替える。`validate_area_path_layers` の一部 overlap 拒否を再現し、差し替え後に通過することを試験で確認 |
| 8 | `.claude/core-areas.json` 登録 | ステップ 7 とは別コミット。head 側の core-guard が全対象を検出し、未記入の人間逐行確認を拒否 |
| 9 | 最終の正本追随・検査・申し送り | pytest/ruff/ty、DB/認可/基線/guard 検査を通し、TSK-395 へ公開契約と実経路試験条件を引き渡す。**PR 作成後**の敵対レビューと人間逐行確認は本ステップの完了条件に含めず、PR マージ前ゲートで記録する |

## 影響する正本（本体の既承認範囲の参照追随）

現在地用の写しにも本体§3と同じ既承認対象を機械可読で明示する。範囲/DoD/9ステップ・旧承認・レビュー回数は変更しない。

| 正本 | 本PRでの既承認反映 |
| --- | --- |
| [要件書](../../requirements/requirements-pitchlog-2026-07-22.md) | FR-014/DRAW-03/04と既受理の版整合。本体計画と旧確定記録が正 |
| [データモデル](../../design/data-model.md) | 6-key snapshot/規則出所/専用owner/ロック・最小権限。既承認v1.1の本文/履歴を保持 |
| [規則解決認可面](../../design/product-authz-surface.md) | 受理済み段階Aの認可/残余脅威。本体計画の個別ゲートを保持 |
| [配備前提](../../ops/deployment.md) | 非公開S0〜S3段階起動の追随。共有DB適用/S4公開の許可ではない |
| [索引](../../README.md) | 上記版・参照と正式developのMVP委任実施注記を両方保持 |

PO委任によるCodex判断: 写しにこの節がなかったため計画同期がexit1となった。元の本体§3と同じ対象の参照追随だけを行い、検査を緩めない。
