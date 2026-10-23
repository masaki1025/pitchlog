---
feature: mvp-preparing-create-connection
status: active
承認: 済（PO委任によるCodex判断・preparing作成接続）
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3da93b75e687812e9b44d0b6ff5196e7
branch: feature/mvp-preparing-create-connection
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# preparing試合作成の限定接続計画

## 1. 背景・目的

[要件正本](../../requirements/requirements-pitchlog-2026-07-22.md)FR-001/014/033/034/039、NFR-005/014/018/019/023に従い、必須大会と両チームを指定するpreparing作成を接続する。親は固定`d68e10ed30d77cbe5361ece4cab2a3bd6dac9461:docs/features/ug1-preparing-connection/plan.md`の承認済み6ステップ中5/6と同`design.md`。元U-G1の8ステップ・親の6ステップ・既レビュー/採否を保持し、本計画はその5/6の追加実行単位である。親6/6の実画面受入や開始/1球へ改番・拡張しない。

実起点は`31194a39c9083bbef6c14bde19c24a3e49d09f2e`。今回許可は新worktreeで本plan/researchだけを起案すること。製品・候補sourceのmerge・正式資産変更は未着手。本計画の非作者レビューとrootのPO委任承認後、指定された1ステップずつ実装する。公開/正式受理/本人署名を代記しない。

## 2. スコープ・供給条件

対象は`POST /games`と`GET /games/preparation-options`、既存/new排他的大会指定、両team検証、単一resolver/codec、同一scopeのINSERT、RG1事前/直前、commit後201、および既存入口の作成フォーム。既存rosterのself/opponent取得をそのまま使う。大会なし・固定大会への縮小、新大会管理画面、規則割当/上書き設定、計算、記録権/D4/開始/1球、同期結果や冪等キーの新意味は対象外。

固定供給は以下の正常履歴候補を参照する。正式受理・実develop統合はそれぞれ別であり、成功実測と混同しない。

| 供給 | 固定HEAD・利用範囲 |
| --- | --- |
| read/API/UI/browser/登録候補 | `6f60983c4c905008615b7683c1f7084b8b1a5b45`。通常client、C2、Page/保存read、core登録、単一codec、既存画面を保持 |
| resolver | `efe497ec05ca8784d6f570480ba6970c7134e149`。`repositories/rule_resolution.py`の公開入力/4失敗/同一scopeと固定関数、正規codec |
| initial | `95d766f5d20234b1d534538b96fc369eda1cc6f1`。readの祖先に含まれる正常な初期付与候補。preparingでは付与しない。RG1成功供給ではない |
| RG1成功許可 | 現指定候補には未提供。rootが別単位で固定する実source/契約/認可資産だけを後段で接続。always-true関数/Port・auth override・SQLによる運用openを作らない |

承認後の隔離組立は指定正常HEADだけを通常mergeし、全旧登録・供給source・履歴/snapshotを保持する。旧173の`0aaa22e0`/`8037e1d9`/`f48b5944`をmergeしない。競合の意味変更・guard緩和・supplierの受理値書換えはせず、機械整合で閉じない当該差分だけrootへ戻す。RG1実成功・Port/HTTP完成・正式7.7はステップ1/2の準備開始条件にしない。

## 3. 影響する正本・予定編集範囲

requirements/design/ADR/development/opsへの反映なし。既存FR-014段階A、preparingで初期付与しない境界、RG1 fail-closedを保持する。正本の新意味・DDL/ACL/RLS・migration・依存更新が必要なら具体差分だけ別計画/個別ゲートへ出す。

承認対象となる後続編集範囲は次だけ。現起案の編集所有は本plan/researchの2ファイルのみ。

