# 公開resolver登録の固定根拠

2026-10-24、rootが実develop31194から専用worktreeを作成し、固定f5371ee3を通常mergeした。組立3da4e441、手動競合0、正式contracts/正本差分0、再利用12pathsのみ。f537には既存e1bc3e01（固定operation）/89b57ee9（公開service）/7af797c7（DB接合）が含まれる。旧枝/commitは変更していない。

実baseのcore patternsを機械照合し、repository source/既存function test/DB test/positive fixtureの4群がtenant-isolation等で捕捉されることを確認。production history cochange predicateでe1bc6commit/89b11commit/f53715commitを走査し、違反0。cache/pitchlog/mvp-resolver-core-history-audit.jsonへ保存した。これは最終JSON基線・実PR・7.7の受理とは別である。

既存asset-delta-candidate.jsonは旧base1abに対する未受理案であり、そのrevisionや値をそのまま採用しない。実sourceはCAP:rules:resolve_stage_a、RULE:resolve_stage_aと固定public.resolve_stage_a_rule(uuid,text,text,boolean)を使い、実174のDB関数と対応する。新scopeはSELECT factory正例/実関数IDの正式登録・全生成field追随に限定する。

旧source/単体81/124/実DB155と各独立0指摘は既存operation/service/DBのresearchを参照する。未閉鎖の正式資産/7.7とS4/HTTP/RG1/createをここで達成済みにしない。新規の計画は未承認、source/契約追加編集・push/PR・DB検査をしていない。

非作者/root/resolver_ledger_plan_reviewの第1回全文計画レビュー0/0/0。固定source5filesとf537 byte一致・正式contracts/正本差分0・旧f48祖先なし・全予定core捕捉を独立照合した。rootは上記固定SHA/日時/PO委任根拠で計画を承認し、旧各レビュー系列/未受理赤を保持する。

## 承認ステップ1/2: exact SELECT/関数ID登録の接合

rootのPO委任承認commit `2b436633262afa2b918ad08464a652e8d7f74dbc`を基線にstep1だけを実装。正式7.7/history/snapshot/policy/新PRは編集していない。旧175等をmergeせず、組立済みproviderだけを利用した。製品source3files（function_operations/operation_registry/rule_resolution）、既存function_operations_boundary/DB接合試験、単一codec、stage_a_startupは承認基線byteと一致した。codec SHA256は既供給の`d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4`を保持する。

base-allowlistへ`pitchlog.repositories.rule_resolution._build_stage_a_rule_statement`、署名`_build_stage_a_rule_statement() -> Select[Any]`、SQLA_SELECTだけの1許可を追加し、同名の正例fixture1fileを作成。repository-contractのproduct_function_operation_idsへRULE:resolve_stage_aを1ID追加。既存RG1二登録・DMLの許可/登録/token/capability集合は不変。実DB関数/owner/EXECUTE権限、S3 publishable=False、4失敗/実scope/rollback/codecの計算意味を変えていない。

実差分がある2資産だけrevisionを候補更新（base34→35、repository23→24）し、repositoryの既存canonical方式（source_digest除外・sort_keys/UTF-8/空白なし）からdigestと全生成field対応を追随した。生成モジュールの変更はrevision/digest/関数IDの3項目だけ。既存snapshotで全fieldを資産と照合し、既存変異表へfunction_executor/product_function_operation_idsも加えた。実registryの3operation ID・関数identity・RULE token/capability/入力/戻り型/行数・既存DMLとの非混在を明示試験し、別DB関数/別schemaへの差替えも拒否した。

### 9資産/8外部の候補実照合

frozen_projection_contentで9資産全件の実before/afterを計算した。変更は次の2射影だけで、他7資産は完全不変。外部8対象も承認基線の実byteと全件一致した。新fixture/生成/試験差分を理由なく他資産のrevision/corpusへ広げていない。

| 資産 | before射影SHA256 | candidate after射影SHA256 |
| --- | --- | --- |
| base-allowlist.json | f532e8e1ea6d99ebfb90d5e9b67f427987cdb91623bac1b27596622e3da65ae2 | 46a7c0eb7c7d5acfd118b1d5ed4c114d62c71315aa72888f419b5d19302a2d78 |
| repository-contract.json | ca05640633b465694ea638026324f87dd24c2a177a3d6829d651d7d54bc096b6 | aa287c2b06e99d68e89aae865e066e99171e77b0804edb4b79cb9c44e41659cf |

