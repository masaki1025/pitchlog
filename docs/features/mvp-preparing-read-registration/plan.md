---
feature: mvp-preparing-read-registration
status: active
承認: 済（PO委任によるCodex判断・隔離read登録候補）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-preparing-read-registration
created: 2026-10-24
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 準備中readの正式登録に向けたmetadata候補

## 1. 背景・今回の到達点

主担当の指示により実develop固定`31194a39c9083bbef6c14bde19c24a3e49d09f2e`から隔離branchを作成した。
API `270347f0658a9c233ce788ad11424b652e564a1c`（実装source `b3a8ef8bb7f1200c423fc32ec803300a0f1724ee`）、
UI `9e5c59c3b57012547b3e32932bf8d850cb63eee5`、browser `4977c1b640713b4907ebdad7c99a62f18dd982e3`を
この順で履歴付きmergeした。組立HEADは`f5bda183300846ba2d457cfa9c9eb92cdeffdd7e`。
3件とも自動mergeで、手動競合編集0。指定baseの正式contracts/正本差分0、既存core paths/順序/guard_pathsを保持した。

今回は本plan/researchの起案だけであり、新たな正式JSON・正本・製品source・fixture・生成値を編集しない。
既存3候補の独立レビュー結果は保持するが、この接合や本計画を正式7.7受理へ読み替えない。
旧#175/d68・他worktreeは編集せず、旧#173 initialコード・未受理props・正式期待値/P6封印へ実装を拡張しない。
旧173文書/値は参照だけに留め、旧受理行や値をこの枝へ移植しない。

本計画の実装単位は、2SELECT/2token/2GETの**未受理metadata候補と必要な試験**だけである。
準備中試合の保存値だけを読むGET /gamesおよびGET /games/{game_id}を既存CAP:games:readへ対応させる。
新create/resolver/RG1、開始/記録入力、新capability・DB権限・migration・RLSは追加しない。

## 2. 依存の扱いと開始条件

依存単位名は**実173単位または旧履歴の保全を保持した正常履歴の置換PR**とする。
旧173のf48履歴問題を継承するHEADは供給として用いない。隔離準備へmergeできるのは、
主担当/rootが後で通知する**新しい正常置換候補HEADだけ**であり、現時点では未供給である。
旧173の`0aaa`/`8037`等を組立f5へmergeすると違反が伝播するため禁止する。旧文書/値の参照はmerge許可ではない。

- 計画承認と主担当の個別ステップ指示後に実装する。正常置換の実統合を候補実装開始の一律条件にしない。
- 新しい正常置換候補HEADの固定後は、独立計画レビュー/PO委任承認と個別指示に基づき隔離mergeしてmetadata候補を実装できる。旧initialや未受理枝から一部実装/値を移植しない。提供前でも承認後は既存の固定3候補だけから独立して準備できる2factory/fixture/登録対応を進め、未回答を全体停止の理由にしない。
- 正常置換候補との接合では既受理の全source/登録/fieldを保持し、readの差分だけを追加する。意味変更を要する衝突は機械解消に混ぜず具体差分を主担当へ返す。
- **正式受理ゲート**は別である。正常置換PRの実統合後の実baseを取り込み、完全before/after・revision・全生成対応・履歴/snapshot・最終lock/sealを一つの実状態から再導出し、主担当/rootが唯一writerとして直列受理する。古い候補値を正式値へ流用しない。
- 親#175の正式追加敵対1回は、上記実base/正式接続候補HEAD/diff固定後まで未消費。本計画/候補レビューで消費・回数リセットしない。

## 3. スコープと影響する正本

**正本の反映なし**。要件/design/ADR/development/ops、旧featureのplan/review履歴は変更しない。
以下の実ファイルを後続ステップの候補編集対象とする。正式パスに候補差分を作っても、共有受理値や提供済みへの昇格ではない。