| 範囲 | パス・許す差分 |
| --- | --- |
| backend作成 | 既存`backend/src/pitchlog/repositories/games.py`と新`backend/src/pitchlog/repositories/preparing_game_creation.py`、新`backend/src/pitchlog/services/game_creation.py`、`backend/src/pitchlog/api/schemas/games.py`、`backend/src/pitchlog/api/routers/games.py`。既存readを保持し、作成/optionsのtoken・固定文・DTO・service・handlerを追加 |
| 実登録/C2 | `backend/src/pitchlog/repositories/operation_registry.py`、`backend/src/pitchlog/api/tenant_access.py`、必要な`backend/src/pitchlog/api/app.py`の既存router接続のみ。実scope/execute/認証基盤/codec/resolver/RG1実装はコピーも緩和もしない |
| backend試験 | 既存`backend/tests/test_game_preparing_components.py`、`backend/tests/test_game_preparing_read_boundary.py`、`backend/tests/test_api_app.py`、`backend/tests/test_authz_repository_contract.py`、新`backend/tests/test_game_preparing_create_boundary.py`・`backend/tests/db/test_game_preparing_create_db.py`。`backend/tests/conftest.py`変更0、既存fixture/使い捨てPG構築を再利用 |
| frontend | `frontend/src/api/games.ts`/`games.spec.ts`、既存`frontend/src/screens/GameScreenEntry.vue`・`GameScreenEntryHost.vue`・`GameScreenEntryTypes.ts`・`GameScreenEntryProvider.ts`と対応spec、新`GameScreenPreparingCreate.vue`/`GameScreenPreparingCreate.spec.ts`・`GameScreenPreparingCreateProvider.ts`/`GameScreenPreparingCreateProvider.spec.ts`。共有Pinia/QueryClient/正規client/roster APIを再利用。readと開始封鎖を保持 |
| metadata候補 | `contracts/tenant_boundary/base-allowlist.json`・`repository-contract.json`、生成`backend/src/pitchlog/repositories/repository_contract.py`、既存read正例`tests/fixtures/tenant_boundary/positive/pitchlog/repositories/games.py`・`games/__init__.py`は無変更保持。新正例は後記の`tests/fixtures/tenant_boundary/positive/pitchlog/repositories/preparing_game_creation_allowed/`直下exact6パスだけ、追加試験は`tests/test_check_tenant_boundary_bypass.py`。新6factory/7token/6fixtureを一対一のfactory許可として追加し、他全field/順序保持 |
| 認可候補 | `contracts/authz/route-registry.json`・`http-route-matrix.json`、`tests/test_check_authz_catalog.py`。`scripts/check_authz_catalog.py`はrecord_and_aggregate既知route集合へ下記2件の追記だけ、旧集合と欠落/余剰拒否を維持。lock/oracle/正式履歴はroot後続ゲート |

`repositories/*`・`api/*`・`frontend/src/api/*`・`GameScreen*`・`backend/tests/db/*`は起点のcore対象。新serviceと新boundary試験は固定readのtenant-isolation登録`backend/src/pitchlog/services/game_creation.py`・`backend/tests/test_game_preparing*.py`で捕捉する（[research](research.md)）。これら供給を取り込んでから新ファイルを作るため、新core先行宣言/JSON登録は不要。実接合時に実`core_guard`で全予定パスと拒否保持を確認する。供給前に未登録serviceを先行作成しない。新しい対象外pathが必要なら、宣言/試験→別JSON→製品の別コミット追補を先に承認する。本planからcore3ファイルを無断編集しない。

## 4. 実装方針

### 入力・大会・チーム

既存`PreparingGameCreate`を再利用する。aware日時・5区分・UUID両team・必須大会の`existing(key)`/`new(display_name)`、任意5labelを保持し、tenant/status/applied_rules/rule_override/started_at/D4/余剰fieldを拒否する。同team IDを許し、両側それぞれの所有/可視性を確認する。FKだけでは大会category/disabledやteamのhiddenを保証しないため、同tenantで有効なtournament/両teamを同scopeで照合する。team選択は`/team-records/self`と既存対戦相手ページングAPIを使い、team作成・改名を複製しない。

