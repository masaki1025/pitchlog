# 開始経路の限定照合（2026-10-24）

## 固定点と調査範囲

実baseは`origin/develop=4b2db6907f329c3dde113c3b7e1c3515600fb915`（PR181通常merge）。主repoの作業HEADは旧developの`1ab398cc`であり、これを最新製品と誤認せず、実baseのGit blobを参照した。正常180 supplier`95d766f5d20234b1d534538b96fc369eda1cc6f1`は実baseの祖先である。旧173/0aaa/f48を輸入しない。

U-G1は別wt固定`67dff5f707dcb2311a35140ae870b44f46e24803`、U-F8入口は別wt`eb83787ca5f9e79f94bc773f99e62d74121778cf`と実baseへ統合された外殻を照合。実画面作成の隔離供給はfirst-path候補の固定点`d2713e9ec377fe7f4e882c7be01d9f42005aefa8`と後発CSV supportだけで、正常mainへ統合されたとはしない。最新台帳/RG1/作成を本branchへ一括mergeしない。

全過去レビュー/監査を読み直さず、UG1の開始側契約・UM2呼出し・UR1単一部品・UF8入口と実baseの該当sourceだけを確認。製品/共有metadata/他作者source/DB/Git履歴の変更なし。P6/封印/.env/運用秘密へアクセスしない。

## 実供給と不足

| 項目 | 現物・場所 | 判定 |
| --- | --- | --- |
| 開始の意味と親承認 | 固定67dffの`docs/features/ug1-game-lifecycle/plan.md` §2/4 step3、同design §初期化と成功境界 | 8ステップ/2026-10-14承認/基本計画2周を保持。両側スタメン・UM2・初期権・started_at/in_progressは単一transaction、commit後のみ成功。開始側の物理/側DDL/全lock順は未受理のまま |
| 開始公開operation/endpoint | 実base`backend/src/pitchlog/api/routers/games.py:47,73`、`api/schemas/games.py:64` | preparing list/detailだけ。開始service/DTO/POST startは存在しない。first-pathの追加POSTはpreparing作成であり開始ではない |
| 初期付与単一部品 | 実base`recording_rights/initial_grant.py:48,62,84,104,116,290` | InitialGrantRecord/InitialGrant、DurableGenerationSource、RecoveryEpochFence、InitialGrantScope、issue_initial_recording_rightが供給済み。InitialGrantScope実classは0、試験内fake scopeの成功を実接合としない |
| 実耐久源とRG1候補 | `c07f508df6bdcec815e311e5a81c25feeba08610`、RG1候補`5ee75156adabdb7a43fbd1393c5b62337e6e770a` | root所有の別候補。実Unix peer/同期PG/witness/fenceは再利用でき、reserve/claimはfresh保持中にも実測済み。fresh/全復元完成を同義にせず、今回編集しない |
| 端末資格/再交付/業務epoch | 実base`db/recording_rights/models.py:187`と全db/migrationの該当識別子検索 | RecordingGenerationはD4/issuance_order/holder_device/D3等だけ。device credential、start_request、proof_digest/暗号配達、business recovery epochの保存先/API/実adapterは存在しない |
| スタメン側 | 実base`db/game_state/models.py:223`以下GameLineup | game_id/team_record_id/entries JSONのみ。side/側ごとのuniqueがなく同一team両側を識別できない。親designは側列/uniqueを7.3対象として既に留保している |
| 名簿/記憶 | 実base`repositories/lineup_memory.py:230,282`と`api/schemas/lineup_memory.py:8` | save_lineup_memoryは同一scope、self team→active players UUID順。player/order/positionを保存、当時背番号はUG1所有。fielding_positionはJsonValueであり、そのまま意味確定済みとはしない。対戦相手/紅白戦/9-DH10の全検証はUG1へ残る |
| 実RecordingRightsPort | 実base`sync/ports.py:65,134` | Protocolと空PORT_IMPLEMENTATIONSだけ。実V12照合class/登録は0。別候補`7c04c964`にはPortWriter.run_function/VerifiedDeviceContext等の契約があるが実Port classなし、正常mainへ未供給で丸ごとmergeしない |
| UI/client | 実base`frontend/src/screens/GameScreenEntryTypes.ts:40`、`GameScreenEntry.vue`、`GameScreenEntryProvider.ts` | StartCandidateはprops外殻、実providerはpreparing read。実start client/trigger/初期名簿formはない。未取得lineup/権利/状態をready/heldへ偽装しない |