| パス | 限定する候補差分 |
| --- | --- |
| `contracts/tenant_boundary/base-allowlist.json` | `allowed_symbols`へSQLA_SELECTだけの完全修飾2factory/正確signature/正例fixtureを対応付ける。既存symbolの変更・削除・module全体許可なし。正式7.7履歴は追記しない |
| `contracts/tenant_boundary/repository-contract.json` | `product_operation_token_types`へ通常2型を追加。既存全field/登録順を保持し、正常置換候補で追加されるfactory binding等も全field対応に含める。件数/旧revisionを固定しない |
| `backend/src/pitchlog/repositories/repository_contract.py` | 上記JSONの生成対象全fieldを対応付けて決定的に導出。source digest/tupleだけの部分更新と先決めしない |
| `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/games.py` | list factoryの正確symbol/signatureとSELECT限定正例 |
| `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/games/__init__.py` | detail factoryの正確symbol/signatureとSELECT限定正例。同名moduleへ解決する既存fixture方式を使う |
| `contracts/authz/route-registry.json` | `ROUTE:RECORD:games:read`、record_and_aggregate/design/readの1行と本計画を指す正確provenance。必要なclaim対応は実入力と照合し、要件主張や既存dispositionを架空追加しない |
| `contracts/authz/http-route-matrix.json` | 同routeに`HTTP:ROUTE:RECORD:games:read`/conditional/test_ownerを対応。新3軸cell/resource_kindは追加しない |
| `scripts/check_authz_catalog.py` | `_validate_record_and_aggregate_route_ids`の期待集合へ本計画の`ROUTE:RECORD:games:read`1件だけを追加。既存7経路・不足/未登録/重複/provenance/lock拒否と他の検査を維持し、包括的許可に変えない |
| `backend/tests/test_authz_repository_contract.py` | JSON↔生成全field、既存+read2型/既存CAP・実registryのexact集合と対応を検査。旧登録実在/順序/拒否を保持 |
| `tests/test_check_tenant_boundary_bypass.py` | 正例exact-set、SELECT許可と全拒否変異、署名/別module/別factory/SQL API逸脱の拒否を追加 |
| `tests/test_check_authz_catalog.py` | route/matrix exact-set、provenance/test_ownerと候補差分の正負例。既存closed-set/lock検査を緩めない |
| `backend/tests/test_game_preparing_read_boundary.py` / `backend/tests/test_api_app.py` | formal route行とGET2/operation ID2/C2クラスの対応を入口ごとに確認。matrixの1行だけで2GETを実証したことにしない |
| 本featureの`plan.md` / `research.md` | 入力SHA・候補差分・検証/未達・受渡し記録 |

次の既存製品sourceは入力として照合し、登録不足のために迂回実装/変更しない：
`backend/src/pitchlog/repositories/games.py`、`operation_registry.py`、`api/routers/games.py`、`api/tenant_access.py`、
単一`db/game_state/rule_snapshot.py`、UI/provider/browserの固定source。
実registryには通常read2件、C2にはoperation ID2件が既にある。重複登録を作らない。

新規正例2パスは既存`tests/fixtures/tenant_boundary/*`、他の全編集予定パスも現core patterns/guard_pathsで検知される。
予定外の新test/script/candidate実行資産は作らないため、core先行登録の新単位は不要。
既存core/json/検査器の拒否範囲を縮小しない。追加pathが必要になればその差分を先に分離する。

## 4. 登録する閉集合と検証境界

| 入力source | 対応先・守る条件 |
| --- | --- |
| `_preparing_game_list_statement(cursor_position: tuple[datetime, UUID] \| None=None) -> Select[Any]` | 完全修飾`pitchlog.repositories.games`の同factoryだけにSQLA_SELECTを許可。signatureは既存checkerのAST正規化値を正とする |
| `_preparing_game_detail_statement() -> Select[Any]` | 同moduleの同factoryだけ。別関数/別module/偽signature/text/update/任意SQLを拒否 |
| `PreparingGameListToken` / `PreparingGameDetailToken` | 完全修飾名と通常OperationRegistrationのCAP:games:read・正本Game表・注入tenant bind・固定preparing/可視性・bounded keysetを突合する。tokenに任意tenantを足さない |
| `preparing_game_list` / `preparing_game_detail` | GET /games・GET /games/{game_id}、TenantMatchedRoute、認証/C2先行とno-storeを対応付ける。POST/OPTIONS/開始を登録しない |
| 保存snapshot/DTO/Page | 既存単一codec/保存値検証を再利用。6-key形だけの出所認定、live resolverからの再計算、別codecを作らない |

