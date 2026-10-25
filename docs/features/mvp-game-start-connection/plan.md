---
feature: mvp-game-start-connection
status: active
承認: 済（PO委任によるCodex判断・開始入力の限定単位）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-game-start-atomic-candidate
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 試合開始の入力境界と実接合の先行単位

## 1. 位置付け

実起点は`4b2db6907f329c3dde113c3b7e1c3515600fb915`（実develop、PR181統合点）。正常PR180の初期付与部品を含む。本起案は新branchのplan/researchだけで、製品実装の承認ではない。巨大なfirst-path隔離組立をmergeせず、台帳・RG1・作成候補は必要な固定sourceを後続で個別供給する。

親は固定`67dff5f707dcb2311a35140ae870b44f46e24803:docs/features/ug1-game-lifecycle/plan.md`の8ステップ中3と、既存[U-F8計画](../uf8-full-game-followup/plan.md)の6・8。親U-G1は本起点に未収録のため固定Git参照とし、旧8/9ステップ・レビュー回数・開始側の着手条件を改番/消去しない。本単位のレビューを#175の旧追加枠へ算入しない。

開始operation/DTO/endpoint/clientの製品実装は実baseに存在しない。既存`InitialGrant`と`issue_initial_recording_right`は単一部品として再利用できるが、`InitialGrantScope`はProtocolだけで実DBadapterがない。開始全体をT1/T2計算核の完成待ちにしない一方、transportを通っただけの入力を開始可能・権利保持・計算Readyとは判定しない。

## 2. 今回提案する1ステップ

最初の小単位は開始要求のtransport DTOだけとする。物理未受理のDBを仮設して成功を返すadapterや、常に拒否するだけの製品endpointを作らない。実scope/実DBadapterに必要な有限の追加集合は[research](research.md)へ具体化し、rootが物理契約/所有を確定した後に同じ親step3の次小単位へ進める。

| パス | 次の製品委任で許す変更 |
| --- | --- |
| backend/src/pitchlog/api/schemas/game_start.py | 新設。`GameStartRequest`と両側の`StartLineupInput`を既存`BaseSchema`/`EntityId`で定義する。HTTP/router登録・service・DB呼出しはしない |
| backend/tests/test_game_preparing_components.py | 既存試験へtransport正負例を追加。既存作成/read試験を保持し、新testpathを作らない |
| 本feature research.md | 版・結果・失敗・後続接合の記録だけ |

共有metadata/認可/正本、既存U-G1/U-R1/U-M2/U-F8のsource、台帳package/Protocol、plan自体、他worktreeは製品委任の編集対象外。現在の起案は本plan/researchの2pathだけ。

### 要求DTOの閉集合（新規提案、レビュー/PO委任後に採用）

`GameStartRequest`は`start_request_id: EntityId`、`device_id: EntityId`、`device_credential: SecretStr`、`away: tuple[StartLineupInput, ...]`、`home: tuple[StartLineupInput, ...]`のexact5field。資格は非空・repr/検証エラーに原値を含めない。ゲームIDは後続のURL側で受け、tenant/game/status/started_at/D4/D3/V12/復旧世代/予約attempt/名前/背番号/任意extraをbodyへ加えない。UUIDは既存型と同じ解析契約に従い、端末ID自体を資格証明にはしない。

各要素は`player_id: EntityId`、`batting_order: StrictInt | None`、`fielding_position: JsonValue`のexact3field。打順は非nullなら1〜9、両側配列の外形は9又は10枠。fielding_positionは既存U-M2の保存/復元DTOと同じJSON表現を保持する。このDTOでは守備値の業務集合・重複・DH整合・現役/在籍・背番号・権利を検証済みとしない。守備値の正式な値域/表現が未確定である事実を、任意JSONの開始許可へ読み替えない。後続開始serviceにはサーバー保存snapshotの`dh`と名簿に対する単一の確定検証が必須であり、未提供中は開始呼出部を接続しない。

DTOの返却を開始成功receiptとして使わない。成功時の内部値は既存`InitialGrant`を再利用し、D4/V12/復旧世代の新しいwire表現や成功応答DTOをこの小単位で定めない。後続の実commit確認より前にV12を応答へ出さない。

## 3. 実装ステップ（親の改番ではない）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 開始入力transport DTOと既存component正負例を追加 | exact5/3field、UUID、9/10外形、StrictInt/null、SecretStrの非露出、extra/サーバー所有値の拒否が緑。既存作成/read試験不変、HTTP/DB/権利/状態計算の実提供を主張しない |

独立限定計画レビューとrootのPO委任承認後、指示されたこの1ステップだけを実装・検査・単一ステップcommitして停止する。現時点はsource編集禁止。

## 4. 影響する正本・core・検査

本DTOのtransport先行だけは正本反映なし。既存`api/*`と`test_game_preparing*.py`でtenant-isolationのcore捕捉を確認する。記録権判定・同期動作・DBadapterをこの2pathへ紛れ込ませない。後続の実adapter等は別の具体scope/必要な領域登録を先行宣言→別JSONで確定し、本単位の承認を流用しない。