## T1を待たずに作る順序と具体的な次patch

今回の1stepは[plan](plan.md)の開始要求transportのみ。名前/背番号/tenant/予約attempt/権利をbodyで受理しない。fielding_positionの既存JsonValue表現を保持しても、DTO通過を確定スタメンと認めず、後段の単一検証なしには開始を接続しない。開始の最初の製品小単位をT1状態計算の完成待ちにはしない。

次の実DBadapter単位は、以下の必要集合をrootが確定・個別所有委任してから実装する。これは未提供リストだけではなく、同一scopeで実装するための物理候補であり、現時点の正式値/既受理契約ではない。

1. **業務物理候補**: `db/recording_rights/models.py`＋新migrationに、tenant/deviceを主キーとする資格digest/失効時刻、tenant/game/start_request/device/current D4/epoch/proof digest/ProofEnvelope(key_id/nonce/ciphertext)の束縛と一意配達、外部epochとの同一値照合先を持たせる。`RecordingGeneration`のD4/issuance_order/holder/D3=0と現世代一意は維持する。端末資格の発行/失効・保護鍵供給・attemptの予約前耐久記録は閉じた実入口が必要で、任意UUID/JSONやチームCookieだけを保持端末証明へ読み替えない。V12Boxを再利用し暗号/発行アルゴリズムをコピーしない。
2. **実scope候補**: 新`repositories/initial_recording_right.py`にexact生存`_TenantTransaction`を包むInitialGrantScope実adapterと固定operationを置く。資格の同一tenant共有lock、同一要求の現権利/配達照合、preparing game FOR UPDATE、現世代→配達の固定順、業務epoch一致、2行insert、既存RG1事前/直前を閉じたtokenだけで実行する。Session/任意SQL/tenant argumentの公開はしない。外部fence→資格→game→世代→配達→RG1をcommitまで保持し、再交付も失効/現権利を実再照合する。UM2を含むチーム/選手の全順は次項と一緒に確定してからstart serviceへ接続する。
3. **開始本体候補**: `db/game_state/models.py`＋新migrationのside/`(tenant_id,game_id,side)`unique、新`repositories/game_start.py`、新`services/game_start.py`。同一scopeで両チーム/現役playersを決定順lock→当時背番号取得→保存snapshotのdhを使う単一の9/10・位置/重複検証→両側lineup保存→UM2（紅白戦は後攻1回）→単一初期権部品→status/started_at→RG1/epoch直前→commit→成功。実際のlock順はinitial部品内部の資格→game順とUM2のteam→player順を合わせて固定し、既存syncのgame→世代順を逆転しない。まだ採用されていない守備値集合やD2初期投影を独断で補完しない。
4. **実Port候補**: 新`recording_rights/port.py`＋既存`sync/ports.py`/`port_guard.py`のexact class登録、既存accepted候補のPortWriter.run_functionを必要差分だけ供給。V12 digest/現D4/現epoch/実deviceを同じwriterのreadで照合し、read_rg1/check_rg1を既存固定2関数へ委譲。外部leaseは業務commitまで保持し、偽/派生/失効writer、旧epoch、別device、revoked、原本欠損を拒否する。開始には初期付与scopeが必要で、同期全Port/T1の完成を開始DTO/adapterの一律前提にはしない。
5. **HTTP/UI候補**: 既存games routerへ`POST /games/{game_id}/start`、tenant_accessのexact operation/C2登録、正規`frontend/src/api/games.ts`と新`GameScreenStarting*.vue/Provider.ts`を接続。新ルート不要で既存record hostから名簿/要求を供給、実commit後だけ開始receiptを採用。正規Pinia/QueryClient/epoch/path/abort/Cookie失効を再利用し、未知計算状態で1球ボタンを開かない。既存read DTOはpreparing専用なのでin_progress再取得を別の閉DTOへ分け、既存readを全状態対応済みにしない。

