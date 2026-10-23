# TSK-550 ステップ2前提・data-model保存契約の正式ゲート本文案

2026-10-14。`fa8b8da2`起点の統合候補。TSK-250所有の`docs/design/data-model.md`はこのworktreeで変更しない。現行v0.9 §6-5の既存表・優先順位・非遡及・不正値拒否の箇条を残し、次の段落だけ追加する。版・状態・変更履歴・索引は正式7.3の所有側起案で確定する。§3-2/§10-5、認可/配置、F-2値は対象外。**現行`plan.md`ステップ2は相関検査を要求するため、開始条件の最小追補がPO承認され、計画・受理シートへ反映されるまで、下記の縮小したステップ2合格条件は有効にならない。**

> **段階Aの保存形**: 段階Aで新規に規則を解決して作成する試合の`games.applied_rules`は、既存JSONBの同一top-level objectへ`ruleSetId`と`regulationInnings`、`coldConditions`、`extensionLimit`、`tiebreak`、`dh`を余分なキーなしの6-key exact-setで保存する。`ruleSetId`は同一解決結果の`rule_sets.id`を正規の小文字・ハイフン付きUUID文字列として記録する。後ろの5値は同じ規則行から得た不変スナップショットであり、`contracts/state-transition/game_end_contract_schema_v1.json#/$defs/ruleSnapshot`の既存camelCase形に従う。保存前に5値だけを既存schemaへ投影して検証し、IDはUUIDとして別途検証する。この段階のcodecは6-key形、IDの正規形、5値のschema上の型と単独値域を検証する。値間の相関と同一規則行からの出所は後続のresolverが保存前に検証し、未検証なら作成を成功させない。規則マスタの後日変更を保存済み試合へ遡及させず、規則ID専用ゲーム列や第2の規則計算実装を設けない。
>
> **旧行・不正行**: 旧`{}`、5値だけ、keyの過不足、UUIDや5値の型・単独値域違反をcodecは拒否する。codecだけで出所や値間相関を証明したとみなさず、出所不明行を段階Aの解決済みsnapshotへ推定補完しない。旧行の画面表示・復旧・一括移行はこの保存契約では確定しない。codecの受理はDB保存成功ではなく、保存前のresolverが値間相関と同一規則行由来を保証するまで作成を成功させない。

**実装との対応**: TSK-550ステップ2はこの保存形・単独値域・旧行拒否をstrict codecと単体試験へ写す。FR-014の「コールド適用回＞規定イニングは拒否」と付録F-1 `DRAW-04`の有効条件には矛盾する例（R=9、コールド開始10、L=9）があり、値間相関の正はステップ3以降の関数が保存成功を返す前に要件/正本ゲートで裁定する。ステップ2ではこの矛盾例を成功として確定しない。codecはF-2の実データやDB read、関数owner、配置migrationを必要としない。U-G1は後続の同一`tenant_transaction_scope`でresolver成功→このcodec→game INSERT（`rule_override=NULL`）→RG1コミット直前ゲート→commit/全取消を検証する。TSK-550ステップ2の合格をU-G1本番作成成功と取り違えない。

**7.3射程**: data-model v0.9全文を第1回レビュー対象、変更差分は§6-5の上記2段落と版/履歴、影響節は§10-5の既存規範と6-6のP-30照合。F-2値・意味、5つの固定UUIDと2つの機械文字列の採否、owner/ロール数、§10-5の配置・帰属は審査しない。PO採用済み固定UUIDは5件であり、本ゲートではその値を再掲・再判断しない。`schema-manifest.json`の正本digestは承認された本文の実値で追随し、凍結資産の個別7.7を別に行う。