allowlistはDB呼出し境界の許可であり、それだけでSQL tenant条件や実認可を証明しない。
既存登録時/実行時の連続検査、不可視/他tenant/不在、旧snapshot拒否の実試験も維持する。
origin=designのrouteは本計画の上記read対象文をprovenanceへ正確に対応付ける候補であり、新たな要件意味を作らない。
test_ownerをimplementedにする場合は実収集node IDが必要。planned ownerや候補署名で実装済み認定しない。

## 5. 派生生成と正式受理の分担

repository専用の常設generator CLIは現基線にはない。別資産用の`pitchlog.authz.runtime_contract_generator`で
`repository_contract.py`を生成したとは扱わない。標準json/hashlib/astによる決定的な導出手順を実装時に記録し、
`test_generated_repository_contract_matches_asset`が比較する**全生成field**を正とする。
`source_digest`の導出は既存`_asset_digest`のcanonicalizationに従い、入力JSONと実moduleの全field/署名/exact集合の一致を確認する。
正常置換候補のfieldが増えていれば、そのfieldも生成/比較から落とさない。新しい常設generator/script pathをこの単位で追加しない。

rootが正式ゲートで扱う派生/受理対象は以下である。本候補ステップでは正式履歴・snapshot・最終lock/sealを追記しない。

| rootの後続対象 | 入力/既存生成・検査手順 |
| --- | --- |
| `contracts/tenant_boundary/{base-allowlist,repository-contract}.json`のbaseline_control/history、`contracts/tenant_boundary/history-snapshots/*` | 正常置換PRの実統合後のbaseと候補を唯一の比較対として`uv run --directory backend python -m pitchlog.authz.runtime_contract_acceptance --base <実base> --acceptance-id masaki1025/pitchlog#175 --approved-by <実承認者> --approved-on <実承認日> --reason <理由> --movement-fact <事実> --output <repo外bundle>`。実承認前に値を代記しない |
| `contracts/authz/{route-registry,http-route-matrix}.lock.json`、必要なら同時導出される`auth-catalog.lock.json` | 既存`uv run python scripts/check_authz_catalog.py --asset-spec product --reseal-derived`。3派生lockが対象であるため、read以外のauth-catalog差分を黙って取り込まない。入力manifest/claimsの既存SHAも実baseで照合する |
| root後続のoracle6資産と`contracts/authz/oracle-seal.lock.json` | 下記の8入力commit固定と6context/sealの同時前進、必要差分のレビュー/受理を経てから`uv run python scripts/check_authz_catalog.py --asset-spec product --reseal-oracle`。最後は更新flagなしで全件検査。再封印だけでoracle_commitは進まない |
| `contracts/authz/{requirement-claims,requirement-claims.lock,auth-catalog}.json`等の入力 | 原則不変。実統合された正常置換の入力を保持し、read行追加で必要なmanifest/digest射影だけを根拠付きで再照合する。新要件主張/DB権限/3軸規則へ広がる不足は別scopeへ返す |

### root後続のoracle確定手順

以下は正常置換PRの実統合後にrootが直列に行うゲートであり、本候補の編集scopeへoracle6資産を追加しない。
候補metadataの実装開始をこの正式受理待ちへ戻す条件でもない。