必要な共有変更はrootへ所有を戻す。具体集合はcoreの新source/test exact登録、`contracts/authz/product/{table-classification,capability-catalog,ddl-elements,exposure-facts,application-steps}.json`の新物理subject/列権限、route-registry/http-route-matrixのstart1件、tenant_boundary base-allowlist/repository-contractと生成物、必要9/8/履歴/snapshot/policyである。無制限contracts編集を許可せず、個々の実sourceからexact行を列挙してから候補化する。新表のRLS/FORCE/ACLと資格/暗号列のアプリ直接読取拒否は実負例を要する。正式7.3/7.7の受理はrootの別ゲート。

実DB検証は正常start後のD3=0/権利/両側名簿/UM2/時刻の全確定と、scope例外の全取消、同一要求再交付、別device/越境/失効、RG1両競合、外部reserve/claim不明・消費後business rollback非再利用、旧epoch/fence喪失を含む。製品の実作成→開始operationを通し、試合/権利の手製INSERTを開始成立証拠に数えない。実HTTP/画面では実login/Cookie/C2から通し、保存snapshotを再resolver計算しない。T1計算/1球はその実source供給後の別検証。

## 見込み・未実施

調査はread-onlyでDB0。新wtは実baseから作成、編集はplan/researchだけ。最初のtransport1stepは楽観30〜45分/通常1〜2時間。実scope/物理接合は契約固定後に3〜4/6〜10時間程度、HTTP/UI/browserは別単位。全開始をT1完成待ちへ戻さず、物理未受理を既採用として隠さない。旧親/UR1正常置換/台帳/UF8各レビュー系列と未完DoDは維持する。

起案検査はdocs-status21文書/違反0、design-propagation/doc-coverage成功、新2文書の全ローカルリンク実在、diff check成功。製品/DB試験は起案範囲外なので未実行。新2文書を固定した後に局所plan-syncを実baseと比較し、独立限定レビュー/PO委任前は製品編集を停止する。

## 限定ステップ1の実装と局所検査

非作者resolver_ledger_plan_reviewの初回全文0/0/0をrootが照合し、PO委任承認`9031bab7819c4082be1de7bcdaaa62d6e38f6996`で限定1ステップを指示した。編集は新`backend/src/pitchlog/api/schemas/game_start.py`、既存`backend/tests/test_game_preparing_components.py`、本researchの3pathのみ。plan/HTTP/router/Port/DB/記録権/共有metadata/他wtは変更しない。

要求exact5/要素exact3、既存EntityId/SecretStr/StrictInt/JsonValue、両側9又は10枠とnullable打順1〜9を実装した。未知守備JSON/重複選手を保持する正例はtransportに限り、DH/位置/在籍/開始/保持権の意味許可とはしない。資格は実発行せず公開固定入力で型境界だけを検査した。

SecretStrの通常repr/JSON maskingだけでは、missing等のValidationError.inputに元request全体が残る。そのため本requestだけのwrap validatorで、元input/context/msgをコピーしない固定診断・既知field/index位置へ再構成する。未知JSONの独自errorも同じ拒否へ写し、JSON構文エラーはmodel validatorより前なので`model_validate_json`も同じ秘匿境界に通す。except外から再送出し、資格を含む原例外を__context__へも連結しない。通常代入もPydanticのvalidate_assignmentへ通し、資格fieldを生strで置換しない。共通BaseSchemaは無変更。

初回の型検査はInitErrorDetailsのinput必須/可変error typeのLiteralStringに関する3診断、試験側の意図的な異型代入に2診断。安全条件を変えず、input=None/固定診断typeと通常setattrによる動的入力試験へ是正した。pytest失敗は0。中間の新規対象54成功/1.34秒（旧87deselected）と、原例外context非保持まで含む最終対象全件**141成功/0.75秒（skip0）**を区別する。旧87件の既存関数/class定義24個は承認HEADからAST一致を確認し、期待値を変えていない。

