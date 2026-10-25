---
feature: mvp-rg1-lifecycle-connection
status: active
承認: 済（PO委任によるCodex判断、ステップ1/2/3の対象版を本文に固定）
重さ分類: コア領域
branch: feature/mvp-rg1-lifecycle-connection
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 1
実行方式: 通常
反映周コミット: 適用
---

# RG1の安全な成功条件と実作成接続

旧U-R1計画の新7/8のうち、安全な閉鎖・証拠照合・解除を製品へ供給する限定実装単位。全体計画は変更しない。固定baseは正式develop547d199e、作成候補65598dad、台帳の保護witness固定1e4381f8と後続authorityの実提供版を使う。rootが本worktreeの唯一の編集担当となり、台帳package/他担当パスを並行編集しない。

## 意味と最初の到達点

根拠はsync-protocol9-5/11-4、data-model3-2、U-R1 plan新7/8、rg1-preparing-acceptanceのD4分離。preparingではD4/V12/初期権・保持端末を発行しない。必要なのは認可後・INSERT前と同じ取引のcommit直前の実RG1成功だけである。台帳の全昇格/全設備喪失・非0復元・記録開始/T1完成を新規作成成功の前提へ追加しない。

最初は実隔離環境の一度限りのfresh初期化を、復元外の保護されたgenesis・実identity・既発行/不明/回収対象0の証拠から確認し、同じRG1行を正規制限経路で開いて実画面新規作成→HTTP201→DB保存→GET/reloadを通す。単なるDB行0/fixtureのopen/always-trueで成功させない。復元後の対象0とは別で、旧epoch/予約/未確定journal/不明な既設環境をfreshへ読み替えない。

閉鎖はRG1行だけを最初の取引で排他更新し、通常writerの共有lock排出を確認して確定する。close commit後も再open/競合controllerを防ぐ実leaseを保持し、authorityが同business identity/epoch/close範囲/保持主体/未消費proofを専用能力で照合できるようにする。identity専用observerをRG1読取へ拡張しない。呼出者のbool/任意JSON/非空IDを証拠としない。接続・lease喪失/再起動・旧DB復元・commit不明は閉じたまま。

非0復元の全旧世代fence、端末回収/I6退避・閲覧/書出し・未回収0/期限切れ欠落なし、解除と新D4(D3=0)の不可分確定も同じ親MVPの完成対象として残す。未提供中は当該完了遷移を閉じ、fresh成功へ拡張しない。運用公開・運用解除判断・共有DB適用・新秘密/有料資源は含めない。

## 編集scope・core

新sourceは`backend/src/pitchlog/recording_rights/rg1_lifecycle.py`、固定SQL`rg1_lifecycle.sql`、非秘密機械入力`rg1_lifecycle_manifest.json`。試験は既存捕捉内の`backend/tests/test_rg1_lifecycle.py`と`backend/tests/db/test_rg1_lifecycle_connection.py`/専用support。必要な既存RG1関数body/認可生成/実catalog比較・ORM/migration・schema/認可/tenant登録は同じ能力の最小追加だけとし、現行read ownerのUPDATE(state)・app直接表権限・owner membership/汎用EXECUTEを増やさない。新runtime/control subjectを必要最小に分離する。

実装前に全予定pathの実core被覆を検査し、上記新3sourceと新たな意味帰属が必要な既存authz pathsだけをsync/recording/tenantへ先行宣言・試験→別commitのJSON登録で追加。全旧paths/順序/guard_paths/拒否ロジックを保持する。計画外の意味/新公開経路は追加せず必要点だけroot判断へ返す。

正式9資産/外部8・schema/認可manifest/lock/oracle・履歴/snapshotはroot唯一writerが実差分の完全値/旧prefixから導出し非作者確認/PO委任受理後に反映する。data-modelの新subject/解除境界が構造改訂を要する場合は同一単位で最小7.3/7.6を通し、計画承認で正本確定を代替しない。

