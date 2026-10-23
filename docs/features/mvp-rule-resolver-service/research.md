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

## 隔離step5候補の実装・対象検査（2026-10-23）

rootの実装委任により承認commit `bf512445c9fa164b5452e9f1c30f5f14ea188df1` 起点で表の1ステップだけを実装した。公開 `StageARuleRequest` と `resolve_stage_a_rule`、canonical `DomainValidatedRuleSnapshot` の型alias `AppliedRuleSnapshot`、4 literalの `RuleResolutionError` を既存moduleへ追加した。実 `_TenantTransaction` exact型だけを受け、入力を生成時/SQL前に検査し、既存tokenの実行直前検査も維持する。既知失敗・DB/未知故障・不正snapshotは例外退出し、withの外で受ける試験でrollback/非commitを確認した。SQLや原例外の内因を公開traceback/ログへ残さず、自動再試行はしない。

実行器の不変JSONを正規codecへ渡す表現アダプタだけを追加し、規則の値域/相関/出所計算を複製しなかった。固定codecは元blobとのbyte比較・SHA-256一致を確認済み。今回のsource変更はresolver、固定依存codec、既存境界試験、必要依存pyproject/lockだけ。plan・他worktree・正式assetsは変更していない。

通常依存 `jsonschema==4.26.0` を `uv add --no-sync` で解決した。生成時に付随したalembic/makoのupload-timeメタデータ変動は起点の正確な内容へ戻した。TOML全package比較で、既存packageの変更はbackend自身の依存宣言のみ、新規はjsonschemaとその依存 `attrs 26.1.0` / `jsonschema-specifications 2025.9.1` / `referencing 0.37.0` / `rpds-py 2026.9.1` の5件だけと確認した。#174 lock全体は複写していない。`uv run` は通常のbackend環境を使用し、`--with` によるjsonschemaの代用なし。

| 候補版 | 検査結果と修正 |
| --- | --- |
| V1（未コミット・初回対象試験） | 対象pytestは111成功/1.33s。backend Ruff成功。tyは冗長cast1警告と、故意のfinal派生/不正引数試験の注釈3エラーでexit1。castを削除し、不正値を試験内Anyで明示。final派生の拒否試験だけtyの該当診断を局所抑制。実装の型検査は緩めていない |
| V1修正途中 | runtime型生成へ変えた試みでもtyがfinal派生を検出しexit1。明示的な派生クラスと該当1行の `ty: ignore[subclass-of-final-class]` へ変更。pytest失敗は発生していない |
| V2（独立コードレビュー提出候補） | 対象 `uv run pytest tests/test_function_operations_boundary.py -q` は117成功/0.56s/exit0。既存81＋追加36。backend対象Ruff format、全backend Ruff/ty成功。root Ruff/ty成功（既存test_core_guard docstringのRuff警告のみ）。差分空白検査成功 |
| 正式tenant checker | `python scripts/check_tenant_boundary_bypass.py --root . --base-ref bf512445` はexit2、`固定関数製品ID集合が資産と不一致`。候補step4の既知未反映拒否を維持。正式閉集合・7.7・全検査成功へ読み替えない |

最初の試験追加コマンドはbackend作業ディレクトリに対して二重backendパスを指定し、appendがファイル不存在で失敗した。その後正しい既存試験パスへ追加した。この準備エラーを試験実行成功へ数えていない。

V2の追加試験は実registry/実scope制御＋合成Sessionで、深い不変JSONからcodecへの成功、入力/成功値の不変性、既知4失敗、不正行列/未知status/非JSON表現/旧・無効snapshot、SQL/契約読込/未知故障の秘匿とrollback、空/型不正の生成時/強制変更後拒否、偽scope/直接Session/派生/失効/不正requestを検証する。既存RG1/DML等の81試験も保持した。実DB保存・出所/ACLの実測・HTTP/ゲームINSERTの全取消を証明するものではない。

