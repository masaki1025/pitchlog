# TSK-544 T1受渡し（2026-10-20）

承認済み[plan.md](plan.md)のPR-1a向け。基線は `origin/develop=7c1afebab31facc71e8cfc2731da1a9fa392de4e`（#155統合SHA `015dfa9db0b7b8740369911a9cb5195dd59a62ea` を含む）。本書は正式契約・期待値・着手条件を改訂しない。

## P-6：期待値を見ない独立検証の固定入力

[入力専用JSON](tsk544-p6-blind-inputs.json)に、正式`state_transition_contract_v1`（schemaVersion 1）の109 caseの`caseId`、規範行`rowPointer`/`rowRef`、`inputCoordinate`、`historyInput`、`raw`だけを固定した。`expected`と`normalized`は含めない。対象規範集合は`matrixRows`42行・`operationRows`10行・`undoRows`10行、case内訳は89・10・10。検証者は原典と入力から先に期待値を導出・固定し、その後に契約所有側が正式JSONの出力面と全件比較して、差異、検証者、範囲、結果を受理する。当方の自己確認を独立検証と数えない。

入力専用JSONの完全SHA-256は`9bef18e61bd45cf5c078688a2d6d6fbe0a83c1ed599fb7d2a5a5682591844435`。全109件のID一意性、規範行参照、出力フィールド不在を検査済み。

| 固定資産 | 版・完全SHA-256 | Git blob |
| --- | --- | --- |
| 要件書 | 現行変更履歴版・`d4f911db884d33455d633b8c16364ea8609df807ee3103f59697200c2b75f93b` | `ee6d2508dbdecf34d90c34fc022ff162f73dd3d2` |
| ADR-003 | v0.8・`c414c806be15ca2474ce2860dd93490f80fced2f901b7c6b60a057dd22c4c435` | `fb2b340ebf1a280207f13fe3314ba769f002ef28` |
| 状態契約 | state_transition_contract_v1・`54448fcb5b6e598e3610bc77d60a0a3ce1895f8afee8c5361a040f4aff4244bb` | `b178ff9cbed997866989eb7dc93476683f762e4a` |
| 入力descriptor | input_axes_descriptor_v1・`fab52a2e17ba868ec7f818468241901a2cb12ad98e9cf19c20b52235d184ed56` | `d971360817271f91ddc73c2e674e0c760ead7baf` |
| consumer handoff | appendix_e_consumer_handoff_v1・`d2b5aa439eef4af51d5ae0601e6f8e1d9d79e84d772706b2c0c11d2da0e6f510` | `41515de45491c8f3533e9ca0cd19e952cdd766e5` |

原典は要件書の付録E-1/E-2、FR-003/004/006/009/010/011/012/015/020/027とSO/ADV/RBI/INT等、ADR-003 D-6/D-8/D-14-m。caseの原典ID群は入力JSONの`sourceIds`にある。契約の`inputAxesDescriptor.digest`は`sha256:5107f929d35ae48e01e25e0410a95235521b778ce53bae945ca5d7e2e956dd57`。規範行の出力や`cases[].expected`を独立導出前に読まない。109件は今すぐ着手できる固定範囲であり、P-8の未収録行/caseは後続の正式版と追加入力パケットで別に検証する。109件だけでP-6全体を成立としない。

## P-7：着手前の公開契約と実装後の証跡

| 担当 | 着手前に受理が足りない公開型・署名・責任境界 | 実装後の証跡 |
| --- | --- | --- |
| U-F8/523 | 1球確定からT1への正規化入力、scope/event/prefix・規則snapshot、表示への受取型 | 実画面→HTTP→再読込 |
| U-S1/391後続 | 単一路は`apply_sync_request`、P1/P2混在は`apply_sync_events`。T1投影/検証Port注入点、イベント単位の失敗分類・transaction所有。前方確定を維持する | D5・再送・イベント単位の全取消・前方確定の隔離DB試験 |
| U-R1 | `RecordingRightsPort`の4メソッドの具体登録元とRG1/失効/不保持の失敗分類 | 実Portで閉鎖・失効・越境拒否 |
| U-X1/544 | `ProjectionPort.apply(event, writer)`と`ContentValidationPort.validate(event, writer)`へのT1入力・拒否理由・単一writerの接続型 | 実計算1回、投影/保存の全取消 |
| TSK-506 | E-1/E-2 DTO/route、単一適用核への引渡し、ACK/拒否型、認可と配線担当 | 実HTTP/DBで1球保存・再読込 |