## 実装ステップ

| # | 単位 | 合格条件 |
| --- | --- | --- |
| 1 | core追加層の先行宣言と試験 | 未登録/片側/共変更の拒否を保持し、製品sourceは未追加 |
| 2 | 別commitでJSON登録 | 完全追加層だけ登録、全旧集合/順序/guardを保持 |
| 3 | 実閉鎖/lease/proofとfresh解除・作成接続の候補実装 | 正規制限関数/実authority照合/最小role/RLS、実201/保存/再取得と途中全取消・閉鎖競合・再起動旧open拒否。台帳全DoD/非0復元へ成功を広げない |
| 4 | 正本最小整合・完全値受理・最終独立/CI・通常統合 | 固定HEAD/diff/実baseで全必要ゲート・必須全件CI成功。親新7/8の未提供範囲を保持 |

PO委任に基づく独立確認・root承認後、指定された1ステップだけ実行する。作業中は局所pytest/Vitest/Ruff/ty、実接合は専用DB/port/tempと既存非秘密認証fixtureを使い資源を直列調整してcleanupする。候補環境成功と正式develop/実機/運用成功を区別する。人間本人の確認/署名を代記しない。


2026-10-23T20:37:51.253623+00:00、Codex主担当/rootはPO4/5/8/10に基づき、対象583735f1/plan6ca62a21116e8afb1de7ed8385ccca37579c6498222f64777e2819eed60cc47eを承認。非作者rights_replacement_reviewの限定第1回0/0/0、標準binarydiffd1ef3fd344aa4113eafaff6e0b875922830fdc535fbcff881988cce0a841aa68を照合した。まずstep1の新3source先行宣言/試験だけを実施し、検査後にstep2の別JSON登録を行う。step3の既存関数body/認可資産/migration/起動接合先はその着手前に同じ局所追補へ具体化して確認する。過去承認の再取得や新しい人間待ちではなく、PO委任による対象版の実装具体化。人間本人の逐行確認/署名、実open/保存成功/正式7.3/7.7を代記しない。

## ステップ3の最初の物理小単位（候補・独立確認前）

まず**fresh初回開放の実制限制御面と実scopeへの保持**を作り、既存全復元制御/全正常経路のfence証明とは分ける。新規作成のD4/V12なしを維持する。未知/既設/過去activation/旧backup・business再起動をfreshとして解除しない。非0復元/全write-path停止の証明が未提供なら復元epoch前進へ使える全域closeProofを発行せず、旧advanceの閉鎖を維持する。

### 実source・主体・起動口

| 担当path | 具体化する内容 |
| --- | --- |
| `recording_rights/rg1_lifecycle.py` | root専用のUnix controllerとapp client。閉operation/有限frame/deadline/両方向SO_PEERCRED・root所有非可変config/親dir検査。callerの任意JSON/ID/boolを証拠としない。controllerが実DurableLedger.fresh_activation()からattestationとlive fenceを得る。必要境界未提供時はfail-closed。rootconfigはendpoint/UID/peer接続等の非秘密値だけで新秘密/署名鍵を生成しない |
| `recording_rights/rg1_lifecycle.sql` | 新schema `rg1_control`、NOLOGIN/NOBYPASSRLS/NOINHERIT owner `pitchlog_rg1_control_owner` と専用peer LOGIN/NOBYPASSRLS/NOINHERIT actor `pitchlog_rg1_control_actor`。actorへowner membership/表DML/汎用EXECUTEを与えない。固定controller排他lease・closed確定・fresh open・生存/closed観測だけの制限関数。既存singleton行を使用し新table/column/migrationは初小単位では追加しない |
| `recording_rights/rg1_lifecycle_manifest.json` | schema/role属性・固定関数/引数/戻り・SQL hash・最小列ACL/RLS・実供給依存の非秘密宣言。DSN/資格実値・署名/任意expected集合を保存しない |
| `repositories/rg1.py` | 既存2token/2function IDを保持し、正規controllerの実borrow/確認を同scopeへ結ぶ。default未設定/切断はRG1Unavailable。任意callbackの成功注入口を製品へ追加しない |
| `repositories/transaction.py` | RG1を明示照合したscopeだけに不透明leaseを登録し、PG commit直前確認・commit/rollback/結果不明後まで保持して最後に解放。GET/read一般や認証SQLへ一律RG1を前倒ししない。lease解放がcommitより先にならないExitStack順を実測 |
| `api/app.py` / `api/errors.py` | startupでroot所有configを検査しclientを設定（設定欠落は通常readを維持しRG1書込は閉鎖）。RG1Unavailableをscope rollback後に固定503外形へ。HTTP新経路・tenant選択・認可/C2迂回は追加しない |
| `authz/{classification,product_role_contract,product_control_access,product_table_access,product_catalog,product_provisioning,product_function_acl}.py` | 上記新2subject/schema/固定関数・singleton限定列ACL/RLSだけ。旧read ownerのUPDATE(state)を許さず、helperの限定EXECUTEで生存を照合。全旧role/ACL/policy・製品全数比較/拒否を保持 |