対象component pytest、backend Ruff/ty、root Ruff/ty・docs/局所plan-sync・diff checkを行う。DB起動/全backend/census反復は本transport単位には不要。入力型の正例は開始成功証拠ではなく、現実の端末資格やD4を試験stubへ置換したことにもならない。新鍵・運用秘密を発行せず、`.env`/共有DB/P6/封印へ触れない。

後続の側列/資格/再交付/epochの構造的変更はdata-model等の具体節とハーネス7.6/7.3をrootが判定し、認可/凍結の実差分と7.7はroot唯一writerが直列受理する。現在の未受理値を成功へ変えない。

## 5. 到達点と時間見込み

この最初のコード小単位は楽観30〜45分、通常1〜2時間（対象検査/commit込み）。実DBadapterは物理契約と所有固定後、楽観3〜4時間・通常6〜10時間を見込む。開始HTTP/UI/実browserはその後の別小単位で、T1計算は開始準備/初期権adapterの着手条件にしない。守備値・側列・端末資格・暗号鍵の実供給/登録の確定時間は現時点で算定しない。

製品開始・初期名簿・初期記録権・同一transaction・1球保存は未完成。全復元/全設備喪失proof完成も本transportの前提には加えない。準備中作成の実画面成功を、開始・MVP完成へ拡張しない。


## 計画レビューとPO委任判断

2026-10-24T01:11:08.323361+00:00、Codex主担当/rootは今回PO4/5/8/10の委任により、対象2b6c694743765ba43dfb926ee68a2fce091eb755（plan0a6db0e81f83c85583d9c19b272e051f931f4d1f65befddb4940916ef5fa55ba/research7085e4be6ed16725070e51618287a4a19652ab73dba5f183824a0de3d4f9f158、標準diff f3473cba203d8d84c74518c81169065f654c3a0795e213a1a5603b85fbcc3ab7）を承認する。新案作成に非関与のresolver_ledger_plan_reviewによる初回全文0/0/0と実4b2/UG1親計画/既存型/core捕捉を照合した。exact5/3fieldのtransport入力境界・既存component正負例のステップ1/1だけを指示し、HTTP/権利/DB/新資格・鍵発行/状態計算へ拡張しない。資格の非露出はSecretStr単独とせず、他fieldが不正な場合のerrors()/json()/strも局所検証する。これは既DoDの具体例であり新しい意味仕様ではない。旧U-G1/U-R1/U-F8の承認・ステップ/レビュー系列、実保存/開始の全条件を保持する。起案時の製品編集禁止は本対象版の限定ステップにだけ解除し、本人の実値確認/逐行確認/署名を代記しない。

### step1の非露出保証の適用境界（P1採用・PO委任による技術是正）

7469e676の非作者レビューP1=1を採用し、非露出は公開Classの`model_validate`/`model_validate_json`・通常代入と、既存共通HTTP handlerによる利用者向け応答/ログへ限定する。生TypeAdapter/SchemaValidatorのJSON構文例外、RequestValidationError.bodyなど内部入力が無害化済みとは保証しない。将来のendpointも共通handlerを維持し、body/生parser例外を記録せず、実HTTP応答/ログの非露出を検査する。private Pydantic APIの差替えや入力拒否の黙殺を行わない。rootが2026-10-24のPO委任でこの技術境界と同step1/1是正を指示した。新DBadapter/物理/正本はこの是正の製品scope外であり、全計画・旧レビュー系列を再設定しない。


## 6. 次小単位の物理接合候補（未承認・2026-10-24）

この節は次の限定実装を開始するための追補候補であり、上の承認済みtransportステップ1/1・親U-G1の8ステップ・U-R1の9ステップを改番しない。既DTOの145成功/独立P1是正後0を保持する。rootの採否・新単位の計画承認と必要な正本/具体資産ゲート前は製品を編集しない。次の単位名を`mvp-initial-grant-db-scope`とし、rootが別branch/planで有限scopeを引き受けることを提案する。本branchへ台帳/RG1/開始全体を一括mergeしない。

### 6.1 採用を求める実行境界

**一つのinitial issuer brokerが開始の業務transaction全体を所有する。** appは実HTTP認証・C2を行った後に閉じた開始要求だけを渡し、game/世代/配達の行ロックを保持してbrokerを待たない。brokerはroot管理のUnix socketでapp UID20003をSO_PEERCRED照合し、自身は既Ledger client UID20002で稼働する。Ledgerの許可UIDをappへ拡張しない。appの`TenantContext`をJSON化して真正な文脈として使わず、broker内で提示Cookieを既`TokenPresentation`/`verify_tenant_id`/認証関数へ渡し、tenantを再導出する。body/環境変数/peer UIDだけからtenantを作らない。認証の再実装・新署名鍵の発行はしない。