| V2固定ファイル | SHA-256 |
| --- | --- |
| resolver | `a7ddbc6dd4689bad7748075af49068663da1c4b2d713b000392bc97b06b63cf8` |
| 固定codec | `e587a8f1e01d4d28a39f5f943b2d811b388282f782063e25fe20203a8c6c6e23` |
| 既存境界試験 | `ddc6e6d02e877589b458455e9d6dfb57d6d9479af734274eaf5f668fd75bfba8` |
| backend pyproject | `e2048e9d69dd1fb9f494fa21cd7d06d385910a252d964bcc082c35b43651788c` |
| backend lock | `fd4e71455bd7c8d45d2a335803cdf6023de56994b9c2bdc5a4933af5e5ce40ad` |

次はこの候補の独立コードレビュー。push/PR、正式step5完成、実DB/HTTP成功、7.7受理は未実施である。

## 初回コードレビューP1と単一codec依存の是正

独立コードレビュー第1回は候補 `ed29e96d4b5b7faa79ed34f006bbe289f05bbc09` にP0=0/P1=1/P2=0。正規codecへ無変更供給した#174由来の不備により、JSONSchemaのintegerが受理する9.0等が型注釈intの5fieldへfloatのまま残ることを指摘された。採用し、117試験成功の旧候補を正式step5完成とせず差戻した。初回の固定元blob/hashと試験結果は当時の履歴として維持する。

単一codecの型境界は専用fix計画 `d683f25f` により是正候補 `9bd559df08548380f0fe28d1e9acf4024255a9e6` で修正され、独立レビュー0指摘・既存codec試験113成功を得た。rootの最小追補承認 `7471040fc95a41b2f05fed842d498f6ebb23ec5b` に従い、同じ正規パスの是正codecだけを本候補へ供給した。元supplier #174へ適用済みの `bc436803902a9cde2b54e6a72636acbe522e9e20` ともbyte一致を確認した。本作業で元supplier・fix worktreeは変更していない。

| 是正後の固定対象 | SHA-256 |
| --- | --- |
| 単一codec（fix候補/supplier/本候補でbyte同一） | `d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4` |
| resolver source（旧候補から差分0） | `a7ddbc6dd4689bad7748075af49068663da1c4b2d713b000392bc97b06b63cf8` |
| 既存境界試験（是正回帰追加後） | `69b3b538038b83e66ced7e5d8c33f2deb5b33e11d47e07880f86eb50b2c35e9c` |

serviceに独自の整数変換/業務検証を追加していない。既存境界試験へ5整数field個別・全field同時・延長/tiebreak null保持の7ケースだけを追加した。実registry/実scope制御＋合成Sessionを経て、深い不変JSONを単一codecへ渡し、公開成功型とscope終了後の正規encode結果が同値のexact intになることを確認する。

是正候補の対象 `uv run pytest tests/test_function_operations_boundary.py -q` は **124 passed / 0.57s / exit0**（旧117＋追加7）、失敗なし。対象試験のRuff format、全backend Ruff/ty、差分空白検査は成功。変更3パスだけを固定する。codec113件の専用検証/独立レビューを再利用し、無関係な全件試験は繰り返していない。

次は第2回独立コード差分/影響レビュー。初回P1の最終採否確認、正式閉集合・7.7・実DB/HTTP・push/PR・正式step5完成は未達のまま保持する。

第2回コード差分/影響レビュー: 2026-10-23T14:14:37.957407+00:00、候補作成非関与/root/o5_final_reviewは可決P0=0/P1=0/P2=0。対象0ee701f10f29ce56d192536f70e8f50b7c56649d/base7471040f、binary full-index差分73140290cb1c63d25794eee70a7acddbea4371d7419afb2fffb629a05c192f38。codecは是正9bdとbyte一致、公開resolver本体は初回から不変、5field exactint/null/encode接合を確認、独立124 passed/0.91s。初回P1は解消し履歴を維持。後発差分は本記録だけ。正式閉集合/7.7/実DB/HTTP未達は継続。