最終backend対象Ruff format/check・ty、root Ruff/ty、docs-status21/違反0、design-propagation/doc-coverageが成功。実core_guardのload_core_areas/matched_pathsで新source/既存testの双方捕捉を確認した。局所plan-sync/diff checkはステップcommit固定後にも照合する。DB/全backend/censusは今回未実行で、前の別候補の成功を転用しない。HTTP/実Port/実開始/1球/MVP全体は未提供のまま、独立コードレビューはこれからで作者の局所成功を独立可決へ置換しない。

## 次の実DBadapterへの最小保存対応（候補・未承認）

旧physical annex（旧wt `feature-ur1-initial-rights`、SHA256 `13f1e33fd94b0fe501c0dd7f3ccb264833bcc2296bdf29dd4e8c497660b1d484`）とowner sheet（`108b3286dbcf632eea48bed1478f371d40dfff2f9627b0f966d79ec7fb526c10`）を限定照合した。両文書は当時の候補/未受理を明記しており、実base未収録のためローカル相対リンクを増やさず参照hashだけ保存する。V12 AEAD再交付・資格共有lock・同一業務scope・予約前の耐久attemptとrollback後D4非再利用は既存単一部品と整合するが、新DDLの承認を代記しない。

| InitialGrantScopeの既存メソッド | 次に必要な実保存/操作の最小対応 |
| --- | --- |
| assert_bound_tenant | exact生存_TenantTransactionと実tenant注入を確認する固定token。caller指定tenant/型だけで証明しない |
| lock_valid_device | trusted_devices候補のtenant/device/credential_digest/revoked_atを共有lockし一定時間digest比較。資格失効は同一行UPDATEだけを取り、逆順にgameを待たない |
| existing_start | request/未失効delivery/現normal generation/有効deviceをtenant/game/requestで1件照合。欠損をcommit失敗と断定せず、同端末の現権利のみ再交付対象 |
| precheck_open_and_game | 既存RG1非lock読取＋game可視性/stateの固定read。新規はpreparing、再交付は同一確定要求と分ける |
| lock_preparing_game | tenant/game主キーの実FOR UPDATE、preparingを再照合する。両側team UUID順→players UUID順→UM2の順と、既存game→generation順を含む全順は実start service前に固定 |
| lock_current_start | game→現generation→deliveryの固定lock、request/device/epoch/失効を再照合。同team両側は新side列away/homeとtenant/game/side一意で区別し、旧曖昧行を自動割当しない |
| assert_recovery_generation | RG1 singletonの業務epoch候補列と実外部fence/current epochの一致。旧NULL/欠落を1へ自動補完せず閉じる。fresh設定は実attestationからroot controlが行う候補 |
| insert_initial_grant | generation（D3/prefix0/初回issuance_order）＋delivery（owner tuple/digest/key_id/nonce/ciphertext/epoch）＋attempt成功状態を同じbusiness commitへ。原V12/鍵はDB/SQLbind/logへ保存しない |
| assert_open_before_commit | 既存RG1固定関数のFOR SHARE NOWAITと外部epoch fenceを、business commit/rollback確認まで保持 |

有限な表候補はtrusted_devices、game_start_requests、game_start_attempts、recording_right_deliveriesと既存RG1のepoch/既存game_lineupsのside。tenant付きFK/owner tuple一意/同要求再交付一意/同時active attempt一意が必要。予約前のrequest/attempt intentだけは短い制御transactionで耐久化し、開始成功mark・generation/delivery・両側lineup/UM2/statusは同一業務確定へ入れる。不明attemptから新attemptを自動作成せず、実business primaryの排他照会で旧transactionの終結と未確定を証明できるまでは停止する。詳細DDL/FK/列ACL/固定function/token集合と正式7.3/7.7はrootの次ゲートで固定する。