現developの3 PortはProtocol、`PORT_IMPLEMENTATIONS`は空。「実Port未提供」は実装・マージ前の状態で、上記「公開契約・担当受理の未成立」と区別する。実Port完成・結合試験を計画外の着手前条件に加えない。HTTP側で混在バッチを分割しない。

2026-10-20の項目別回答: U-S1は`ProjectionPort.apply(event, writer)`と`ContentValidationPort.validate(event, writer)`、同一イベントwriter、既存B3a/T9・DI2・B7/P3 B10境界、配線責任を受理した。**訂正**: 混在バッチの入口は`apply_sync_events`であり、イベントごとに確定する。旧表現「単一`apply_sync_request`で混在」「バッチ全体が単一transaction」は採らない。T1正規化入力・履歴・規則snapshot・結果受渡し型は未提供。U-F8/523は観測入力の保持、scope/event/prefix・規則snapshotの受渡し、得点表示と失敗表示の責任を受理したが、製品normalizer関数・TS型・版・提供SHAは未提供。U-R1は既存Protocol/呼出位置とRG1失敗境界を回答したが、具体`RecordingRightsPort`と登録は未提供であり、terminal context不足の公開署名改訂が残る。TSK-506の現受取担当・正式回答は未確認。これらの項目別回答は**P-7全成立ではない**。各実Port・実HTTP/DB証跡は実装後に確認する。

## P-8：T1入力・規範caseの正式化待ち

| 範囲 | 不足する具体物 | 候補作成／正式受理 |
| --- | --- | --- |
| S05/S07/S32 | 閉payload、参照不能ID・重複・相反軸の負例、走者進塁上書きとRBI因果の観測入力 | TSK-544／TSK-236・538契約所有側、P-6 |
| S09/GAP-06 | 第3アウト種別・成立順・記録員判断の観測入力、OUT3-01〜05の正常/拒否case | TSK-544、必要な正本裁定はTSK-546／契約所有側、P-6 |
| S08/GAP-02 | XC-13の23成績フラグの必要十分条件・負例 | TSK-544／契約所有側、P-6 |
| G6-S01〜S11 | 指定走者・打順・回、タイブレーク再開始、履歴長/連続undo、寄与配分の規範行/case | TSK-544、原典不足はTSK-546/PO／契約所有側、P-6 |
| S20 | サヨナラの本塁打/非本塁打のT1得点上限行/case（T2終了検知とは別） | TSK-544／契約所有側、P-6 |
| S11/S13/S22 | 未決正本判断後のT1行/case | TSK-546裁定後TSK-544／契約所有側、P-6 |

#153固定候補`5a9e37bd263787106f08bb05224f01333e79ffc3`のscore観測2件、操作42件、E12相関21件は**候補資料として受領**する。同一scope/event/prefixの直前/直後得点とundo後再評価をT1共有核が供給する責任境界も受け取る。正式入力schema/descriptor、規範行/case、独立期待値、所有側受理・必要な7.7は未成立。T2 provenanceや表示5件をT1の正式P-8に数えない。

## 既存計画への紐付け

専用枝名は計画slugと異なるため、既存の`check_plan_docs_sync.py --plan docs/features/ux1-state-calc/plan.md`を用いる。現HEADで成功。既定の枝名自動導出は失敗するが、CIは現時点でこのスクリプトを直接の必須ジョブとして呼んでいない。計画を複製せず、PR検査資料へ明示コマンドを載せる。`feature_status.py`の枝名由来の表示は派生で、承認済み計画・レビュー回数の正を変更しない。実際の必須ゲートに自動導出が現れた場合だけ最小の機構差分を提示する。
