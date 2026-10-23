# TSK-550 ステップ4の隔離候補

主担当 `/root` のPO委任判断による2026-10-23の実装指示で、既存承認済み `ux1-fr014-rule-resolution/plan.md` のステップ4だけを実施した候補。新計画として既存レビュー回数をリセットせず、既存9ステップの番号も変更しない。新worktreeはorigin/develop `1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`起点。既存#174・U-R1のworktreeは変更していない。

## 固定した提供物と新実装

共有実行器Aは#141で統合済み。GitHubのmergeは `e7e8d3a4324687ada828b1e4b49692c087af5c44`、2026-10-15T21:01:27Zで、このmergeがorigin/developの祖先であることを確認した。既存の `FunctionOperationRegistration` とtenant-bound `run_function` を再利用し、Session・SQL・tenant IDをcallerに開かない。

#174 `e30edc79a7f90aa27cb14303910676e414c2cab6` のDB関数SQLは未統合の固定供給候補である。blob `13de1e4a576d70df2220040f1e61ad7993b0ef18`、SHA-256 `f5bbd863d072b95931efc73ea0da984bb4723df0e900e2dca745aa6e4dd71af8`。このSQLを新worktreeの製品へ複写していない。4引数 `public.resolve_stage_a_rule(uuid,text,text,boolean)`、jsonb戻り、scope注入UUIDと公開3入力の契約だけを固定し、新規のtoken・固定登録・decoderを実装した。DB関数の存在やACL適用、#174の正式統合を本候補の成功で代替しない。

新実装は `repositories/rule_resolution.py` のfrozen token、固定Select、DB戻り外形decoderと、既存registryへの1件追加。既存DMLとRG1の2登録は維持する。operation IDは `RULE:resolve_stage_a`、capabilityは `CAP:rules:resolve_stage_a`。内部の実装識別子であり、新しいHTTPや利用者権限を公開していない。

decoderは、Aが不変化した単一オブジェクトについて、`resolved`ならstatus/ruleのexact-setとruleの不変オブジェクト型、失敗なら既存SQLの4 statusだけを検査する。規則候補を保存可能なsnapshotへ昇格しない。6-key/値域/相関・出所を確認する単一codecの呼出し、公開DTO・4失敗の公開分類・rollbackへの接続はステップ5に残る。契約未整備の成功型を供給済みとは扱わない。

## 正式資産の不足と最小差分

[候補差分](asset-delta-candidate.json)に固定したbefore/afterは、関数operation ID集合の末尾1件、生成Pythonの対応定数、固定Select builderの限定SQLA_SELECT許可だけ。DB関数・専用owner・app EXECUTEは#174が提供するため、この登録だけで新しいDB ACLを加える必要はない。既存scope・GUC・資格情報隔離・直SQL拒否を維持する。

正式 `repository-contract.json` はRG1の2IDで閉じているため、実checkerは `固定関数製品ID集合が資産と不一致`、exit 2で拒否した。正式資産・生成契約・履歴は変更していない。新builderの固定factory許可とpositive fixtureも正式登録が必要である。checkerを回避する許可追加・検査変更は行わない。

共有資産は#174→#173の実履歴を保って直列化する。実統合後の基線からrevision・digest・snapshot・7.7完全前後値を再導出し、独立レビューとPO委任による受理を経て初めて正式反映する。本候補のfield差分やraw hashを完全な7.7受理値と称しない。HTTP/DB試験成功を契約候補整備の新たな着手前条件にはしない。

## 検査と提供境界

- `uv run --with pytest-xdist==3.8.0 pytest -n 2 tests/test_function_operations_boundary.py -q`: 69成功。backendの既存pytestに、rootで固定済みのxdist 3.8.0を実行時だけ追加し、依存宣言・lockは変更していない。
- backend Ruff/ty成功、対象3ファイルのRuff format適用。初回はSQLAlchemyのString bind表示に不要なVARCHAR castを期待した試験1件が失敗し、実固定SQL表現に合わせて修正後69件成功。
- 試験は実registry/token・実scope制御へ合成Sessionを接続し、tenant注入・入力型・未知戻り・失効scope・decoder異常のrollbackを確認した単体境界試験。実API／実DB保存の証拠ではない。
- 正式checkerは上記の未受理ID閉集合で拒否。全件green、ステップ4完了、正式提供、push、PR、DB適用は未実施。新resolverの公開・規則snapshot検証はステップ5へ進んでいない。

## 限定独立レビュー

`/root/product_connection`（候補作者/root/o5_registrationおよび主担当から独立）が3sourceを全文照合し可決P0=0/P1=0/P2=0。69対象試験を独立再実行して69 passed/2.05s/exit0。既存正式checkerのexit2は未解消で、正式受理/統合/step4完成ではない。

固定SHA256: module `5cd834679a64500f08abdb8dece0a9909d1d497f98a4f36ae5c9e1563f126590`、registry `7e2d72f8d28dfef7498d78ed41ec65dc04025cdee3ff9b022ed82c26be95a945`、test `7868a53933c04441f0e08cfccba913f994ad8aea8d3c5692bd15730c389120d4`。review diffSHA `6aaab4f6c3eda3aa0417f2146db1582517698c9fcd7efb4b0a80475b6ac9313c`（3パスをmodule/registry/test順でbinary/full-index差分連結、未追跡moduleだけno-index /dev/null比較）。レビュー後は本記録だけを追記し、製品差分は不変。

## 空キー拒否の限定是正候補

受理済みstep1契約に対し、候補b4b8aaf2は空keyをprepareへ渡していた。追補計画94ad459aのPO委任承認後、登録型へ既定空tupleのnonempty_inputsを追加し、登録時にexact tuple/str名/重複/宣言済みstr入力だけを許可する。resolverの2keyだけを指定し、実行直前に検証した同じ値をbindへ入れる。RG1は既定空tupleのまま、全strの一律制約・トリム・独自SQL・権限緩和なし。正式資産の変更はなく、既記録の閉集合不一致exit2は残る。

backend Ruff format/check/ty成功、対象test_function_operations_boundary.pyは81 passed/0.65s。従前69件へ12件を追加し、構築時/強制変更後の各2key拒否を実scope・合成Sessionで確認。SQL実行に到達しないrollback、未指定strの空文字・指定strの空白保持、誤登録を検査した。実DB/HTTP試験ではなく、正式step4/7.7完了ではない。root Ruff/tyも成功。次に固定候補の独立レビューを実施する。

是正候補bffa1f963ef702f43b0140e7f4101023eb25655aは/root/o5_final_reviewが候補作成に関与せず独立レビュー可決P0=0/P1=0/P2=0。base94ad459adce1b6cb68bb3909bbf4fa0ddb018542、binary差分SHA256 ca61a58ca6f490c3c8d8a61a5aa5ae9b8e784d961f9f6b16adb61bd3731340b8を照合、独立再実行81 passed/0.83s。後発差分は本記録のみ。従前レビュー履歴と正式未受理の留保を維持する。