optionsの試合区分表示は既存正本seed `contracts/seeds/game-type.json`の固定5組を読み、同じ表示名/キーを別定数へコピーしない（欠損/不正seedなら非成功）。非tenant表をtenant operationへ偽装する新DB読取は作らない。大会は`category='tournament' AND disabled=false`の大会をSQLで限定する。大会ページ既定20/最大100、`key`昇順keyset・limit+1、応答に不透明next_cursorを持たせる。全件ロード/クライアント絞込みはしない。`/games/preparation-options`を`/games/{game_id}`より先に置く。

**大会名称の最小追補（今回のPO委任判断で採用、旧採用済みとは扱わない）**: DBに名称unique/正規化規則はなく、チーム名用NFKC等を大会へ転用しない。新名は入力Unicodeを保持し、正規化/独自長上限を加えない。空文字と空白だけを拒否する（空白判定はPython `str.isspace`、保存時trimなし）。既存指定は名称でなくkeyで同tenant/category/disabledを検査する。new指定の完全一致名が既存にあれば、無効名を復活/上書きせず拒否し、有効名は既存選択を求める409とする。複数一致も409、照会は最大1行で存在判定する。新keyはserver生成のopaque UUID表記、名前のslug/hashや端末生成keyにしない。DBが保証する一意性は`(tenant_id,key)`であり、同時新規登録の表示名グローバル一意性は保証しない。同名の異keyは区別して表示/選択できる。この扱いが親の既採用内容と相違すると判断された場合は当該名称分岐のみを差し戻し、入力/DML/フォームの他部分は継続する。新unique制約・新排他方式を暗黙に加えない。

### 保存と失敗

認証/C2 expected-tenant/認可をbody検証・業務SQL前に行う。作成は実`TenantContext`から単一`tenant_transaction_scope`を開き、RG1非ロック事前→大会確定（new語彙INSERT含む）/両team検証→`resolve_stage_a_rule(scope, StageARuleRequest(game_type_key,tournament_key,False))`を1回→正規`encode_applied_rules`を1回→game INSERT→RG1直前→scope退出commit→201。game IDはserver生成、status=preparing、rule_override/started_atはNULL、D4/初期付与なし。

resolverの大会親FOR UPDATE→別statementで割当照合→既定/規則FOR SHAREを保持し、両teamの検査ロックはその前に決定順で取得する。同teamは重複取得を除き、異なるteamはUUID順。既存実行器の限定team行ロック（通常FOR UPDATE、tenant/id/kindの等値bindとhidden_at IS NULL、selected idだけ、主キー全束縛）を再利用する。kindは先行readで得たself/opponentを用い、ロック取得後の存在/可視性を再照合する。kind自体はORMの不変列である。大会親のロックはresolverだけに任せ、汎用語彙FOR UPDATEや未対応FOR SHAREを実行器へ追加しない。待機後に有効性を再照合し、逆順取得や別Sessionによる検証に分割しない。実ロック形に不足があれば成功を仮定せず当該接合差分だけ提示する。

内部serviceは実scope exact型を受け、resolver/RG1を任意callback/boolで差替え可能にしない。登録tokenのみ実行し、tenantは実行器から注入、利用者に任意SQL/列/Session/tenantを渡させない。新語彙INSERTとgame INSERTは同じ取引で、全例外をscope外へ伝播させてrollbackする。scope内で失敗応答に変換してcommitしない。commit失敗/結果不明も201を返さない。

resolver公開4失敗の外形は親designを維持する: `stage_a_unsupported`=422、`rule_not_available`=404、`invalid_rule`=409、`outcome_unconfirmed`=503。RG1拒否/timeout/deadlock/serialization/未知障害は全取消後503。大会/チームの不存在・別tenant・不可視は同じ404、内部SQL/原例外/存在情報を露出しない。HTTPを再送指示とせず、createの自動再送0・冪等キー新設0。