業務DBの新主体は`pitchlog_initial_actor`（LOGIN/NOINHERIT/NOSUPERUSER/NOBYPASSRLS/NO*ROLE/DB/REPLICATION、membership0）と`pitchlog_initial_fn_owner`（NOLOGIN/NOBYPASSRLS、membership0）のexact2 role。actorの接続設定・旧鍵を含む既V12Boxはroot保護配置から注入する。DSN/資格/鍵をRPCや公開factoryの引数にしない。appにはactorへのmembership、SET ROLE、初期権関数EXECUTE、秘密列SELECT/直接DMLを与えない。現在のappの`recording_generations`直接INSERTを剥奪し、後続の通常/緊急引き継ぎも同じowner境界の別操作として供給する。既存read/updateの必要権は列ごとに据え置き、無関係なACLを縮退/拡張しない。

既`create_database_engine()`はsession_user/current_user=`pitchlog_app`に固定されているので、引数や期待roleを広げない。brokerのactor接続は別の私有生成入口にし、実role属性/membership/transport/DB identityを検査する。既`_TenantTransaction`の共通operation検証・結果実体化を再利用する私有factoryを追加し、actor状態で許すtoken/functionの有限集合を別に固定する。公開`tenant_transaction_scope`、Session非公開、scope失効、同一tenantの一度限り束縛は保持し、汎用Session/任意engine/任意SQLを新たに渡す実行器を作らない。新規秘密表/世代挿入は固定関数だけとし、後続U-M2/開始操作は既tokenの必要列に限る別のactor権限と同じハンドルのexact登録へ結ぶ。U-M2の既存検証/ロック/保存をコピーせず、必要な既tokenの実行だけを同じtransactionへ参加させる。

appのgameロック中に別sessionがpermitのgame FKを書く案は採らない。brokerの短いintent transactionを**開始業務transactionより前に完了**させ、両方を一つのbrokerが所有する。業務commit/rollbackをbroker自身が観測し、appからの「commitした」というboolやcaller指定D4/digestを受理しない。V12の原文は既単一発行器からだけ作り、business commit成功確認後の同一端末向け応答へだけ返す。

### 6.2 有限な保存集合

新表は以下の4表だけとする。全表にtenant付きPK/FK、FORCE RLS、物理削除禁止のlifecycle/immutabilityを宣言する。表のactor直接DML/SELECTは0、ownerだけが固定関数を通して操作する`function_only`資源として分類する。RLSのtenant GUC一致は文脈整合であって認証証拠ではない。認証済みtenantの導出は6.1に残す。

| 表/既存列 | 固定する最小列と制約 |
| --- | --- |
| `trusted_devices` | PK `(tenant_id,device_id)`、32byte `credential_digest`、`created_at`、nullable `revoked_at`。tenant FK。資格原文/Cookie/V12は保存しない。再ログイン時も有効資格と新しいチームCookieの双方を検証する |
| `game_start_requests` | PK `(tenant_id,game_id,start_request_id)`、`device_id`、32byte `request_digest`、`created_at`。game/deviceへtenant付きFK。同じ要求IDのdevice/payload変更は拒否。digestは開始要求のserver側正規化にだけ用い、D5内容やT1のcanonical event契約を変更しない |
| `game_start_attempts` | PK `(tenant_id,attempt_id)`、game/request/deviceのowner列、`created_at`、nullable `resolved_at`、`outcome`（`pending/committed/rolled_back`）。同一requestへのFK、同一requestのpendingはpartial unique1件。予約前に耐久commit。未解決を期限だけでrolled_backへ変更しない。claim不明はpendingのまま止める |
| `recording_right_deliveries` | PK `(tenant_id,game_id,generation)`、`start_request_id`、`device_id`、`key_id`、12byte `nonce`、48byte `ciphertext`、`created_at`、nullable `revoked_at`。generation/request/deviceへtenant付きFK。同一request unique1件。原V12/鍵は保存しない。暗号長は既V12Boxのraw32byte＋AESGCM tag16byteの現物に一致させる |
| `recording_generations` | nullable `proof_digest BYTEA`（非null時32byte）とnullable `recovery_generation BIGINT`（非null時正のbigint）を追加。新normal発行は両方必須、holder_deviceはcanonical UUID文字列、D3/prefix0、試合内最初のissuance_order=1。既存行へ仮digest/epoch/holderを補完しない。旧NULL行は初期権の再交付/検証では閉じる。migration行と旧データの意味を自動変更しない |
| `rg1_restore_gate` | nullable正bigint `recovery_generation`を追加。NULL/欠損/外部epoch不一致は閉じる。新規closed seedに1を推測代入せず、実fresh attestationから既root controllerが設定する閉じた操作を別のroot所有RG1差分で供給する |

`game_lineups.side`/`(tenant_id,game_id,side)`uniqueと対応する側teamの検証は開始service単位に残す。側の曖昧な既存紅白戦行を自動割当しない。scope単位の保存検査に側移行や守備値の意味決定を混入させず、側/単一名簿検証なしの開始成功を提供しない。

### 6.3 InitialGrantScope実装のexact対応

既`issue_initial_recording_right`/`V12Box`/`DurableLedger`を単一実装として使う。新scopeは私有factoryからのみ生成され、tenant/game/request/attemptをその生成時に固定し、各methodで実生存scopeと一致を再照合する。後からcallerのtenant/scalarで再束縛しない。9methodの対応は以下に閉じる。

