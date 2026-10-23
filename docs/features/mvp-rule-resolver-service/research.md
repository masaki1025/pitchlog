# TSK-550 step5隔離候補の限定調査

2026-10-23、rootの委任により新worktree/branchの不存在を確認し、`feature/mvp-rule-resolver-service` を `e1bc3e014ed746681a8904cf11db50044e545233` 起点で作成した。本回は同ディレクトリのplan/researchだけを編集する。製品コード・他worktree・正式資産の変更、実装/DB適用/HTTP試験は行っていない。

## 固定した根拠

- 候補step4: `e1bc3e014ed746681a8904cf11db50044e545233`。`repositories/rule_resolution.py:25` のfrozen token、`:39` 固定SQL、`:51` 外形decoderと、`operation_registry.py` の1登録を継承する。公開入力名 `rule_override_present` は現tokenの `has_override` に対応させる。空キー拒否は既存function operationの `nonempty_inputs` による実行直前検査を保持する。
- 既存550承認計画/受理記録: #174 `e30edc79a7f90aa27cb14303910676e414c2cab6:docs/features/ux1-fr014-rule-resolution/plan.md` のstep5、および同HEAD `step1-contract-acceptance.md`「最新の採否」「固定function operationの最終契約案」。公開型・必須大会入力・4失敗とscope例外退出は既受理。旧節の未受理履歴を最新判定へ戻さない。既存計画のレビュー/承認を複製・初期化しない。
- 起点の `docs/features/mvp-rule-resolver-operation/research.md` にある候補81単体成功・独立査読と、正式閉集合不一致exit2を継承する。ここでは再試験しておらず、正式step4/7.7完了へ読み替えない。

## 単一codecの依存供給

| 固定項目 | 値 |
| --- | --- |
| 元PR/固定HEAD | #174 / `e30edc79a7f90aa27cb14303910676e414c2cab6` |
| 元・供給先の正規パス | `backend/src/pitchlog/db/game_state/rule_snapshot.py` |
| Git blob | `e30256c33d2ff2fc7a660715d7d7da3b787e153e` |
| ファイルSHA-256 | `e587a8f1e01d4d28a39f5f943b2d811b388282f782063e25fe20203a8c6c6e23` |
| 公開利用面 | `DomainValidatedRuleSnapshot` / `decode_applied_rules`。保存側の `encode_applied_rules` は後続U-G1で利用 |

起点にこのファイルは存在しない。rootは計画起案中の連絡に対し、実装時にこのblobを正規同一パスへ内容無変更で供給する方法を了承した。現在は供給しない。異なるmoduleへ複写して別の計算実装を作らず、固定依存の同一パス配置として扱う。後続の本物の#174統合後にも同じパスのhash一致を照合する。正式統合成功・凍結資産受理の証拠ではない。

同codecは `decode_applied_rules` で構造/単独値域/相関を検査するが、型docstringどおり規則行の出所は証明しない。出所・有効大会・割当拒否の保証は#174の固定SQL契約に依存する。単体の合成SQL応答で出所の実DB証明を済ませたとは扱わない。codec既存の相関未裁定拒否も維持し、resolver側で補正しない。

依存照合では起点のbackend通常依存/lockにjsonschemaがなく、codecのmodule importに必要と分かった。#174固定HEADの `backend/pyproject.toml` は通常依存 `jsonschema==4.26.0` を宣言する。この1件と対応lock解決値だけを将来の実装範囲に含め、合成のmoduleや試験専用スタブでimport成功を偽装しない。#174全体のlockや無関係な依存は持ち込まない。

rootは同1pin由来に限定した通常依存/lock同期を了承した。`--with` を製品依存成立の代用にしない。参照元#174の依存ファイル全体を以下で固定するが、全体の複写を指示する値ではない。実装後には候補側の変更範囲と実hashを改めて記録する。

| 参照元 | Git blob / SHA-256 |
| --- | --- |
| `backend/pyproject.toml` | `b71d54db4513826d76995686fae6e2556a9dbb83` / `e2048e9d69dd1fb9f494fa21cd7d06d385910a252d964bcc082c35b43651788c` |
| `backend/uv.lock` | `7b1e297fabba3f87a838b983c576936c51c12e50` / `e030363a74eb3acb6c41eda9a780d6289160d9cf0ca98c40964c53f76e0b24e0` |
| jsonschema 4.26.0 wheel | `d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce` |
| jsonschema 4.26.0 sdist | `0c26707e2efad8aa1bfc5b7ce170f3fccc2e4918ff85989ba9ffa9facb2be326` |

## sourceの選択と表現境界

`repositories/rule_resolution.py` の拡張を選ぶ。既に固定token/SQL/外形decoderが同所にあり、公開resolverはそれを呼ぶ薄い境界である。新servicesパスを増やさず、既存 `test_function_operations_boundary.py` でscope/例外退出まで照合できる。単一codecを検証済み成功型の正本とし、`AppliedRuleSnapshot` はその型aliasを公開する。リクエストだけをfrozen DTOにし、同じ規則値の二重検証を避ける。

実行器の `ImmutableValue` はMappingProxy/tuple等へ結果を閉じ、codecはexact dict/listのJSON表現を受ける。この差だけを戻すアダプタが必要。ゲーム規則のkey、値域、相関、出所をそこで判定しない。非JSON表現を拒否して、正規codecの検証結果だけを採用する。

既知4失敗は同じliteral、無効snapshotはinvalid_rule、SQL/未知結果/契約読込不能はoutcome_unconfirmedへ分類する。内部原因は公開例外へ含めない。例外をscope内でcatchして失敗値を返すとcommitしうるため、resolverは例外を外へ出し、呼出し側のwithを異常終了させる。実DBに依存しない合成Sessionの観測では、この例外退出とrollback要求までを証明する。

## 実装前レビューと留保

本計画の独立レビューは未実施。受理範囲は正本違反/ステップが緑にできない/DoDと成果物の不対応の3種とする。レビュー後のrootのPO委任判断まで製品コードを編集しない。正式閉集合/7.7、DB関数/ACL配置の成立、実DB/HTTP/保存成功、正式step5完了は後続事項である。レビュー回数や機構状態はplanだけで管理する。

## 限定計画レビュー第1回

/root/o5_final_reviewによる全文/受理記録/実行器/codec照合は否決P0=0/P1=1/P2=0。
対象plan SHA b1a4202d117f8ec1aa9977b84827da3ad648bd61439719dc5e85ad108bf1e75a、
research1eaf6e2b520733ae6dfc2f587660d386b26956f9966a4c65696c376724ff61ef。
P1はbound_transactionの実型/拒否条件が不明でduck typingなら偽scope成功を許す点。採用し、
実_TenantTransactionのexact型限定、偽scope/Session/派生型の入口拒否、失効handleの公開入口試験を追補した。
既存run_functionのstate_key/tenant文脈の実行直前検査は再実装せず保持する。修正後の差分レビュー待ち。

第2回独立差分/影響レビューは可決P0=0/P1=0/P2=0、第1回の実scope型P1解消。対象SHAはplan承認記録へ固定、rootがPO委任で隔離1ステップを承認した。レビュー済み計画の実装を開始し、旧履歴と正式ゲート留保を保持する。