pathsの先頭は`backend/src/pitchlog/`。指定14実装/試験候補の機械被覆は現coreで14/14、新3sourceはstep2により捕捉済み。既存authzはtenant領域、RG1 function bodiesはsync/recording/tenantに捕捉されることを実pathで再確認する。実装所有はroot。SQLを別作者へ分割する場合はそのpathだけ引受台帳へ記録し、同時書込みをしない。

### 正式入力と試験の必要追随

正式反映はrootだけ：既存`contracts/authz/product/{ddl-elements,application-steps,exposure-facts,probe-product-map,failure-injection-points}.json`、`function-bodies/manifest.json`と`roles/rg1_control*`ではなく上記実role名のSQL、`schemas/rg1_control.sql`、`functions/FUNCTION:rg1_control:*`、singletonの追加owner列ACL/policy、既存RG1読取2関数bodyを実生成器/全catalog比較へ合わせる。capability/routeを不要に増やさない。tenant9資産/既存8外部・必要census/生成物/履歴/snapshotは実差分が変わる部分だけ完全値で受理。新tableを作らないためschema manifestの表数を仮増ししない。data-model3-2/索引は新2subject/制限境界の最小構造7.3候補を同単位で審査する。

試験：新`backend/tests/test_rg1_lifecycle.py`と必要なら`test_rg1_lifecycle_sql.py`、`backend/tests/db/{rg1_lifecycle_support,test_rg1_lifecycle_connection}.py`。既存`test_rg1_operations.py`/`test_rg1_lock_contract.py`/`test_authz_product_roles.py`/`test_authz_product_control_access.py`/`test_authz_product_function_acls.py`/`test_product_authz_catalog.py`、`tests/test_check_tenant_boundary_bypass.py`、既存実browser source`frontend/src/screens/GameScreenE2eServer.py`とread側のcreate操作case追加だけを必要範囲で追随する。source/testと期待を同時に緩めて通さず、unitの偽transport検査と実fresh/実PG/実UI成功を分離する。共有conftestの成功固定やRG1のalways trueを作らない。

最初の成功証拠はroot所有の隔離構成で、実genesis/identity/同期pair/未発行・不明0→実controller→実認証/C2→作成INSERT→commit後201→同ID GET/reload全値一致。直前閉鎖・controller/authority/PG切断・未知結果で201を返さず全取消し、古いopen行だけでも拒否する。controller喪失時のDB session lease解放、scope commit中の外部lease保持、peer偽装/不正frame/未設定を拒否する。非0復旧・全旧writer排出・全9-5経路/T8接合は親新7/8の次小単位へ残し、初回fresh成功でそれらを受理済みにしない。