### UI・認可登録

既存正規`apiRequest`のtenantBoundとCookie/C2を使う。新フォームは日時/区分/両team/既存大会又は新名称/任意labelを供給し、全値が揃いonlineのときだけsubmit可能。送信中は同じフォームの二重操作を同期的に遮断する。tenant/authEpoch/経路/要求世代を送信時に固定し、切替・unmount時は即時に選択/旧表示を破棄する。遅い旧POST結果で新tenantの成功表示/cache/navigationを変えない。abort/切断/503は結果不明として一覧/詳細で明示確認する。大会名/label/チーム名はVueの通常text bindingだけで表示し、生HTMLを挿入しない。復帰、focus、認証再確認でPOSTを自動再送しない。テスト用通信応答を製品の保存成功証明に数えない。

候補operation_idは`preparing_game_create`と`preparing_game_preparation_options`。候補route_idは`ROUTE:RECORD:games:create`（CAP:games:insert）と`ROUTE:RECORD:games:preparation-options`（CAP:games:read）、対応matrixは`HTTP:`接頭辞。実serviceの内部SELECT/INSERTには既存CAP:tenant_vocabularies:read/insert、CAP:team_records:readを必要操作ごとに対応させる。新CAP/DB grantは作らない。C2は実operation IDで通常registryへ追加し、静的routeを動的IDより先にprematchする。認証overrideで登録不足を補わない。

metadataのfactory許可は実sourceのmodule/関数/戻り文種別/署名をexact対応させ、SELECT許可へINSERTを紛れ込ませない。既存DMLの固定文検査・token登録・tenant注入を使う。許可方式に新しい検査能力が必要と判明したら、その具体的不足を限定追補してから実装する。生成moduleは`test_authz_repository_contract.py`の全field対応を正とし、3定数等へ限定しない。

### factory・token・正例の閉集合（第1回P1採用）

既存readの`games.py`/`games/__init__.py`はlist/detail専用正例として保持し、新関数のfixtureへ再指定しない。作成/optionsの新factoryと新tokenはすべて新module `backend/src/pitchlog/repositories/preparing_game_creation.py`に置く（module完全修飾名`pitchlog.repositories.preparing_game_creation`）。既存`repositories/*` core glob内であり追加登録不要。`repositories/games.py`のread SQL/許可2行は変更しない。

以下のfactoryはこのmodule直下の関数で、signatureの戻り型は`sqlalchemy.sql.dml.Insert`又は`sqlalchemy.sql.selectable.Select[Any]`を正規importする。表中fixtureの前置はすべて`tests/fixtures/tenant_boundary/positive/pitchlog/repositories/preparing_game_creation_allowed/`。**この6ファイルをexact集合とし、package用__init__.py等の余剰正例は作らない。**