| 既method | 実行する固定処理 |
| --- | --- |
| `assert_bound_tenant` | actor実scopeの登録状態/tenant発行証跡と固定tenantの一致。失効/偽/派生ハンドルを拒否 |
| `lock_valid_device` | owner関数`lock_device`でtenant/device1行をFOR SHAREし、digest/失効状態をprivate戻り値にする。adapterが`hmac.compare_digest`で提示資格digestを照合し、成功後にだけ同scopeの`resolve_start_attempt`へ固定tenant/game/request/attemptを渡してrequest→attemptを排他lockする。固定`StartOwner`のowner束縛・戻り値・行の存在・outcomeを照合し、欠損/不一致/許可外を閉じる。`pending`だけ新規経路、`committed`は後続`existing_start`で同一現権利を確認する再交付経路とし、その行がなければ閉じる。device共有lockとrequest/attempt排他は同じbusiness Sessionのcommit/rollbackまで保持する。資格原文をSQL bindへ渡さない |
| `existing_start` | game/request/deliveryと現normal generation1行をtenant付きjoin、未失効/現holder/同epochを確認して既`InitialGrantRecord`を返す。別tenantは不在と同じ外形。原V12はSQLに現れない |
| `precheck_open_and_game` | 同じscopeで既RG1非ロック読取とgame存在/stateを固定読取。新規はpreparing、再交付は同一確定要求かつ現権利を必要とし、全statusを開始可能へ広げない |
| `lock_preparing_game` | game1行をFOR UPDATE、preparing再照合。後続start serviceとの接合時には、この取得直後かつgeneration取得前に、brokerに固定した開始payloadを消費する私有`_initialize_start_before_generation`から両team→players→U-M2の有限な同一scope操作を呼ぶ。任意callbackをconstructor/RPCで注入せず、既単一発行器に第2発行経路を作らない。別session commitは受理しない |
| `lock_current_start` | game→現generation→deliveryを固定順でロックし、request/device/失効/epoch/所有を全再照合。世代の新旧をD4大小で推測しない |
| `assert_recovery_generation` | 同一scopeのRG1 singleton epochを固定read、正bigint/外部fence値とのexact一致。NULL/旧値/不明を拒否 |
| `insert_initial_grant` | 単一発行器が実reserve→claimした記録だけをbroker内部で受け、固定owner関数でgeneration＋delivery＋attempt committedを同一transactionにINSERT/更新。app/任意RPC入力のD4/digest/envelopeは入口で拒否。game/request/attempt/ownerと既世代0件を再照合し、unique競合は全取消 |
| `assert_open_before_commit` | 既RG1固定関数のFOR SHARE NOWAITを同じscopeで呼び、外部同channel fence/actual business bindingとともにcommit/rollback結果確認まで保持 |

この表に加え、予約前のintent作成/実結果解決の固定2操作だけを追加する。intent開始は実有効device/自tenantのgame/requestを照合し、同じpendingを再利用する。commit済みbusiness rowがあれば既delivery再交付へ進み、rollback確認済みなら旧D4を再使用せず新attemptを耐久化できる。不明時はpendingを保持し、次attemptを自動発行しない。broker消失後の解決はDB primaryの排他照会で旧transaction終了と該当成功行不在を確認し、同じownerの外部実予約/claim状態と照合できる場合だけ行う。台帳不明や旧business identityでは停止を維持する。

新固定関数は`initial_right_api`内の下記**exact9件**とする。`assert_bound_tenant`はPythonのみ、`assert_open_before_commit`は既RG1関数を再利用するため、新SQLを増やさない。関数ownerは固定search_path、完全スキーマ修飾、PUBLIC EXECUTE剥奪、actorだけEXECUTE、実`session_user`/tenant一致、既存FORCE RLSを要求する。未使用関数や任意SQL/JSON実行関数を付け足さない。


固定SQL署名候補は以下。tenant引数はbrokerで再導出したscopeだけが注入し、game/request/device/attemptは私有scope構築時のowner tupleへ固定する。`StartRecordRow`はtenant/game/request/device UUID4列、generation/epoch bigint2列、proof_digest bytea、key_id text、nonce/ciphertext byteaのexact10列。資格digest/envelopeをappの汎用readへ返さない。