2026-10-23T21:27:34.427271+00:00、Codex主担当/rootはPO4/5/8/10に基づきd156e605/plan50efb40ea978aed089c4847c2558471f549e64be7ffb1ee783161e53dd768fa2のステップ3最初小単位を承認。非作者rightsの限定第1回0/0/0、標準binarydiffa3cdc6ee397ea879f5f82912ec87c7d8524acd0941fce85132b68be00d9ef959を照合した。まずSQL/機械manifest/実Unix client・scope保持を候補実装し、実fresh供給未提供では閉じる。SQLの固定内部名はrg1_control.{try_controller_lease,release_controller_lease,close_gate,open_fresh_gate,controller_lease_alive,read_closed_gate}、いずれも引数なし、最後だけjsonb/他booleanと具体化する。controller排他leaseとopen生存leaseを別keyにし、closed確定後・実fresh照合後だけopen leaseを得る。新roleの7属性/列ACL/RLS/固定search_path・完全修飾を維持する。編集分担はroot=Python/manifest/transaction/rg1/API/共有資産/文書・Git操作、csv_review=rg1_lifecycle.sqlと専用test_rg1_lifecycle_sql.pyだけ（同一worktree別path、Git/index操作禁止、完了handoff後rootがcommit）。追加の人間承認待ちや過去承認再取得ではなく実装具体化。実201/正式7.3/7.7/全MVPはまだ未達。


### 同一Sessionの実DB束縛（ステップ3の技術具体化）

2026-10-23T21:48Z、PO委任によるCodex主担当/root判断。制御peerのDBと作成scopeのDBをcaller値ではなく双方の実観測で一致させるため、固定読取 `rg1_control.scope_binding(p_tenant_id uuid) RETURNS text` を追加する。既存tenant GUCとの一致を検査し、system_identifier/database_oid/database_name/postmaster_started_at/backend_pidの5要素だけを実PGから返す。appはこの1関数のEXECUTEとschema USAGEのみを持ち、制御6関数・DML・membership・汎用EXECUTEを持たない。既存RG1の2token/2ID/署名は保持し、新token `RG1ScopeBindingToken` / ID `RG1:scope_binding` / capability `CAP:rg1:scope_binding` / factory `_build_rg1_scope_binding_statement` を同じ閉じたregistryへ登録する。必要な追加編集は `repositories/operation_registry.py` とこの登録に対応するexact metadata/正負例のみ。新HTTP経路、任意SQL、独自tenant選択を追加しない。完全正式値の受理・非作者レビュー・実PG検証は従前のステップ3〜4の条件を維持する。これは新たな記録意味・安全条件の変更ではなく、すでに承認された実business識別の補完不能な観測手段である。


同じステップ3の影響試験は既存 `test_function_operations_boundary.py` の新1登録exact追随と `test_api_app.py` / `test_api_errors.py` の未配置read維持・未信頼config拒否・PG終結不明503非漏洩を含む。既存DML集合/旧bool2登録と拒否を維持する通常追随であり、新HTTP製品経路・認可成功条件を追加しない。


ステップ3の実接続に必要な同単位の正本7.3候補準備は並行して進める。第4ステップの正式受理/全最終CI/通常統合条件は維持する。2026-10-24、rootは今回PO委任の計画順判断として、実fresh→controller→app peerの1接合成功と非作者91e90限定0に基づきdata-model3-2の最小構造候補と旧読取2SQLの安全な成功条件候補を作成する。単一行openをTrueに置換するのではなく、実actor同DB/PIDの二重leaseと同scopeの実borrow/fence/commit保持を揃える。正式authz/manifest/7.7未受理、最終201/reload未実証は保持する。


### 実INSERT件数の保持（通常不具合是正の最小追補）