追加の技術不足として、実app UID20003は固定Ledger client UID20002へ直接接続できない。また現baseのrecording_generationsはappの直接INSERT許可を持つため、新関数を追加するだけでは任意D4/digestの直接投入を防げない。候補は既存RG1/identity subjectを広げない独立のroot保護initial issuer broker/PG subjectと、実owner-bound claimを記録したattemptの一度限り許可を消費する固定関数。これは新署名鍵や第2allocatorを作る提案ではなく、実`DurableLedger`（source c07f508d）/`V12Box`/RG1（5ee75156）の能力を分離して再利用する方法である。broker/4表の設計をこの追補で確定せず、資格enrollment/暗号再配達・最小CAP/列ACL/RLS・実registry・replay不明時停止を次の具体差分として残す。T1本体や全非0復元はこの保存contractの起案条件にしない。DB/source/正本/共有資産の変更は0。

## 7469e676の独立P1と同ステップ是正

非作者rightsの初回コードレビューはP1=1。証拠SHA256は`49a078d16cb4215209da67e559a780d9a4ef10cf5814bc476774071a44c8ddb7`。生TypeAdapter/SchemaValidatorの壊れJSONはClass overrideより前に失敗し、ValidationError.inputへ資格を含む元JSONを保持する。旧141成功はこの外側経路を検出しておらず、全経路の内部入力まで無害化した証拠ではなかった。同レビューは現共通HTTP handlerの外部応答/INFOログが非露出であることも独立に実証した。旧固定版/旧成功/P1を保持し、未接続候補のまま是正する。

rootはPO委任で、安全な公開Class入口（model_validate/model_validate_jsonと通常代入）・既存共通HTTP handlerの利用者向け応答/ログを保証境界として採用した。生parserやRequestValidationError.body等の内部入力は資格を保持し得るため、記録/汎用serializeへ渡さない。module/class/planへこの利用契約を明記した。private Pydantic APIの差替え・拒否の黙殺は0で、sourceの実行ロジックは7469から変更していない。

既componentへ生parser2負例と、DBなしFastAPI通常検証（壊れJSON/他field欠損）の実共通handler2例を追加。422の固定応答・ログ本文・LogRecord・exc_info/tracebackに資格がなく、不正routeの業務関数呼出し0を確認した。ここで追加したrouteは試験アプリのtransport検査口だけで、製品HTTP開始の提供ではない。対象4成功/0.63秒（旧141deselected）→最終component全件**145成功/0.87秒、skip0**。旧54+87と今回4を区別し、独立再レビューはこれからとする。backend対象format/Ruff/ty成功。物理追補は前節の必要対応だけを保存し、broker/4表/DDLの設計完成・採用を主張しない。


## 次単位の実actor/単一業務transaction案（候補・未承認）

2026-10-24、主担当からplan/researchの2pathだけの追補委任を受け、`fe4788d1` cleanから現物を狭く再照合した。編集/実行対象は本2文書だけ、source/DB/正本/共有metadata/Git indexの操作は0。旧physical annex/owner sheetは前記hashの未受理候補のまま、全過去引継ぎ/保全物の再監査はしない。

実物から新たに確定した接合不足は、(1) `repositories/transaction.py`のscopeが`create_database_engine()`＝app roleに固定、(2) TenantContext証跡はprocess内secretでRPC転送証明ではない、(3) 既RG1候補`5ee75156`の`rg1_control.scope_binding`はappだけEXECUTE、controller borrowもapp UID20003だけ、(4) Ledgerの許可client UID20002とapp UID20003は別、(5) 初期発行器はdevice共有lockの後にreserve/claim、game lock/insertを行う、である。旧annexの『全行lock無し予約』や、brokerへ既scopeを渡せばそのまま別roleで動くという推定を採らない。