| 関数（schemaは全て`initial_right_api`） | 戻り値/lockと列権限 |
| --- | --- |
| `lock_device(uuid,uuid)` | `TABLE(credential_digest bytea,revoked_at timestamptz)`、最大1行、device FOR SHARE。owner SELECT全4識別/資格列＋`UPDATE(device_id)`を行lockのためだけに付与。本文DML0 |
| `read_existing_start(uuid,uuid,uuid)` | `StartRecordRow`最大1行、現在のgeneration/delivery/request join、非lock。ownerの必要SELECTだけ |
| `read_start_game(uuid,uuid)` | `TABLE(status text)`最大1行、非lock。adapterが既RG1PrecheckTokenを先に実行し、新規/同一再交付の状態を判定 |
| `lock_preparing_game(uuid,uuid)` | boolean、game FOR UPDATE/preparing、owner SELECT識別/state＋`UPDATE(status)`（行lockに必要、本文UPDATE0） |
| `lock_current_start(uuid,uuid,uuid)` | `StartRecordRow`最大1行、game→generation→deliveryを明示個別SELECTでlock。必要SELECTと識別列UPDATEを各表へ限定。JOIN一括lockによる順序の未定義化を避ける |
| `check_business_epoch(uuid,bigint)` | boolean、singleton1の現epoch一致/NULL拒否、非lock。ownerはsingleton/epoch SELECTだけ。RG1 state更新権0 |
| `insert_initial_grant(uuid,uuid,uuid,uuid,uuid,bigint,bigint,bytea,text,bytea,bytea)` | boolean、引数順tenant/game/request/device/attempt/D4/epoch/digest/key_id/nonce/ciphertext。既lockの所有/現世代不在/owner tuple/attempt pendingを再確認し、generation＋delivery INSERT、attempt成功markだけ。ownerの新規行INSERTとattempt状態列UPDATE。D3/prefix0・issuance_order1はSQL定数でcaller引数にしない |
| `begin_start_attempt(uuid,uuid,uuid,uuid,bytea,uuid)` | `TABLE(attempt_id uuid,outcome text)`最大1行。tenant/game/request/device/request_digest/server_attemptを束縛。同request行→pending attemptをlockし、新規intent又は既pendingを返す。before-business専用の短いtransactionでのみ呼ぶ |
| `resolve_start_attempt(uuid,uuid,uuid,uuid)` | `TABLE(outcome text,generation bigint)`最大1行。固定tenant/game/request/attemptのrequest→attemptを排他lockして、owner束縛・outcome・成功行の有無を実readする。業務scopeでは`lock_valid_device`が実device資格を照合した直後、issuerのreserve/claimより前に呼び、同じSessionのcommit/rollbackまでlockを保持する。`pending`だけ新規経路、`committed`は同一現権利の再交付確認へ進み、欠損/owner不一致/戻り値不正/他outcomeは閉じる。短いintent取引のlockが継続すると扱わない。broker消失後の結果照会も同じ排他で旧業務transactionの終結を待つが、欠損を即rolled_backへ更新する口は作らない。再試行の許可はbrokerが外部同ownerの実状態も照合できた後の別の限定制御差分で行う。それまではpendingを残し新attemptへ進まない |

最初のscope単位では`outcome=rolled_back`は予約済みだが、brokerが同じprocessで業務rollbackの確定を観測した場合の限定後処理を次差分へ残す。未解決pendingの自動解消や期限切れによる新attempt採番は実装しない。これは既MVPの再試行を削除する意味ではなく、source/未知故障の段階供給を明示するもので、通常再試行と再起動後解決のpositive gateは開始接合前に必須として残す。

### 6.4 全順とRG1の必要な最小接合

通常新規は「broker認証再検証→外部epoch共有fence→短いintentの耐久commit→業務scopeのdevice共有lock→要求/attempt lock→既単一発行器のreserve/claim→game FOR UPDATE→両team UUID昇順→対象players UUID昇順→U-M2→現generation→delivery→RG1 FOR SHARE NOWAIT→同じbusiness commit/rollback確認」とする。単一発行器はdevice lockを保持してreserve/claimする実装なので、旧未受理annexの『全業務行lock無しで予約』を成立済みと記録しない。gameロック前の有限timeout内の外部呼出しを維持し、game→generationとU-M2 team→playerの採用済み順を守る。現在の単一発行器にはteam/player処理がないため、その呼出位置は後続start service差分で明示的に接合し、grantだけの成功を開始成功へ読み替えない。

資格失効はdevice行だけをUPDATEし、そのままgameを待たない。intentの短いtransactionは業務scope開始前に終了し、scopeを持ったまま別sessionでFK先gameや同じ要求を更新しない。復元制御はRG1閉鎖だけを先行commitし、外部epoch排他を待つtransactionでgame/世代を取らない。認可/RG1/epoch/資格/現世代は最終ロック下で再照合し、外部fenceと制限scopeをcommit後まで保持する。

RG1候補`5ee75156`の`scope_binding` EXECUTEとcontroller borrowは現在app role/UID20003だけである。broker actorを別sessionでappに偽装しない。現在進行するapp/control2+observer2の正式RG1登録をこのbroker完成待ちへ戻さない。その次のroot所有RG1限定差分として、旧 `(UID20003,pitchlog_app)` を保持し、新 `(UID20002,pitchlog_initial_actor)` のexact1組だけを`scope_binding`・controller peer・実backendのrole/DB/PID照合へ登録する。任意UID/actor追加やboolによるlease証明にしない。controller設定/identity mismatch、別role同UID、別UID同role、失効backendの負例が必要。actorが借用できてもfresh/非0復旧解除が完成したとは扱わない。