2026-10-24、PO委任によるCodex主担当/root判断。実HTTP接合で新大会INSERTがSQL例外なしにrowcount=-1を返し、既存_require_insertedがoutcome_unconfirmed/rollback503へ閉じる不具合を実測した。ロック済みSQLAlchemyのpreserve_rowcountの動作根拠と整数件数だけの非改変観測を照合し、`repositories/base.py`の単発実行と`repositories/transaction.py`のscope実行が、検証済みCore statementの実件数をclose前に保持する実行optionだけを指定する。型/SQL/bind/tenant/ロック/順序/未知・0・複数の拒否は変更せず、件数を1へ補完しない。追加編集範囲はbase.pyと対応する既存基底/transaction試験、既承認の隔離実HTTP/DB接合試験だけ。別計算/新API/認可成功注入口/凍結免除追加はしない。sourceの非作者限定確認と、実POSTで新規INSERT→201/GETを通す回帰を必要とし、正式metadata/全件CI/最終通常統合は既存条件のまま。


### 正式認可全数の有限追随（既承認step3のPO技術具体化）

2026-10-24、rootはPO4/5/8/10の実装具体化委任により、固定RG1 SQL8b8b36e9/manifestf3b1e1c4とledger業務identity SQLa3218c04/manifestcb0d0ecdの実集合を既profileへ登録する。同じscopeのsourceは既宣言7authz moduleに`scripts/check_authz_catalog.py`の対応有限validator分岐を明記追加する。正式JSON/body/corpus/9・8/受理と正本はroot単独writer、source/testはrootのpath別個別委任で編集を一本化する。

登録は旧7role全属性を保持して実control2＋business observer2を加える11role（observer ownerは実SQLどおりINHERIT true・membership0、他新3はfalse）、schema5→7、関数56→64、policy37→39、既存table46不変である。既知差分4種はCONNECT2/public USAGE1/singleton列ACL3/policy2であり、全profile差分はそれだけではない。外部台帳cluster専用4roleを業務profileへ混入させず、主体7属性/全membership/owner/ACL/固定関数本文・search_pathを全数検証する。appの旧read ownerへstate UPDATEやcontrol actor権限を与えない。

builtin追加EXECUTEは既acl_expectationsの有限な追加kindで、pg_catalog.pg_control_system()・引数空・EXECUTE/grantable false・追加granteeがcontrol_owner/identity_ownerのexact2組だけとする。PUBLIC builtinの既実効権限を変更せず、追加明示grantと既実効を別検査する。app/probeへの新明示grant/任意builtin/引数/任意SQLは拒否。撤去は追加2grantのREVOKEだけで、builtin DROP/OWNER/PUBLIC権限の改変をしない。既一般group/全拒否を保持する実装選択であり新野球意味/耐久条件の変更ではない。

DDL bodyは既認可manifestへの有限配置、既生成器・validator・実catalogへ接合し、固定SQLと別の判定意味を作らない。source自己申告だけで全数成功にせず、正式資産と実DBの追加/越境/直接DML/membership/最小権限・撤去を確認する。provisioningは既CREATE ROLEとsourceSQL二重適用を避ける一回配置へ整合する。RG1 source SQL/manifestのstatic2は全母集団へ残し、ledgerの正式宣言方式と同じ閉じた追加宣言を別途rootが反映する。RG1:scope_bindingは旧2固定登録＋resolverを保持してexact1追加し、任意function呼出しは認めない。

次のsource委任は具体集合/正負例とcacheへの未適用正式候補までで、正式history/snapshot/承認/統合はrootの既step4へ残す。現在app/control2+observer2の提供を、新broker actorやT1/全非0復旧完成の前提へ戻さない。既承認内容の通常具体化であり人間の新たな承認待ちを作らず、必要な独立最終差分確認/実値受理/必須CIは省略しない。


## 初期actor向けの既承認供給の最小追補