| factoryのexact署名 | token型（同module）/CAP | 固定文の役割 | 一意fixture末尾 / allowed_api_ids |
| --- | --- | --- | --- |
| `_preparing_game_insert_statement() -> Insert` | `PreparingGameInsertToken` / `CAP:games:insert` | games INSERTのみ。tenantは注入、server game ID、preparing、規則6-key、全入力label。開始/権利列は発行しない | `_preparing_game_insert_statement.py` / `SQLA_INSERT`のみ |
| `_preparing_tournament_insert_statement() -> Insert` | `PreparingTournamentInsertToken` / `CAP:tenant_vocabularies:insert` | tenant語彙INSERTのみ。server key、tournament、表示名、disabled=false、不要属性NULL | `_preparing_tournament_insert_statement.py` / `SQLA_INSERT`のみ |
| `_preparing_tournament_options_statement(cursor_key: str \| None=None) -> Select[Any]` | `PreparingTournamentOptionsToken` / `CAP:tenant_vocabularies:read` | 有効tournamentだけ、key順、任意cursor_key、bind limit+1最大101 | `_preparing_tournament_options_statement.py` / `SQLA_SELECT`のみ |
| `_preparing_tournament_name_exists_statement() -> Select[Any]` | `PreparingTournamentNameExistsToken` / `CAP:tenant_vocabularies:read` | 同tenant/categoryのdisplay_name完全一致、disabled条件を付けず有効/無効とも409判定、bind limit=1 | `_preparing_tournament_name_exists_statement.py` / `SQLA_SELECT`のみ |
| `_preparing_tournament_parent_statement() -> Select[Any]` | `PreparingTournamentParentToken` / `CAP:tenant_vocabularies:read` | 指定keyの有効tournamentをbind limit=1で照合。待機後の権威ある親再検証/ロックは正規resolverが担当 | `_preparing_tournament_parent_statement.py` / `SQLA_SELECT`のみ |
| `_preparing_team_lock_statement() -> Select[Any]` | `PreparingSelfTeamLockToken`、`PreparingOpponentTeamLockToken` / いずれも`CAP:team_records:read` | 1行id SELECTの通常FOR UPDATE。tenant/id主キー全束縛、kindは各tokenのprepare/RequiredBindingでself/opponentへ固定、hidden IS NULL。任意kind/lock変種なし | `_preparing_team_lock_statement.py` / `SQLA_SELECT`のみ |

teamの先行lookupは既存`pitchlog.repositories.roster.SelfTeamRecordReadToken`（1件）と`TeamRecordReadToken(limit=1, record_id=指定ID)`（opponent限定、hiddenなし）を再利用する。self ID以外は後者で照合し、任意kindを利用者から受けない。既存`_build_roster_statement`/正例/登録は無変更。self/opponentが判明した後、上記2種のlock tokenをUUID順・同ID重複除去して実行する。同じ1factoryを共有する2tokenにfixtureを2重割当しない。gameの201 DTOは検証済み入力・server値・正規encode値から組み立て、追加のgame読取factoryを作らず、commit後の既存GETで保存全値を照合する。

他の再利用操作は公開resolverの`StageAResolveRuleToken`（`resolve_stage_a_rule`経由、既存固定関数factory/許可を保持）、`RG1PrecheckToken`/`RG1CommitCheckToken`（既存公開関数経由）、既存list/detail2tokenである。区分表示は正本seedで、新system語彙DB tokenは作らない。これらを含めて新設は**6factory・7通常token・6正例**であり、追加の実行SQLが必要なら先にこの対応表/scopeを追補する。

正例は既存`startup_allowed`と同じclass-qualified方式を使う。各一意fixtureに`class preparing_game_creation`を置き、対象factoryと同じ引数/戻り注釈の`@staticmethod`を1個だけ定義する。SELECT正例はselect1回、INSERT正例は小さなTableにinsert1回だけ。実行/接続/SQL文字列は含めない。実checker `scan_directory`の既存fixture alias（5939–5951付近）は、宣言symbol末尾2成分`preparing_game_creation.<factory>`をfixture moduleへ対応させる。製品は通常のmodule直下symbolで検査し、fixtureだけのaliasを製品へ広げない。fixturepath一意拒否（900–905）と正例actual/declared exact-set（1606–1616）は変更しない。

ステップ1はこの6factory/7tokenと候補OperationRegistration集合・serviceを実装するが、production registry/metadata/正例はステップ3まで追加しない。純入力/SQL生成・固定文検査と実常閉RG1の拒否を局所確認し、正式checkerの未許可TB005等を未受理として明記する。ステップ3で7tokenを既存PRODUCT_OPERATIONSへ追加し、6allowlist行/6正例を同時対応させ、generated module全fieldを再導出する。既存read2factory/正例/許可API/署名/順序を保持し、新集合だけの正例通過、全拒否TB900（各fixtureの単一DB API callを検出）、誤module/関数/署名、欠落/余剰/fixture重複、SELECT↔INSERT入替・text/updateの拒否を既存root試験へ追加する。実fixture検査はaliasを構成する既存`scan_directory(POSITIVE_ROOT, ...)`経路を使い、素のscan_sourceでclass aliasの検査を省略しない。実source側も6許可symbolのexact対応/全拒否を別に確認する。

