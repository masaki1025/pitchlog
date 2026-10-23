---
feature: mvp-rule-resolver-operation
status: active
承認: 済(2026-10-23・PO委任によるCodex判断)
重さ分類: コア領域
worktree: ../../..
notion: https://chatgpt.com/space/page_711a9b1ac7d88191a6b0bc313a60db01
branch: feature/mvp-rule-resolver-operation
created: 2026-10-23
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# TSK-550 step4の隔離実行範囲

## 1. 背景・目的

既存承認済み `feature-ux1-fr014-rule-resolution-followup/docs/features/ux1-fr014-rule-resolution/plan.md` のステップ4（固定resolver operation1件）を引き継ぐ。POの2026-10-23指示4/6/10は固定候補での独立接続・供給不足実装を許可している。主担当は実装前に `/root/o5_registration` へstep4だけの隔離実装を委任・承認した。本書は既存計画のレビュー回数・正式ゲートをリセットせず、隔離成果と未充足を追跡する。

## 2. スコープ

新module repositories/rule_resolution.py、既存operation_registry.py、test_function_operations_boundary.pyの3パスだけ。Aは#141 merge e7e8d3a4でdevelop祖先、#174固定DB関数は提供仕様として参照し製品ファイルへのコピーなし。既存#174/#173/共有正式資産は編集しない。凍結資産・7.7は候補exact前後差分をresearchへ固定し、正式反映は依存PR統合後の実値受理で行う。step5公開DTO/4失敗分類・codec適用、step6実DB/HTTPは進めない。

## 3. 影響する正本

反映なし。既承認の同一scopeと固定関数登録規則を適用する。正式契約/7.7が未反映なので本候補を正式に統合・提供済みとしない。正本外の候補資産差分は本feature/asset-delta-candidate.jsonへ分離する。

## 4. 実装方針

既存A実行器へ固定token・function identity/SQL/bind/戻り外形decoderを1件追加する。DML/RG1/tenant文脈/失効scopeを維持し、任意SQL・tenant ID・Sessionをcallerへ渡さない。decoderは外形だけで保存可能snapshotを認定しない。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 既存step4の固定operation/token/外形検査を隔離候補化 | 対象69試験、backend/root Ruff/ty成功。正式閉集合検査の未反映拒否は未達として記録。候補の独立レビュー後に保全し、正式ゲートなしにmerge/pushしない |

## 5. DoD

候補コード・固定provider・必要な正式資産の最小前後差分・検証結果を保全。正式step4の合格、7.7、実resolver提供の完成はDoDに含まない。正式版へ移す前に全閉集合/生成物/fixture/実7.7受理・全検査を一致させる。

## 6. テスト計画

backend test_function_operations_boundary.pyで実registry/scopeを通す単体・拒否試験。固定登録1件、input exact型、戻り外形、未登録/偽造/Session/失効scope等の既存検査を保持。backend Ruff format/check/tyとroot Ruff/ty。閉集合検査の不一致（exit2）は正式未反映を拒否した結果として明記し、成功へ読み替えない。