1. route/matrixの変更と派生lockを含む更新済み**8入力を確定するcommit C**を固定する。対象は`requirement-claims`、`route-registry`、`auth-catalog`、`http-route-matrix`のJSON/lock各1件（計8件）。変更しない入力もC上の実blobを照合する。
2. oracle6資産（checkerの`ddl_elements/rejected_configs/claim_mutant_map/attack_tree/boundary_proposal/verification_evidence`）の`oracle_context.oracle_commit`と、sealの`oracle_commit`を**同じCへ同時前進**させる。実asset-specの各パスをrootが解決し、既存意味と必要な更新差分を確認する。旧commitのままdigestだけを更新しない。
3. 最終6資産の必要差分をrootの後続レビュー/受理へ提出する。候補試験成功やcontext変更だけで6資産を受理済みと扱わない。レビュー/受理後にのみ`--reseal-oracle`でblob/digestを再導出する。
4. `validate_oracle_seal`により、6contextとsealのcommit一致、8入力の作業木blobとC上blobの一致、最終6資産のdigestを全て確認し、更新flag/skipなしの全体検査を行う。C固定後に8入力が変わった場合はその変更を保持した新しい入力commitを固定し直し、影響差分をレビューへ返す。

根拠は組立HEAD `f5bda183300846ba2d457cfa9c9eb92cdeffdd7e`の`scripts/check_authz_catalog.py:7121`と`:7184–7225`。
`_build_oracle_seal`は既存sealをコピーしてinput blobとsealed asset digestを再計算するが、oracle_commitを変更しない。
`validate_oracle_seal`は6context一致とcommit上の8blob一致を要求するため、`--reseal-derived/--reseal-oracle`だけではcommit更新の不足を解消できない。

上記CLIはroot用の手順列挙であり、この起案で実行しない。正式値/履歴の唯一writerと受理時期を変える許可ではない。
候補実装中の正式checkerが未受理history/lock等を拒否した場合は理由を記録し、候補局所検査の成功と区別する。
実統合で値が変わった範囲だけ追随し、既受理sourceの意味や既存履歴を再裁定/遡及編集しない。

## 6. 実装ステップとDoD

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 固定sourceと新しい正常置換候補を保持して、read登録metadata/正例/全field生成対応と試験を局所固定する | 第3節の限定候補だけで2factory/2token/2GETの対応を独立レビューできる。正例/拒否変異・生成全field/実registry・C2入口対応の局所検査が緑。正式7.7/履歴/snapshot/最終sealはroot後続ゲートとして未達を明示し、親追加敵対枠を消費しない |

DoDはレビュー可能な未受理metadata候補であり、#175正式提供/7.7/作成/RG1/1球/1試合の完成ではない。
指示されたこの1ステップを実装したら日本語の`(ステップ 1/1)`コミットで停止する。
承認前の今回はplan/researchだけを起案し、既存3候補のmerge以外は実装しない。

## 7. テスト・受渡し

- root：`uv run pytest tests/test_check_tenant_boundary_bypass.py tests/test_check_authz_catalog.py`。正例fixture exact-set、全拒否変異、他symbol/module/API/署名の拒否と旧登録保持を検証する。
- backend：`uv run pytest tests/test_authz_repository_contract.py tests/test_game_preparing_components.py tests/test_game_preparing_read_boundary.py tests/test_api_app.py`。正常置換候補の既存exact集合を維持し、read2件だけを追加する。
- read実HTTP/専用DBは既存`tests/db/test_api_auth_exit_entry.py -k preparing`の実収集対象を確認して実行し、認可成功stub/Cookie事前注入を使わない。保存read成功は作成成功ではない。
- UI/API/providerの固定sourceと正式登録の接合後は、既存read専用`pnpm exec playwright test --config src/screens/GameScreenPreparingRead.playwright.config.ts`を用いる。旧sealed-ui全件/新TLS・署名鍵生成器を実行しない。専用DB/動的port/資格隔離とcleanupを維持する。
- root/backend Ruff/ty、対象Prettier/ESLint/vue-tsc、docs-status/局所計画同期、差分・保持対象byte/新権限0・core被覆を確認する。
- 正式checkerは`uv run python scripts/check_tenant_boundary_bypass.py --base-ref <比較基線>`と`uv run python scripts/check_authz_catalog.py --asset-spec product`。局所候補検査で消したTB005と、全体の未受理拒否を取り違えない。
- 起案/実装/正式受理の固定HEAD/diff/source hashと失敗・skip・未提供をresearchへ残す。共有DB/.env/秘密・P6封印は読書きせず、他worktreeを編集しない。