このactor exact1組と実epoch/bindingのroot所有固定候補供給は、(c)の正常grant/再交付/競合を実接合で検査する**前**に行う。現app RG1正式登録の先行独立性を維持し、その後の限定供給とする。(c)の型/DDL/単体/拒否の実装はこの供給待ちで止めず、正常系のDoDも削らない。未供給なら正常実接合だけを未実施と明記し、app偽装/常成功RG1/権利stubで埋めない。(d)に残すのはbroker実RPC・実Cookie/認証再検証を含む全経路であり、必要なactor RG1供給を(d)まで後置しない。

### 6.5 編集scope・受入と実行順

次単位の候補製品pathは`backend/src/pitchlog/repositories/initial_recording_right.py`（9method adapter/固定token）、`backend/src/pitchlog/recording_rights/initial_grant_broker.py`（私有actor engine/閉RPC/単一発行器の呼出しとcommit所有）、既`repositories/transaction.py`（私有限定factory/実状態のtoken集合のみ）、既`db/recording_rights/models.py`、新`backend/migrations/versions/0035_initial_recording_right_storage.py`、既`backend/tests/test_game_preparing_components.py`、新`backend/tests/db/test_initial_recording_right_scope.py`/`initial_recording_right_scope_support.py`とする。migration番号は現在実baseのhead0034を次単位作成時に再照合し、他担当の番号を上書きしない。

root所有の有限共有集合は`data-model.md`/`docs/README.md`の表/role/epoch最小確定、既authz productのclassification/capability/ddl/exposure/application-steps、既repository/function operation登録とtenant_boundaryの実影響資産、core先行宣言/別JSON登録とpolicy実PR1件。関数SQLは既product認可資産の生成経路へ置き、新規の未登録SQL資産をruntime検査から免除しない。上のRG1 controller/SQL/manifest接合は既root所有featureへ個別供給し、共有ファイルのwriterはroot一人。列/主体/関数のexact差分と必要7.7はsource由来で別に受理する。静的件数だけで任意DB APIや新接続を許可しない。


**最初の製品実装小単位(c)の型と検査。** `InitialRecordingRightScope`は既`InitialGrantScope`を構造的に満たすfinal classとし、公開constructorでSession/DSN/tenantを受けない。私有`_initial_recording_right_scope(context, owner, actor_runtime)`は実登録されたactor runtime/有効TenantContext/凍結`StartOwner(tenant_id,game_id,start_request_id,device_id,attempt_id)`だけを受け、終了時永久失効する。`StartOwner`はprivate型で、JSON/HTTP/外部receiptの証明にはしない。exact9関数のtokenは各1 class（同じ関数への任意引数/statement生成口なし）。既`InitialGrantRecord`/`ProofEnvelope`/例外を再利用し、別のV12/世代DTOや生成アルゴリズムを作らない。

(c)の実DB testはowned business/台帳primary/standby3系、実source/peer client、実限定actorで行う。既公開test-vectorのcredential/AEAD keyはfixture準備でのみ注入し、実暗号/実資格比較/実DB関数を通す。初期device行はfixture投入であることを証拠に記録し、この局所成功をenrollment/画面開始の成功としない。正例は9methodの署名一致、実reserve/claim→D3/prefix0/issuer1/暗号再交付、同requestの同V12/追加予約0、全commit・全rollbackを含む。負例はappから9関数EXECUTE/4秘密表読取DML/generation直接INSERT、actorの直接DML/membership/別tenant、失効/別端末/変更payload/偽scope/失効scope、generation/delivery片側INSERT故障、RG1両順序、外部lease喪失を含める。actor transport前のfixture runtimeと、後続実broker/APIの成功を明確に別記する。

実装へ進める順は、(a) rootの本候補採否・専用単位plan/必要最小7.3、(b) core新pathの先行宣言→別JSON確定、(c) 4表/既存epoch列/actor限定固定関数と9method実scopeの隔離検証、(d) broker実RPC/実Cookie・認証再検証の全経路を接合、(e) 正式asset照合/独立coreレビュー/全件必須検査とする。(c)の型/DDL/単体/拒否を先行し、正常実接合前に6.4のactor RG1固定供給を受けてから正常grant/再交付/競合も検査する。各実装委任は一単位で止める。T1/P6/P7/実Port/HTTP/全非0復旧完成を(a)〜(c)の着手条件に追加しない。broker transport供給前の実actor DB scope局所成功と、(d)の実broker正常経路を分けて記録する。

(c)の実DB証拠は実外部台帳reserve/claim＋実V12Box＋実actor関数で、別tenant/無効資格/偽scope/直接app INSERT拒否、同一requestの同V12再交付、別request/device/payload拒否、rollback後D4非再利用、claim不明停止、commit失敗の全取消、credential失効との直列化、RG1事前/直前両競合、外部fence喪失を含む。(d)は実Cookie再検証/peer/role/binding/切断/応答不明を追加し、app/actorへ常成功RG1や権利stubを渡さない。公開済み既test-vectorだけを隔離暗号試験に用い、新規の運用秘密/署名鍵の生成や共有DB適用を行わない。