[plan §6](plan.md#6-次小単位の物理接合候補未承認2026-10-24)へ、専用brokerがCookieを実再検証して開始の全業務transactionを所有する境界、exact2role/4表/既存2表の最小列、9methodの固定実処理、intentの先行durable commit、game→team→player→generation→delivery→RG1の順を具体化した。appがgameをlockして別sessionのpermit FK書込を待つ案は循環し得るため不採用候補とした。新たなallocator/暗号/認証計算は作らず、既単一発行器/実Ledger/V12Box/U-M2/共通executorを再利用する。

既単一発行器のgame lockとgeneration insertの間に、将来の開始serviceの両側名簿/U-M2を同一scopeへ接合する必要は残る。その開始差分で有限な専用操作として実装・レビューするため、本scopeの保存試験を実開始成功へ広げない。actor transportもRG1のexact peer/role1組追加なしには借用できないことを明記し、roleをappと偽装したりLedgerをappへ開放しない。新scope/role用の私有生成入口は実role/許可token集合を固定し、既公開app scopeの真性検査を緩めない。

この追補の新たな野球意味判断は0件。鍵実発行・運用配置・共有DB適用は未実施/委任外を維持する。rootの採否・独立レビュー/専用plan/必要7.3/具体asset受理前は次source編集を開始しないが、T1/実Port/HTTP/全非0復旧の完成を保存contract/実adapter局所実装の前提にしない。旧transportレビューP1/是正・UG1/UR1の親ステップ/回数を保持する。

親からの追加指示に従い、brokerのexact peer/role追加は現在のapp/control2+observer2正式登録の**後続**として分けた。次scope小単位はfinal `InitialRecordingRightScope`/私有factory/凍結StartOwnerと、exact9固定関数・4表・既存epoch/digest列・正負試験へ絞り、enrollmentのコード方針は既チームCookie＋端末資格方式の技術案として具体化した。新しい個人認証仕様のPO質問を作らない。最初のDB scope fixtureがdevice行/公開vectorを準備する事実と、後続の実enrollment/実broker開始を別に記録する。未知pendingの自動解消は実装済みとしない。


## §6初回P1×2の全採用と反映候補

固定bc8fdf39の限定非作者初回はP0=0/P1=2/P2=0、START-SCOPE-PLAN-01（(c)正常系が必要とするactor RG1供給を(d)へ後置）とSTART-SCOPE-PLAN-02（予約前から終結までのrequest/attempt排他の固定操作対応が未明示）だった。証拠は`/home/ymdms/.cache/pitchlog/review-start-scope-plan-bc8fdf39/evidence.json`、SHA256 f8527c11a24fa629312e3eecd91c6052c1c23d7e4b6dfa890f547534468847f9。旧plan e821ea55b6e9fca8dc72bf97275c4a6e3cd04fd7d6f8a9587c483b676166d4e4/research808e5d75d521c3bccc318cfa0f6fd069816cbb442ab364504fe08cc1782bb01cと初回否決を保持し、反映後の0件判定を先取りしない。

rootはPO委任による技術判断として両P1を採用し、plan/research2pathだけの最小反映を明示指示した。01は現app RG1正式登録を先行独立のまま保ち、その後のactor exact1組/実epoch・bindingのroot所有固定供給を(c)正常実接合前へ置いた。(c)の型/DDL/単体/拒否は供給待ちで止めず、正常grant/再交付/競合DoDも維持する。(d)には実broker RPC/実Cookie・認証再検証の全経路を残し、current RG1の成立をbroker完成待ちへ戻さない。

02は既9固定関数を増やさず、`InitialGrantScope.lock_valid_device`が`lock_device`→実credential digest真照合成功後に、同business Sessionの`resolve_start_attempt`で固定ownerのrequest→attemptを排他lockする対応へ具体化した。戻り値/owner/行存在/outcomeを照合し、pendingだけ新規進行、committedは同一現権利のexisting_start照合へ進み、不正・欠損・他outcomeは閉じる。これにより既issuerのreserve/claimより前から終結まで排他を保持し、短いintent取引のlock継続や別Sessionを代用しない。並行同request2本の直列再交付/追加予約0、無効資格・owner差替え・許可外outcome・別Session/短intent lock代用の負例を(c)へ対応させた。

今回rightsは主担当の明示指示により反映作者へ役割を変更した。初回非作者レビューと今回の候補作成を別に記録し、反映後の独立最終確認を兼ねない。source/DB/共有asset/Git indexを変更せず、4表/2role/9関数/9method、T1/Port/HTTP/全復旧を準備着手条件へ追加しない境界、旧transport/親全計画/全レビュー系列を維持した。rootが別の非作者へ固定反映差分を渡し、再確認/対象版判断後だけ次の製品実装へ進む。