### 計画承認

2026-10-23T17:13:09.266744+00:00、Codex主担当/rootはPO委任4/5/6/7/8/10に基づきplan b9c01f62dd1150ed0a05fd666f11e515e8b2919eac625af2e43918ca7c9fbb02 / research1cddce040102f3dc1334834840a5c56658517f0c3f2d7b194e3d9eeeabe8d280を承認。独立非作者/root/independent_reviewの第1回P1=1（oracle anchor/6context手順不足）を全採用、第2回反映差分/影響は可決0/0/0。正常な記録権置換候補HEADの供給と個別指示後に本ステップ1を実施し、旧1730aaa系をmergeしない。正式7.7値/履歴/snapshot/最終sealは実統合後の実baseでroot直列受理。親175追加敵対1回と旧レビュー系列を保持し、今回計画/候補準備の成功を正式read提供・実機・人間署名へ広げない。

### read経路のexact-set検査器追随（限定追補・PO委任承認済み）

実装調査で`_validate_record_and_aggregate_route_ids`（固定組立f5bda183の2278行）が既存7経路を閉集合としていることを確認した。本計画で既に対象としたgames:readをroute/matrixへ追加するだけでは構造検査が拒否するため、第3節へ既存checker sourceの同集合1件追記を追加する。経路の意味・CAP・認可・DB権限・入力source/2GET・正式受理時期は変更しない。新core pathはなく既存guard捕捉を維持する。既存`tests/test_check_authz_catalog.py`で正規8件、games:read欠落、旧7経路の各欠落、余剰routeの拒否を検証し、exact-setを動的入力へ追随して弱めない。独立限定計画レビューとrootのPO委任承認前にはこのchecker差分を実装しない。前計画レビュー2回・初回oracle P1採用履歴・親175追加敵対1回未消費を維持する。

2026-10-23T17:19:48.188174+00:00、Codex主担当/rootはPO委任4/5/7/8/10に基づき追補plan SHA256 c06fe3c3bd808e9ae11969b43dff5f675887c3a7d1fa32f3541dfa89087bcab3を承認。非作者/root/independent_reviewの限定差分レビュー0/0/0を受領し、既計画のgames:read1行に必要な検査器の固定集合追随と全旧拒否保持だけを許可する。過去2回と今回限定1回を別に保持し、親175正式追加敵対1回は未消費。人間本人の逐行確認・署名を代記しない。checker差分はこの承認後に実装可、正式値/履歴/封印のゲートは前節どおり。

### 正常供給接合のcore機械整合（root委任追補）

rootが新PR #180の正常候補`dfa697721f35f573d2e3802783ff3d8d3cd218fa`だけの隔離mergeを許可した。
旧0aaa/8037等はmergeしない。WIPは外部backupと識別済みstashへcommit前に保全する。
当該mergeで競合する`.claude/core-areas.json`・`scripts/core_guard.py`・`tests/test_core_guard.py`を、両供給の登録/旧順序/拒否試験を保持する機械整合だけに限定して追加scopeとする。
JSONはAPI由来tenant2patternと初期付与2patternを双方保持し、guard全関数のAST/拒否ロジックを変更しない。
元各枝の先行宣言→別JSONコミットの履歴を保持し、実`_changed_paths_in_commit`/`verify_area_path_baseline`でmerge commitを検査する。違反を発見した場合は完了扱いせず主担当へ返す。

指定31194比較ではtenantのAPI2＋initial2を全件追加層として扱う候補である。
実#180統合後の正式#175比較ではinitial2が据え置き層となるため、実baseを取り込んで**API2だけをpendingへ回転**させる必要がある。
部分overlapの拒否を緩めて両状態を通さない。metadata自身の新core path不要という根拠は不変で、正常供給の2pathはその元の先行宣言/別JSON履歴から継承する。
正式7.7履歴/snapshot/lock/oracleは引き続きrootのみが実統合後に受理する。