根拠は承認済み6065063bのstart plan §6.1/6.2/6.4と末尾のPO委任確認。本段は全体計画を変更せず既ステップ3/3内で、初期権を止める未供給だけを具体化する。source作者準備は /home/ymdms/.cache/pitchlog/rg1-initial-actor-supply-candidate-20261024/evidence.json（SHA256 3175494e06bfd1a2157c4dc84951741b5196cf08ad9ef9bf031ceb0500f7986a）。これは独立レビュー/正式受理/DB実証ではない。非作者の有限差分確認とrootの既委任判断後にだけ当該sourceを適用する。旧ACL P1/別core P1の終結と全レビュー履歴を保持する。

- 初期actorはUID20002/role pitchlog_initial_actorのexact1組だけ追加し、旧UID20003/pitchlog_appを保持。controllerはkernel peerからroleを決め、同じDB/実PID/pg_stat_activity roleをborrow/held/releaseで照合する。caller JSON role/tenantやboolを証拠にしない。
- scope_bindingと旧RG1 read/commit-checkの3関数EXECUTE、rg1_control/rg1_apiの必要USAGEだけを追加。旧2関数のAS本文、tenant/state/lease/lockを不変保持し、初期actorへcontrol関数EXECUTE・表DML・builtin一般EXECUTE・membershipを与えない。
- 初回専用rg1_control.bind_initial_fresh_epoch(bigint)は実fresh_activation内の同controller Sessionだけから呼ぶ。真正provider attestation/live fence/business identity/epochを照合し、closedかつNULLへ実attested E1だけを束縛する。既control owner/actor境界・固定search_path・PUBLIC/app/initialactor拒否を保持。旧control2列ACLにepoch専用1列ACLだけを加える。
- 既noarg openの未割当XID拒否を維持するため、close commit→真正fresh/fence→epochのみcommit→別transactionで既open commitとする。間はclosed。setter/openの結果不明は成功へ補完せず、NULL推測1/上書き/自動再fresh/非0復元・epoch前進へ拡張しない。後着actorは正規設定済み生存controllerへattachするだけ。

### sourceと供給順の有限範囲

runtime/SQLは既rg1_lifecycle.py/sql/manifest、生成境界は既authz/product_function_acl.py・product_control_access.py・product_role_contract.pyとcatalog/provisioningの必要期待値だけ。旧3関数/schemaの正式bodyとauthz productの既JSON/manifest/必要生成body、tenant_boundaryの実影響値はroot単独で直列生成・完全値受理する。固定未適用2patch（d16ead7047fdcc9af31a56fd29185bb4a0370aaed533ef660a5de516561bc8a6 / 141729f10d89ef317e38bf592a37d55cb32b12349ff17cbf53fc8f531d422e1e）を入力にし、root独自の未審査拡張を混ぜない。

正常供給をPR間の循環にしないため、本RG1単位で既承認initial_actor/initial_fn_ownerの2roleを権限最小の前提として先行作成し、既新4roleと合わせ13roleへ追随する。初期9関数/4新表/Generation新2列は次のinitial-scope単位が所有する。RG1が必要とするgate.recovery_generationだけを本単位のnullable正bigint・補完なしとして先行供給する。実latest34を再照合後に新0035_rg1_initial_fresh_epoch.pyを配置し、初期scopeの未適用0035候補は0036へ通常改番してdown_revisionを接ぐ。初期側からgate列追加を除き同じORM属性/制約を保持し、未適用候補以外の既migration履歴や既データを改変しない。この3列は既存2表への合計3列という606の範囲を変えない。

この前提sourceはdb/recording_rights/models.pyのgate属性だけと新migration、root役割宣言2件だけ。新roleはまだ初期9関数の実行権・直接業務DMLを持たず、APP旧12列read/updateと既INSERT剥奪方針は初期scopeの正式供給へ続ける。CSVの初期2role/9SQL candidateと二重CREATE/二重body所有をしない。Gate列とroleの既core glob包含を実確認し、対象漏れなら先行宣言/別JSONなしに新sourceを書かない。