(c)の要求lock検査では、`lock_device`成功→資格digest真照合→同Sessionの`resolve_start_attempt`→issuerのreserve/claimという順と、commit/rollbackまでのrequest/attempt排他を実照合する。無効資格ではresolver/予約へ進まず、owner差替え/欠損/不正戻り値/許可外outcomeも閉じる。同requestの並行2要求はrequest→attemptで直列化し、先行commit後の`committed`は同じ現V12を再交付して追加予約0、先行結果不明ならpendingを勝手に解消せず新attemptを発行しない。短intentのcommit後にもlockが残るとみなす負例、別Sessionで結果照会してlock保持を代用する負例を含める。


**端末enrollmentの次の有限技術案。** 既UR1の採用済み「有効なチームCookie＋サーバーが検証する同じ端末資格」を保ち、個人account/追加役割を作らない。brokerの閉`enroll_device`操作が既Cookieを再検証後にdevice UUIDと256bit資格を発行し、owner限定登録関数へSHA-256 digestだけ保存する。クライアントは返却pairを端末内へ耐久保存できるまで開始を送らない。応答消失時にdigestから原資格を再生成せず、まだholderでない新端末の再enrollmentとして扱う。既holderの紛失/失効は通常/緊急引き継ぎの明示経路を必要とする。再ログインは既pair＋新Cookieを使い、Cookieだけで保持端末としない。資格失効はdevice1行のUPDATEで直列化しgameを待たない。コードと公開vectorによる隔離検査を先行できるが、今回(c)の9関数へenrollment/revoke関数や公開routeを混入させず、次の有限差分で個別供給する。運用秘密/署名鍵を新たに発行したとは記録せず、実運用発行は既承認境界を維持する。

**依存の区別。** 4表/DTO/固定scope/owner分離/ロック/再送停止は既意味＋PO技術委任で確定できる。守備値/9-DH10の単一名簿検証と側列は既資料との照合・必要な正本確定を後続start serviceの前に完了する。新しい野球結果の意味判断は本物理単位では0件。鍵保管先・運用鍵の新発行・運用配置/共有DB適用は委任外として実行直前に判断資料へ集約し、コード/隔離検証を止める条件へ拡大しない。実grant scopeだけでは製品開始・1球保存・MVPを完成としない。

### §6限定計画の初回2P1採用・反映候補

固定`bc8fdf39dba4415ac368c3a03e4dabfa86769eaf`の非作者rightsによる限定初回はP0=0/P1=2/P2=0（plan SHAe821ea55b6e9fca8dc72bf97275c4a6e3cd04fd7d6f8a9587c483b676166d4e4、research SHA808e5d75d521c3bccc318cfa0f6fd069816cbb442ab364504fe08cc1782bb01c、標準diffcb13c1cf54a06008cb11b157bb6d94e86525fe5a283bd0b056cf294ad9f69fd7、証拠f8527c11a24fa629312e3eecd91c6052c1c23d7e4b6dfa890f547534468847f9）。rootはPO委任の実装順/既契約具体化判断でSTART-SCOPE-PLAN-01/02を全採用し、(c)正常系前のactor RG1固定供給と、`lock_valid_device`内の同Session request/attempt排他を反映指示した。4表/2role/9固定関数/9methodと(c)の正常・負例DoD、旧transport/親全計画・未達は維持する。

本反映は主担当の明示指示によりrightsが作者としてplan/research2pathだけを編集した候補であり、上記初回の非作者資格をこの反映後へ流用しない。rootが別の非作成者へ反映差分と影響を渡し、独立再確認と対象版判断を受けるまで新§6を承認済み/実装開始済みとは記録しない。初回否決/2P1/旧レビュー通算を保持し、人間本人の確認/署名を代記しない。


2026-10-24T02:55:16.478688+00:00、PO委任によるCodex主担当/root判断として次物理接合§6を承認する。対象c6ebdd2b0b36966131ede76ff32b9aa3eac1090c、plan62b46d084491aa22417cdc24e9973a6f8960a558d9313c2dfd645afdef946ac4/research24491067bfd52a63b7bf1ae2cca5007ac381f8b455e1040143e832b0848a3192。初回bc8fdf39のP1=2を全採用し、rightsによる限定反映（この反映では作者）を、新しい非作者initial_scope_plan_reviewが第2回相当0/0/0で照合した。証拠62de47cbb58341044425923c9890395363f003972487f1087e592070dc815177。旧否決/2指摘/反映1回/各親レビュー通算を保持し、反映作者を独立判定者へ数えない。4表/2role/9固定関数/9method/同一業務commitと、actor RG1固定供給を正常実接合前に分離する順を採用する。bytes入力/nullable結果も既共通function executorへの有限な型具体化としてsource前にexact宣言する。次専用単位でcore先行登録と指定source/実DBscope検査へ進み、本transport branchへ全sourceを一括輸入しない。実broker/enrollment/開始/1球・親全MVP義務の未達、運用秘密/共有DBの委任外境界を保持する。本人の実値確認/署名を代記しない。


## 7. 同一TX開始供給への有限追補（2026-10-26 JST）