### 実装ステップ（コミット単位）

| # | 実行単位 | 合格条件 |
| --- | --- | --- |
| 1 | 正常候補を隔離接合し、backend作成/optionsのDTO・DML/token・service・拒否境界を候補化 | 全供給bytes/旧登録/履歴保持とcore捕捉を確認。RG1常閉を保持し、上記6factory/7token候補（production未登録）の固定文tenant/列/型/上限、無効大会/category/両team/余剰入力の拒否、実RG1常閉から非成功・全取消を検証。実成功は未達。任意成功RG1/auth/codecコピーなし。正式資産の未受理拒否は記録して局所合格と区別 |
| 2 | 既存入口へ作成入力フォームと正規client/providerを接続準備 | 大会選択・new名・roster self/opponent・全任意値を保持。入力欠落/offline/送信中二重POST/旧epoch・遅延応答/結果不明自動再送0をVitestで検証。RG1未提供でも実装可、仮保存成功/画面seedを実作成成功へ数えない。既存read/開始封鎖を保持 |
| 3 | 固定実RG1供給を接合し、作成/optionsの通常登録metadataと実HTTP/実PG全取消を候補検証 | 実RG1成功source/権限/実提供契約をrootから受領後に接続。実login Cookie/C2→同tenant scope→正規resolver→INSERT→直前ゲート→commit後201とGET保存全値一致。新語彙直後/ゲームINSERT後/直前RG1拒否/commit障害で両INSERT取消、既存語彙不変を確認。RG1二接続競合を実関数で検証。7token登録/6factory許可/一意6正例・既存全許可保持/生成全field/正負fixtureを固定し非作者レビューへ渡す。正式7.7/lock/oracle受理は下記root後続ゲート |

各行は個別指示・個別commitで止まる。ステップ1/2の独立部分をRG1待ちで一律停止しない。ステップ3未供給は未完のまま保持し、成功stubで緑にしない。親6/6・read全workstream/親#175追加敵対1回は本計画と別に保持する。

## 5. DoD・正式化順序

本単位の成果は、親5/6へ返せる作成接合候補と直接影響する実証である。ステップ1/2の完了は準備済み、ステップ3の実証は候補接合済みと呼ぶ。正式提供済み/親5/6全充足はrootの後続受理・統合まで宣言しない。親6/6の画面からの保存/reload全受入、T1/P7、開始/1球/MVP全体完成は含めない。

root唯一writerの正式化順は、正常なinitial/read/resolver/RG1の実統合基線取得→全旧登録/guard_paths保持とpending宣言回転の検査→このcreate/options差分の完全before/after導出→対象ごとの7.7受理/履歴/snapshot/全field生成→認可の派生lock確定→oracle更新→最終非作者レビュー/全必須CIである。候補での局所成功、supplier rowのafter、古いbaseの値を新差分の受理へ延長しない。

7.7対象候補はtenant-boundaryのallowlist/repository射影（外部実装blobを含む）・そこから実際に動く他射影、route-registry/http-route-matrix・派生lockとoracle/seal。実基線で既存9射影すべての値/識別値/履歴を比較し、変化した集合だけを過不足なく導出する。現起案で新revision/digest/receipt行は作らない。rootが独立確認/委任受理する前に正式値を加えない。

oracleはroute/matrix等更新済み8入力を確定するcommit Cを先に固定し、6資産の`oracle_context.oracle_commit`とsealの`oracle_commit`を同じCへ同時前進する。必要な6資産差分をレビュー/受理後に再封印し、C上8blob一致/6context一致を通常checkerで検査する。`--reseal-oracle`だけではcommitを進めない。lock/oracle/正式履歴/snapshotは本実装scope外、root後続所有であり未成立を緑へ数えない。