cache-invalidation/census/db-api-inventory/frozen-inputs/negative-fixtures/runtime-authz/tenant-contextはbefore=after。実base26件（末尾#174）の履歴は全値を保持、history-snapshots192件もbase blobと全byte一致・追加削除0。policy/manifest/core JSON/guardも変更0。180実統合後のroot直列受理では実baseから全9/8・候補head/新IDを再導出する。この候補revisionや実値を次の基線へ先行受理しない。

### 今回の局所検査

- backend `test_function_operations_boundary.py`＋`test_authz_repository_contract.py`: **177 passed / 1.19秒**。既存公開resolver124件を含む。既存関数/不変DTO/4literal/失効拒否等の再利用とmetadata全fieldを接合した。初回も177成功/3.70秒だが後述lint整形前の版として区別する。
- root `test_check_tenant_boundary_bypass.py -k 'stage_a or fixed_function or positive_fixtures'`: **27 passed / 2.16秒**。新fixture/実sourceの同完全修飾SELECT許可、別module/関数名/署名/任意SQL/INSERT/UPDATE/未登録実行口拒否、既存正例/固定builderの拒否維持を確認。初版26成功後、実行API負例を1件補った。全bypass/census長時間反復は最終CIへ残し、新HEAD全件成功とは記録しない。
- 既存`test_stage_a_rule_candidates.py -k test_public_resolver_s3`: **5 passed / 26 deselected / 32.69秒**。PostgreSQL17.11（Debian17.11-1.pgdg12+2）、正式S3/publishableFalse・実app role・実engine/Session/_tenant_transaction・固定registry・公開resolverで成功/越境/override割当/不正保存rule/実EXECUTE拒否、rollback/秘匿/GUC/lock保持解放を接合した。scope/Session/認可を成功stubへ置換していない。

DBは既存disposable fixtureを使い、外側1clusterの専用admin/tested DSNを明示供給して既存verify_connection_identitiesを維持、各5件は別の内側clusterを使う。最大同時2containers・動的loopback port・専用pytest tmpを分離し、終了時containers0/自前tmp削除を確認。資格は出力しない。初回DBコマンドはbackendにxdistがないため`-n 0`を引数として拒否（exit4、収集/実行0）、外側clusterをcleanup後、当該不要引数を除いて実行した。既存fixture/試験を変えて回避していない。frontend pnpm frozen installはstage起動依存のセットアップだけで、宣言/lock変更0。

初回lintはbackend新試験の行長2件とrootのimport整形/行長4件、実行負例追記後の行長1件を検出した。backendは所有試験だけruff formatし、rootは手動改行で是正（root ruff format未使用）。最終root/backend Ruff/ty、backend生成モジュール/所有試験format --check、docs-status21件/違反0、design propagation/doc coverage/plan sync/diffが成功した。製品sourceは整形も行わずbyte不変。実履歴predicateは実31194→承認HEADで違反0/基線受理、新正例fixtureも現core globに捕捉される。

### 未受理と引渡し

正式tenant-boundary checkerは`--base-ref 31194a39...`で**exit2（履歴末尾と7資産の識別値が不一致）**。関数ID不足は登録したが、新IDの7.7行がないため履歴赤は継続する。期待値/検査器/既存historyを緩めない。PR_ACCEPTANCE、180実統合後の正式値受理、snapshot/policy/manifest、新PR公開/全必須CIはrootの後続ゲートであり未実施。

metadata/正例/試験6paths（本researchを除く）のfull-index binary差分SHA256 `f5bb83a182039511d0baa0a2d1a796d85f478d78d68c641e7f8f3f404bdad596`。生成repository_contract.py SHA256 `e71b42afd6cf1b911afb8a053b71c62945f642d7dda849a24230d6a5ea1bf3a4`、新正例SHA256 `71d58c3452020ddf738cc2ef1bfd9a7f58ad9018423849c881c917854b9bb5f8`。commit後のHEAD/全7paths/全差分SHA・実履歴predicateを引渡しへ固定する。元operation/service/DB・親TSK550のレビュー/未完履歴を保持し、実create/HTTP/RG1解除/S4/MVPを完成扱いしない。秘密/P6/他wt編集、新運用鍵、push/PRは行っていない。