影響正本は既docs/design/data-model.mdのRG1/role/初回束縛の有限節とdocs/README.md。新契約の実現手順だけを7.6/必要7.3・7.7へ運び、全設計や既意味を再承認しない。実Port/DBをこの具体化の着手前条件へ追加しない一方、正常actor借用/初期grant・再交付・unknown/失効/越境/原子性/実role ACL・catalogを隔離DBで通す前に提供完了とはしない。

試験編集は既backend/tests/test_rg1_lifecycle.py、test_rg1_lifecycle_sql.py、test_rg1_operations.py、test_rg1_lock_contract.py、test_authz_product_roles.py、test_authz_product_control_access.py、test_authz_product_function_acls.py、test_product_authz_catalog.py、tests/test_check_tenant_boundary_bypass.py、backend/tests/db/test_rg1_lifecycle_connection.py/rg1_lifecycle_support.pyの実影響だけ。初期側の実DB2pathは初期scopeが所有する。合成9probe/SQL静的検査を実PGや耐久証明へ読み替えず、固定HEAD非作者レビュー・全必須CI・実merge確認を通常統合前に揃える。


## 初期peerの正式catalog入口追随

既606/c58のCONNECT1・schema USAGE2・epoch列ACL1を、既check_authz_catalogの閉じたexpected集合へ接合する。rootはcache固定source案07bc28ecc66cd57baa12bb04022c95ea5a39e8c0834f6d275b059f637c068c88を適用し、tests/test_check_authz_catalog.pyへ最小DB接続権の正例と欠落/owner流用/CREATE/TEMP/委譲/整数bool拒否だけを追加する。旧主体/旧権限/未知拒否を保持し、正式schema-manifestと全profileの実値受理が済むまでCLI/DB正常供給とは扱わない。source案/asset候補作者と異なる非作者が最終差分を確認する。PO委任によるrootの有限技術具体化で、新しい意味・権限緩和・共有DB適用を認めない。


## 実段階起動と0035列の順序接合

2026-10-24、rootは既PO委任の通常不具合修正・保存保証を維持する具体化として、隔離候補5f074491の実PGで発見した前提列/認可順の是正を既ステップ3へ含める。S0(0033)から全認可前段が新recovery_generation列ACLを実行し、列を追加する0035未適用のためUndefinedColumnで停止した。1error/必須call未到達4.64sを失敗として保全し、共有DBへ適用していない。

- `backend/src/pitchlog/db/stage_a_startup.py`
- `backend/src/pitchlog/authz/product_provisioning.py`
- `backend/tests/test_product_authz_provisioning.py`
- `backend/tests/db/test_stage_a_rule_candidates.py`
- `backend/tests/db/rg1_lifecycle_support.py`

前段の旧resolver保留16件を保持し、新epoch列ACLのexact1件だけを後段へ保留する（実241DDLから直接列参照依存を照合）。0034の固定規則配置を確定した後、ownerで0035のnullable正bigint・補完なし列を適用し、全認可→S3の実revision/列型・nullable/default/check・全catalog照合へ進む。再開は既固定5行/owner/RLS/一時権なしを保持し、既知0034は0035を適用、0035は再適用せず、未知revision/偽marker/欠列を拒否する。常時成功や記録権/認可/RG1の迂回は作らない。

DB試験補助の正規生成profile後の同SQL二重直接適用は除き、実関数・peer認証・最小権限の検査を維持する。候補作者は専用cache wtだけを編集、rootが所有disposableで実PG試験を実行、非作者が最終差分と故障/再開例を確認する。正式共有資産/全値受理はroot単独で直列化し、source5fの一次8射影/N3導出は保全、是正source後に必要分だけ再導出する。新しい規則意味/安全性削減/共有DB適用の承認ではない。


## 再適用と読取試験の有限追随