元6065063bの計画・transport1/1・§6のレビュー履歴を保持し、実初期grant12DBの固定候補を再利用する。既単位の完了を開始成功へ拡張しない。今回の根拠はPO委任と操作単位で供給する最新指示、作者反映1 plan ed8b506f9eba5dfad8b9af473e8b6b659a6663c8a995d68c54ca999731be5e7c、非作者review90d28e6a7130bfb8d6f4723b329389ceb18282e2b6c85097168270d125a28528。実UI defaultはgame_other R9/extensionLimit9/DHtrue、両team公式10人ずつである。9人/DHfalseも既有効設定として保持する。

初回同TX sourceの設計P1はreadで対象選手を特定する引数不足だった。rootは2026-10-25T15:28:03Z、PO委任によるCodex判断としてsignature-delta SHA0ccc5d56b861d13a23720106d9311f34869529a0dfe075f02d11d8253da203bcを採用。read_initial_start_context/persist_initial_startの両方を(tenant uuid,game uuid,request uuid,attempt uuid,request_digest bytea,typed_payload_json text)へ揃え、同じserver canonical凍結payloadをowner/保存request digestへ再照合する。tenantはscope注入、全対象IDsをexact抽出、game→team UUID順→player UUID順のlock、最大20名。全roster先頭20件やcallerのdigestを権限証明にしない。

### 最初に実装するsource小単位：開始payloadの閉型とcanonical化

編集するのは backend/src/pitchlog/repositories/game_start.py（新設）と backend/tests/test_initial_game_start_components.py（新設）の2pathだけ。初期scope12DBの567入力をhash再照合した隔離WT verify-game-start-atomic-4f2f2185 を利用する（receipt3af62085603dfe9b247aaadae51a2092546e69ac9e6f2dac8e53a430b37f2024）。元fixed WTは変更しない。

既GameStartRequestとT1の閉fielding role表現を再利用し、公式UUID・StrictInt/null打順・fielding(position1..9)/designated-hitter・両side凍結tupleのtransport閉型を具体化する。全nested入力を不変にし、同payload/同canonical bytes/digestと、ownerのtenant/game/request/device/credential digestを結合する型・canonical化部品を供給する。資格原文をrepr/検証エラー/canonical payload/logへ入れず、既資格照合責務を複製しない。caller supplied digestやJSON shapeだけで真正性/認可成功としない。

9/10の外形/閉表現までのtransport検査とし、DH/打順重複/守備網羅/初期状態の野球計算をPythonに実装しない。これらは単一TS artifactの次供給、所属/背番号/権限/lockは実DB側の別責務。新部品は開始成功・V12・D4・同TX保存を返さず、現grant-only committedを開始済みとしない。

正負型/extra/欠損/数値coercion/入れ子変更/UUID/非canonical表現、同payloadの再現bytes、payloadやowner/device等変更時の異なるdigest、資格非露出を検査する。実開始/初期roster受理/DBをfixture成功へ読み替えない。作者はこの2pathで止め、別非作者レビュー後にrootが接合する。Git/index/正式JSON/共有台帳はroot所有。

後続同TX sourceのbroker/read-save固定2operation/限定UM2/SQL/ACL/再送/全取消と単一TS名簿検証は既反映案の次有限範囲として残す。初期resolver・結果不明回収・実Cookie/enroll/RPC/API/UIも実1球保存前に必要だが、この閉型部品や既796数学核の開始前条件へ戻さない。全MVP義務を維持する。

2026-10-26 JST、rootは上記2pathを既承認開始設計の型/保存境界具体化としてPO委任により承認。本人の実値確認・署名の代記ではない。未登録SQL/任意engine/Session/callback/常成功ゲートを導入せず、今回sourceはDB接続0とする。

2026-10-26 JST、§7のread署名欠落P1反映を伴う限定計画レビュー1周をfrontmatterへ追記し、旧transport/§6本文の系列は保持する。閉payload作者の初回0e8c4738/48成功と低水準改変P2を保全。未知roleをDHへfallbackする経路を明示拒否し、nested tuple/entry/UUID/order/role/ownerの閉値再検証へ是正した反映1はhandoff1fb608a97c4f9aecf66dae552f941d9a5fcb93f88f09866c2c0e484b1504eb91、非作者最終evidence210db794faeb4a5a0cb4c74e3e611323659f7105ca0f81f8eb00b5215d64c25e/reviewecac5319a13a7839039a4a4e3d9b6580f152fbe81a121e048c845ae53e245ab2は0/0/0。独立68成功0.60s・旧48test AST/正常9,10人canonical bytesとowner同一・旧破損反例拒否を確認。rootはsource02eec45bfd4587eda46a7f9fe1fad505d5d39a122ebe9497c3ad429da0f7ef6f/testabb54b0f41040b21e317be273063df4e8fa4338fa41e06db0c56f94e3e7b10acをPO委任で受理。既DTOは606実blobの無変更seed da5662d213357b5de4770fe9c30860847136eb86ebe8d6559b6bc5d1aaf0f07aを依存として同時保存する。参考preparing検査の旧migration文字列1失敗は既不整合として保持し、この型部品の完了に含めない。実DB0・開始成功/単一TS名簿業務検証/actor同TX/RPC/UIは未提供。