## 6. テスト計画

| 対象 | 実行・観測 |
| --- | --- |
| backend局所 | 上記既存component/read/API/contract試験と新create boundary試験。DTO悪型/5区分/label/大会排他、tenant束縛/extra/禁止列、token強制変更/失効scope/任意SQL拒否。実RG1常閉/実resolver失敗のrollbackを先行実行。backend対象Ruff format/check・ty |
| frontend | games.spec、Entry/Provider既存specと新Create/Provider spec。正規clientの送信exact値、二重操作でPOST1回、遅延POST/GETとauthEpoch切替・旧cache拒否・明示結果確認。悪意ある大会名/labelの自動エスケープを確認。Prettier/ESLint/vue-tsc/Vitest/build。`.env`を読まない`envDir:false`で起動 |
| 実HTTP/DB | 新db試験は既存migration/製品認可DDL/実アプリ接続fixtureを再利用し共有DB禁止。server側のみをseedして保存成功と称さず、実Cookie/C2/登録scope/正規resolver/RG1を通す。正常201全値、別tenant/無効親/割当あり/上書き拒否/unknown拒否、新名を含む故障別の新語彙0・新game0、既存語彙不変、二接続の復元先行/作成先行を実測。RG1未供給時は未実行として残す |
| metadata/root | 既存test_check_tenant_boundary_bypass/test_authz_repository_contractの全fieldと上記新6factory/7token/一意6fixture、旧read2件を含む全許可保持、各新正例の全拒否TB900、誤module/関数/署名・fixture重複・SELECT/INSERT種別混入・text/update・欠落/余剰拒否。authz checker旧route全保持+新2件、C2 prematch順。root Ruff/ty、対象pytest、docs-status/局所plan-sync/core_guard、正式no-flag checker。既知未受理と実装不備を分け、skip/timeout/中断を成功にしない |

調査の固定根拠・未裁定境界・既存レビュー回数は[research.md](research.md)。本計画はレビュー第1回P0=0/P1=1/P2=0を採用し反映済み、改訂差分は未再レビュー・承認未。旧#175の基本2回・read追加1回未消費を継承しつつ、本計画の新しい局所レビューをその追加枠へ算入しない。

## 限定計画のPO委任承認

2026-10-23T18:35:59.893253+00:00、Codex主担当/rootはPO4/5/6/7/8/10に基づき、対象plan475c841df65c24381254b699bfdc4dd8291ed0c28c33146813211a1ae52d12aa/research0b092f80528dfbcdd4c6a81ceaacda77b8ecbb935b5ae4b4c423e98c110edad7を承認する。非作者/root/rights_replacement_reviewの全文初回P1=1（一意正例scope不足）を全採用し、6factory/7token/一意6fixtureへ反映後の第2回差分・影響は可決0/0/0。レビュー実行2回・指摘反映1周、親UG1/175基本2回とread正式追加1回未消費を保持する。

大会名は既存key identityとText保存を変えないAPI入力/失敗の具体化として、入力Unicode無変換・独自長上限なし・空白only拒否・完全一致既存名のnew指定409/既存key選択要求を今回採用する。例として「春季大会」と「 春季大会 」は別の保存文字列で、同名を同一entityへ自動統合せず、disabled名を復活/上書きしない。表示名のglobal uniqueや新排他/DB制約は追加しない。新しい記録結果・試合区分集計の意味を採用する判断ではなく、旧資料の未採用提案を過去承認済みへ書き換えない。

既存CAP・同一scope・RG1前後fail-closed/単一resolverとcodec・commit後201・C2先行・結果不明/自動再送0を保持する。rootが指示する1ステップずつ実装し、候補の成功を正式登録/7.7/実RG1・親6/6/1球/MVP完成へ拡張しない。人間本人の逐行確認/山田正輝の署名を代記しない。