実PGの段階起動は前段/後段の両方で正規認可を適用する。241DDLを全数分類し、新6roleのplain CREATE、新schema2、plain CREATE FUNCTION2の再適用漏れを閉じる。既5pathに次の5pathを加えsource/test計10pathとする。rootは既PO委任による通常接合修正として範囲を確認し、非作者が最終差分を照合した後だけ正式受理へ進める。

- `backend/src/pitchlog/authz/product_role_contract.py`
- `backend/src/pitchlog/authz/product_function_acl.py`
- `backend/tests/test_authz_product_roles.py`
- `backend/tests/db/test_rg1_startup_epoch.py`
- `backend/tests/db/test_rg1_lifecycle_connection.py`

6roleは既単一意味の7属性と両向membership0を使い、不存在時CREATE・存在時全一致だけ再適用を許し、不正既存をALTERして修復しない。schema2は既適用器に所有者exactの再適用guardを置き、不正ownerを修復せず、旧5schema SQLを変えない。function2は既rendererでCREATE headerだけOR REPLACEへ正規化し、AS判定本文/引数/戻り値/ACLを全保持する。生成bodyの計8既path（6role/2function）はroot単独で生成し、他233body/旧7role/固定外部SQLを保持する。未知role/schema/functionと既存衝突を拒否する。

DB試験は専用owned fixtureで実owner/admin別主体とsession_user/current_userを照合する。unused DSNはテンプレートだけで、factoryが実動的port/DB/資格へ置換し外部DSNを使わない。requires_db/実call0拒否を維持する。旧primitiveの常false期待は採用済data-model1.3§3-2安全な成功条件/本plan88行相当の追補へ接合し、2readのlease無しopen・違tenant・controller喪失/再起動falseと、同DB/PID二重lease時のtrueを検査する。手動のprivileged SQLprimitive成功を実DurableLedger.fresh_activation・初期grant・UIの成功証拠へ拡張しない。

中間の1error/3error/4error/4成功1失敗を保全し、最終はsource/test10＋生成SQL8の全18file前後hashを同一固定して5DB成功・独立非DB147成功/所見0/0/0を確認した。これは候補の正常起動/再開/権限境界の実証で、正式9射影/8source完全値受理・残検査/全件CIは引き続き必要である。


## 起動補助の検査メタデータ接合（2026-10-25）

既PO委任による通常追随として、実検査済みstartupの `_apply_epoch(owner_dsn: str)->None` と `_require_epoch_state(applicator_dsn: str)->None` をbase-allowlistの既allowed_symbolsへexact2追加し、既 `_require_placed_state(applicator_dsn: str)` の戻り値だけNone→strへ追随する。前者は既_apply_placementと同じcreate_engine/Engine.beginの2API、後者は既_require_s3と同じpsycopg connect/cursor/executeの3APIだけ。既35行はこの署名1値以外保持する。sourceのDB操作やchecker拒否条件/global scan allowlistを変更しない。

対象は contracts/tenant_boundary/base-allowlist.json、tests/test_check_tenant_boundary_bypass.py、tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/ の新_apply_epoch.py・新_require_epoch_state.py・既_require_placed_state.py と本plan/research。正例・登録欠落・署名差替え・余分API・未登録同module関数の拒否を確認し、非作者へ有限差分を渡す。現在の全値提案は未受理のまま保持し、修正後の正式census/9射影8外部を再導出してから単一受理する。TB005を許容census codeへ追加しない。

認可の広域回帰で検出した product/exposure-facts.json のRG1物理資源引用1値も、採用済data-model1.3§3-2の現本文へ逐語追随する。分類・理由・権限・他evidenceは変えない。新13主体/7schema/65関数の既意味に対する既backend認可試験の件数・候補fixture依存供給だけを是正し、negativeの対象操作/拒否理由を保つ。共有JSONのwriterはroot、既backend/testsのclassification/database_schemas/function_acls/staging/table_access/table_rls/migration_batch_roleの実影響差分は担当分離して候補化・非作者確認する。
