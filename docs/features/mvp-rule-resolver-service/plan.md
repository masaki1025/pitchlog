---
feature: mvp-rule-resolver-service
status: active
承認: 済（PO委任によるCodex判断・隔離1ステップのみ）
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f993b75e687810fa2b0e0b6edc228bc
branch: feature/mvp-rule-resolver-service
created: 2026-10-23
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# TSK-550 step5公開resolverの隔離候補計画

## 1. 背景・目的

[TSK-550](https://app.notion.com/p/3f993b75e687810fa2b0e0b6edc228bc)の既存承認計画 `e30edc79a7f90aa27cb14303910676e414c2cab6:docs/features/ux1-fr014-rule-resolution/plan.md` のステップ5だけを、候補step4 `e1bc3e014ed746681a8904cf11db50044e545233` に接続する隔離実行単位として起案する。FR-014・NFR-018/019と、同HEADの `step1-contract-acceptance.md` の公開型・必須大会キー・4失敗・同一scope全取消の受理を継承する。既存9ステップの番号・承認・レビュー回数・未成立ゲートをリセットしない。

rootからの今回の委任は新worktreeで本計画と調査記録を作る範囲。製品実装は未指示。本計画の独立レビューとrootのPO委任判断後に限り、下表の1ステップを実装できる。個人の逐行確認・正式7.7・公開/マージをこの委任へ含めない。

## 2. スコープ

やることは `backend/src/pitchlog/repositories/rule_resolution.py` の公開resolver、不変入力/成功型、公開例外の4失敗、既存単一codecへの接続と、既存 `backend/tests/test_function_operations_boundary.py` への単体境界試験追加。新services module・新test pathは作らない。固定依存として#174の `backend/src/pitchlog/db/game_state/rule_snapshot.py` を正規の同一パスへ内容無変更で供給する。同codecに必須の `jsonschema==4.26.0` だけを#174と同じ通常依存として `backend/pyproject.toml` に加え、`backend/uv.lock` の対応解決値を同期する。他の依存更新や#174 lock全体の取込みは行わない。出所・blob/hashは [research.md](research.md) に固定する。

実DB適用/二接続/HTTP、ゲームINSERT・大会登録・UI・RG1成功許可・RecordingRightsPort・開始/1球保存、段階Bの大会割当/試合上書き、T1〜T6、正式registry/認可/tenant-boundary/lock/seal/履歴・core登録の変更は行わない。依存codecの規則・相関・schema読込先も変更しない。既存step4の固定SQL/入力検証を緩めない。

## 3. 影響する正本

反映なし。requirements/design/ADR/development/ops・既存550計画/採否を改訂しない。候補step4の正式閉集合不一致・7.7未受理は留保する。今回の単体成功で正式step4/step5完成・#174統合・保存成功を宣言しない。後続の正式接続は実統合後の固定資産・基線・7.7を別に満たす。

`repositories/*` は現core登録の対象。codecは既存正規パスの固定依存で、既存試験ファイルへ追加する。新パスの例外追加や検査緩和が必要と判明した場合は本単位で正式資産を触らず、その具体差分をrootへ返す。

## 4. 実装方針

既存step4 moduleを拡張する。同一moduleの固定token/decoderから公開関数までを追える形にし、別services層・同内容のcodec/DTO業務検証を増やさない。詳細な固定依存と現状の根拠は [research.md](research.md)。

- 公開入口は受理済み `resolve_stage_a_rule(bound_transaction, request)`。入力はfrozen/slotsの `StageARuleRequest(game_type_key: str, tournament_key: str, rule_override_present: bool)` とし、任意tenant ID・SQL・Session・規則ID・decoderを受け取らない。既存 `StageAResolveRuleToken` の `has_override` へ明示的に対応付け、`bound_transaction.run_function` だけを一度呼ぶ。別scopeを作らない。bound_transactionは実行器の実 `_TenantTransaction` exact型に限定し、入口で `type(...) is _TenantTransaction` を検査する。duck typingや任意Protocol実装・派生型・直接Sessionを受け付けない。実handleの失効/state_key/tenant文脈再検証は既存run_functionが実行直前に担い、公開入口でも失効handleから成功を返さない。
- 成功型 `AppliedRuleSnapshot` は単一codecの `DomainValidatedRuleSnapshot` の公開型aliasとする。UUID+5値はその不変 `structural` 値から参照し、重複する検証済みDTO・相関計算を作らない。これが単独で規則行の出所証明やDB保存成功を表すことはない。固定段階A関数の出所/割当拒否契約とcodecの構造/相関検証を通った結果だけを返す。
- 公開例外 `RuleResolutionError` の `code` を受理済み4 literal `stage_a_unsupported` / `rule_not_available` / `invalid_rule` / `outcome_unconfirmed` に閉じる。SQLから返る既知4 statusは同じcodeへ写す。`resolved` だけをcodecへ渡す。無効snapshotは `invalid_rule`、codec契約読込不能・DB例外/競合・未知/不正結果・decoder違反は `outcome_unconfirmed`。内部SQL・DBメッセージ・tenant存在・原例外内容を例外本文へ含めず、例外連鎖も外へ露出させない。入力exact型・非空keyの拒否は実SQL前に維持し、成功/既定値/暗黙トリムへ変換しない。
- 実行器が不変化した `MappingProxyType` とtupleを、単一 `decode_applied_rules` が受けるdict/listへ戻す表現アダプタだけを置く。JSONスカラーを変換せず、業務key/値域/UUID/相関/付録F条件の検証はcodecへ委譲する。未対応の非JSON表現は拒否し、既定値補完・5-key/旧行修復・encode/decodeコピーはしない。U-G1保存時の単一encodeは後続へ残す。
- 失敗は戻り値で握り潰さずscopeの外まで例外退出させる。scope内で成功値や失敗DTOへ置き換えてcommitしない。単体試験でも呼出し側の `with tenant_transaction_scope(...)` の外で例外を受け、rollback/非commitを観測する。読取の隠れた自動再試行はない。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 既存550 step5の公開resolver・不変型・4失敗と単一codec接続を隔離候補化 | 固定codecを正規同一パスへ無変更供給しhash一致。既存登録済み候補scope/SQLを通す単体でUUID+5値の不変成功、既知4失敗、SQL例外/未知戻り/不正snapshotの非成功とscope全取消、空/型不正のSQL前拒否を確認。既存RG1/DML/失効/偽造拒否試験を保持。backend対象pytest/Ruff/ty、root Ruff/tyを通す。正式閉集合検査は結果を実測し未受理による拒否を留保。実装後の独立レビューへ固定差分を提出し、正式step5完成と区別して候補を保全する |

この1ステップを承認後の1委任・1コミットで実施し、先の実DB/HTTPへ進まない。計画起案コミットにはステップ記法を付けない。

## 5. DoD

公開入力/成功型・4失敗と、固定scope/SQL→外形decoder→単一codecの接続を候補としてレビュー可能にする。成功は検証済みの不変値だけ。候補なし/越境は共通 `rule_not_available`、割当/上書きは対象外拒否、未知・故障・無効snapshotは全取消へ倒し、内因を秘匿する。

依存codecの供給元・内容一致と、既存拒否境界の非緩和を記録する。対象試験に合成Sessionを使う事実、正式閉集合/7.7と実DB/HTTPの未達を明示する。正式step5/TSK-550・U-G1保存成功は本DoDに含めない。#174実統合後に正規同一パスのhash一致を再確認し、正式提供と実測は後続で判断する。

## 6. テスト計画

既存 `test_function_operations_boundary.py` に以下を追加する。新試験ファイル・独立の期待値仕様・sealed期待値には依存しない。

- 実registry/scope制御＋合成Sessionで、固定SQLへ同tenantと3入力が渡り、別scope/直接Session/任意SQLを使わない。成功結果に深いMappingProxy/tupleを含めて正規codecへ接続し、不変成功値を検査する。
- 既知4 statusを各1件以上、未知status・行列/外形不正・SQLAlchemy例外/競合・codec契約読込失敗を非成功へ分類。例外はwithの外へ伝播しrollbackし、commitしない。ログ/例外に内部SQLや機密的な原文が混入しない。
- 6-key欠損/余剰、旧 `{}`・5-key、UUID/値域/相関の不正は正規codecが拒否し `invalid_rule` になることを呼出し境界で確認。codecの業務条件や全ベクタを試験へ再実装せず、codec呼出しの有無と失敗伝播を確認する。
- 空key・None・int/bool混同・不正request型・強制変更された入力はSQL前拒否。run_functionを持つ偽scope・直接Session・派生scope型を入口で拒否し、実scope失効後も公開resolverから呼べないことを試験する。既存tokenの実行直前exact型/空キー検査、RG12登録・DML・tenant/context・失効scope・偽造token拒否の既存全試験を回帰実行する。
- backend対象pytest/Ruff format対象限定/check/ty、root Ruff/ty、正式tenant-boundary checker。既知の閉集合不一致exit2、skip/timeout/中断を成功へ数えない。実DB・二接続と実HTTP・game INSERT/RG1全取消は後続の既存550 step6/U-G1へ残す。

承認記録: 2026-10-23T13:46:57.377081+00:00、Codex主担当/root。対象plan SHA-256 1ce7c99744063eac5c9582db9a719a7798e6818daf50517939bdaa3eacdaa351、research adec833745dfcebb54f71840e93350f45822d3c81097e7a938f88300440521d3。第2回独立レビュー/root/o5_final_reviewは可決P0=0/P1=0/P2=0、第1回P1解消。PO指示4・5・6・10に基づく同一step5の隔離実装を承認する。正式閉集合・7.7・実DB・HTTPの残条件は不変。山田正輝の個別実値確認や署名とは記録しない。

## 単一codec固定依存の型是正追補

PO委任によるCodex主担当/root判断（2026-10-23T14:08:19.231202+00:00）。対象は公開resolver候補ed29e96d。
独立コードレビュー第1回はP0=0/P1=1/P2=0、単一codecがinteger値floatを公開intへ残す上流不備を採用する。
元#174 blob無変更供給という当初計画はその時点の事実として保持し、固定依存を是正版へ更新する。
別承認計画d683f25fの是正候補9bd559df（独立レビュー0、113成功）から、同じ正規パスのcodecだけをbyte一致で供給する。
元#174側への同2path是正はbc436803902a9cde2b54e6a72636acbe522e9e20、是正codec SHA256 d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4。
service側の業務検証/数値変換は追加せず、既存境界試験へ5fieldの整数値float→exactint回帰を追加する。
本1ステップの差戻し是正として、codec依存の更新・既存試験・researchだけを変更する。型保証以外の意味・schema・4失敗・scope・正式ゲートは変更しない。
次の第2回独立コード差分/影響レビューで接合を確認する。山田正輝の個別確認・署名の代記なし。
