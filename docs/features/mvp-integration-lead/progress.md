# 初回MVP 主担当引受・進捗台帳

## 2026-11-10 07:40 JST：P3直後readの停止点を`read_undo_prefix`のanchor枝へ限定

- **再測**: `test_actual_p3_26_csv_export_http` **1 passed 336.59秒**（ZIP 26行・対象d1=26「ボール」）。`lifecycle_after_p3` は503のままで、応答bodyは汎用エラー。
- **停止点**: `read_p3_nonplay_current`/`p3_effective_nonplay_frame`/`p3_effective_nonplay_stack`/`_read_legacy_undo_source` の例外traceは空。停止は `read_undo_prefix` の `nonplay-prefix-checkpoint-v1` 枝が `read_lineup_prefix` へ委譲した先の `OrdinaryPrefixError:通常投球の確定prefixを確認できません`。P3訂正直後は物理CPがanchor形式のまま、27球目保存後にv3 CPへ進み同readが200になる。
- **次unit**: `read_undo_prefix` のanchor枝で、P3 capsuleの合成checkpoint/effective frameを `read_lineup_prefix` と同じ `_read_p3_lineup_projection` へ渡し、物理anchorと論理nextの差を二重実装せずに扱う。実装時はP3直後read 200を同じ26球試験で再測する。

## 2026-11-10 07:20 JST：D11実DBと走者操作の実ブラウザ縦断が成立

- **D11実DB**: `test_stats_native_d11` **2 passed 159.41秒**。27指標を実SQL/RRRO/receiver/formatterへ通し、`ordinary-pitch-play-v1` は走者の得点/盗塁観測をwireに持たないため `rbi`/`runs`/`steals` を `source_unavailable`（reason `MISSING_OBSERVATION`）として返す。score不変から0を推定しない。
- **走者操作の実ブラウザ**: `test_runner_operations_screen_e2e` **1 passed 250.22秒**。ローカル生成self-signed TLS（SAN `IP:127.0.0.1`）でPlaywright/Chromium→Vite HTTPS→製品app→owned DBを実走。UI作成/開始、実走塁の保存、重複、reload、越境拒否、DB全値を照合した。**実機・実利用者端末・本番TLSではない**（候補環境の実ブラウザ）。
- **同時実行の切分け**: 同一invocationのHTTP/DB試験は substitution vertical、lifecycle v3、stats undo helper×2 の **4 passed**。runner/batted hits/interference/substitution/undo の画面E2EはTLS PATH未供給で4 skipped + interference setup errorだったため、self-signed TLSを明示して個別に再実行した（skipを成功へ読み替えない）。
- **画面E2Eの実測**（self-signed TLS、実Playwright/Chromium）:
  - **pass**: runner operations **1 passed 250.22秒**、substitution product **1 passed**。
  - **fail（未解決）**: batted hits 3件は零読み後の「三振・攻守交代を含む投球の記録へ」ボタンが30秒以内に現れず、4件目は結果ファイル欠落。interferenceはINT-02（1play）まで保存後に次分岐のPOST/GETが30秒timeout（2試合目は0play）。undoはACK喪失→reload→retryで同一undoの`attemptSha256`が変わり、同要求再送の期待に反した（新attemptで送信）。いずれもobtained rejection/失敗として残し、成功へ読み替えない。
  - **undoの再実行**: 上記のattempt差は、`recoverableSyncPost.spec.ts`が固定する既採用の結果不明解決（`retry_allowed`後に同本文/同D5のまま新attemptへ進める`SyncAttemptBarrier`）と一致していた。E2Eの旧期待「attemptまで同一」を、本文/D5同一・attempt更新の期待へ是正し、`test_undo_product_screen_e2e` は **1 passed 115.05秒**。旧attemptの再利用を成功条件にしない。
- **3試合×30閲覧load**: **未成立**。E2E導線のcold start待ちを分離した後、30閲覧の初回`更新済み`・server-only注記・18名 lineupは通過したが、wave 1の実保存で`recordRealPitch`のPOST/GETが45秒timeout。30閲覧同時poll下でwriter保存が45秒以内に成立せず、保存後10秒更新の測定へ到達しない。**NFR-004の3試合×10閲覧（本試験は30閲覧）は未達**として残す。タイムアウトを延ばして成功へ読み替えない。
- **次の実行**: 30閲覧下のwriter starvation（app/DB/uvicorn worker/ブラウザ資源の切り分け）、共有E2E導線（create→start→record）の現行UX追随、interference分岐の停止点、P3直後read。TLS資材は`/tmp/opencode/tls`の試験専用で、リポジトリ/シークレットへ保存しない。

## 2026-11-10 06:55 JST：broker再起動B（同一epoch）も26球→P3→27球目で成立

- **新たに通った**: `test_p3_26_broker_restart_vertical` **1 passed 359.39秒**。26球記録中にinitial grant brokerの子PIDをkillし、supervisorが**新しい子PID**で同じsocketへ再起動した後、P3 26件訂正→27球目まで受理。DBはgate open/recovery_generation=1、`recording_generations=(1,normal,NULL,NULL,1)`、play_rows=28（26元+P3有効版1+27球目）、現在stats source_count=27、open writer_bindings=0を実測した。endpointファイルの再出現だけでなく新child PIDを確認している。
- **意味の限定**: これは**同一epoch**のbroker再起動であり、非0 gate/right epoch復旧ではない。fail-closed後の旧epoch同一D5再送がB7/503のままであること（再起動だけでは権利を復活させない）は既存試験で確認済み。新generation/D4+V12付与・旧generation失効・旧holder/epoch拒否・結果不明の別解決は未実装。
- **次の実行**: D11実DB、操作在庫（走者/併殺/失策/妨害/交代/取消/タイブレーク/終了条件）のowned画面E2E、3試合×10閲覧、P3直後read。

## 2026-11-10 06:50 JST：P3後28球目まで同一候補で成立、30秒はwire指紋の重複再計算が原因

- **新たに通った**: 26球→P3 26件訂正→27球目→`lifecycle-prefix-v1` 200→終了受理→再開受理→**追加play（28球目）受理**→再終了→reload→公式成績/ゲームCSV/シーズンCSV。`test_actual_p3_26_lifecycle_end_reopen_add_reend_stats` は **1 passed 492.58秒**。DBは `play_rows=29`（26元+P3有効版1+27球目+追加）、有効版イベント行1、現在stats `source_count=28`/`confirmed_ended`/current版1、最大source_count 28、gate open、ゲームCSV 20行・シーズンCSV 10行を実測した。
- **原因の確定**: 以前の`writer binding rejected`（binding_age 30.1秒）はP3 26件検証の重複ではなく、同一の不変wire sourceに対する`source_binding.read`/`assert_event_source`が117回、各回で全V7 activeStackの指紋・正規化・原本encodeを再実行していたこと。cProfileで当該apply 30.4秒のうち`source_binding.read` 23.25秒、`_flush_native_stats` 15.96秒、`_json_value` 15.08秒を実測した。
- **是正**: `wire_event_fingerprint`と`wire_original`の正規化を、不変`MappingProxyType`の同一性で有界に再利用するcacheを追加した。seal/型/指紋一致の比較は毎回維持し、差替え/偽値の拒否試験は不変。P3 current/頁の全bytes keyによるプロセス内packet cacheも追加し、anchor CP行の`quoted_name` keyだけをkey生成時にplain strへ正規化した。**30秒DB writer bindingは延長せず、不変のまま**。
- **実測**: P3 packet cacheはhit 27/miss 6/key error 0。hit時`verify_p3_current_packet`は約90ms、miss時約3.4秒。lifecycle readは約1.6〜2.0秒（以前約5.3秒）。追加playの最終binding ageは7.558秒で30秒内。**5秒目標は未達**（追加playは7.5秒超）だが、30秒期限拒否とは別測定として記録する。
- **限定**: P3訂正直後（27球目前）のlifecycle readは503のまま（P3 current CPの物理行と論理next contentの差）。実機/実TLSブラウザ/3試合×10閲覧/バックアップ復旧/運用公開は未実施。
- **既知赤の追加**: `test_sync_apply_writer_binding::test_void_adapter_preserves_every_other_registered_function` は固定registry期待が現行operation数に追随しておらずHEAD前から赤（本差分外）。既存の`save_primitive_source`本文不一致と`tenant_transaction_scope`欠落も継続。

## 2026-11-10 05:30 JST（履歴）：追加playはdomain TIME_LIMITを解消、30秒bindingの原因切り分け

- **新たに通った**: 26球→P3訂正→27球目→lifecycle read 200→終了受理→再開受理→**追加playのdomain評価**。27frame級の非play継続が`vmTimeoutMs=100`の`TIME_LIMIT`になったため、5秒応答目標・2秒reply期限の内側で`_VM_TIMEOUT_MS=500`へ有限上限を広げた（30秒DB bindingは不変）。
- **現在失敗**: 追加playの`persist_accepted_play_export`で`writer binding rejected`（`precommit_failure.binding_age_ms=30145`、`expires_at<=now`）。DB writer bindingの30秒総保持を**延長せず**、server側`read_confirmed_nonplay_normal`がP3 capsuleの26-item T5/監査検証を再実行する重複で30秒を超えた。クライアント直後のlifecycle readと同一P3不変原本を二重検証している。
- **次の作業**: P3 capsule/head/current CPをkeyにした同一プロセス内の検証済みP3 packet cache（またはsource専用の軽量検証）で、write bindingの30秒区間から重複T5/監査再計算を除く。30秒は延長しない。その後、追加play→再終了→reload→成績27/CSV、P3直後read、broker再起動B、D11実DB、残操作、閲覧、正式統合へ進む。

## 2026-11-10 04:30 JST：P3後27球目の終了・再開は受理、追加playは次unit

- **新たに通った**: 26球→P3訂正→27球目→`lifecycle-prefix-v1` 200→**終了宣言 受理**→**再開 受理**。write側 `read_confirmed_lineup_prefix` と `read_confirmed_nonplay_prefix` に、P3 next CPが現在docの祖先である場合の同一限定（watermark/revisionの祖先+現在headからのlast source）を接続した。P3-effective stackをread/writeで同じ `p3_effective_nonplay_stack` に限定し、物理/論理の二重実装を作っていない。
- **現在失敗**: 再開後の追加play（28球目）が server-side domain guest で `DomainRuntimeError: ゲストの実行に失敗`（`_evaluate_nonplay_normal_bound` → domain host）。クライアント側の同じ継続評価は成功しているため、serverが再構成するP3-effective中間frame（d1=26の実効play/historyEntry/source）と継続requestのsource束縛の不一致を次に切り分ける。終了・再開のACK、read 200、gate openは実測済み。
- **次の作業**: (1) 追加playのserver-side source再構成（`_evaluate_nonplay_normal_bound`）でP3-effective frameの`play.source.eventId`/historyEntry/playIdを現在chainへ束縛する、(2) 追加→再終了→reload→成績27/CSV、(3) P3直後（27球目前）のlifecycle read 503、(4) broker再起動B、D11実DB、残操作、閲覧、正式統合。

## 2026-11-10 03:20 JST：P3後27球目のlifecycle readは成立、終了書込みは次unit

- **新たに通った**: 26球→P3 26件訂正→27球目保存（`prefix=27`）に続き、27球目後の `lifecycle-prefix-v1` が **200**。P3 capsuleのwatermark 26・item 26・頁chain形式のsource/evaluation digest・非current候補版・T5評価26件・後続27球frameを実DB readerで照合し、P3 next CPを履歴ancestorとして受理した。P3/CSV純201 passed、追加76 passed。
- **残る503**: P3訂正直後（27球目前）のlifecycle readは503（P3 current CPが物理行と論理next contentで異なるP3 stateの未対応）。27球目後の **終了宣言** は503 `OrdinaryPrefixError: 通常投球の確定prefixを確認できません`。原因は lifecycle write の `read_confirmed_lineup_prefix` が物理/旧履歴のactive sourceを照合し、lifecycle readのP3-effective source（d1=26の訂正後frame）と一致しないこと。終了・再開・追加・再終了へ進むには、同じ `p3_effective_nonplay_stack` をwrite側actual sourceへ適用し、P3 next CPの祖先を限定する専用unitが必要。
- **次の作業**: (1) `read_confirmed_lineup_prefix`/`_confirmed_lineup_source` のactual sourceへP3-effective stackを同一関数で適用（物理／論理の二重実装をしない）、(2) 27球目後のend→reopen→additional play→re-end→stats/CSVの再実測、(3) P3直後readのcurrent CP論理next対応、(4) broker再起動B・D11実DB・残操作・閲覧・正式統合。
- **既知赤**: `test_p3_function_product` の `save_primitive_source` 本文不一致と `test_nonplay_prefix_read` の `tenant_transaction_scope` 属性欠落は変更前から。D11実DBは未実行。実機/運用/3試合10閲覧/バックアップは未実施。

## 2026-11-10 02:10 JST：P3後のlifecycle読取を候補版・履歴CP・頁chainへ接続

- **診断の確定**: `lifecycle-prefix-v1` はP3訂正直後と27球目後の双方で503。traceは `read_p3_current` の `P3 current ... rejected` → 修正後 `P3 current count rejected`（capsule watermark 26が旧1..25上限を超過）→ `P3 current source count rejected`（P3 headが後続版を指す）→ verifierの `P3 current stats row/CP linkage/source集合`。P3候補版はcurrentでなく、後続playがhead/capsuleのstats pointerを進め、頁chain形式の `source_set_digest`/`stats_evaluation_set_digest` を持つ。
- **是正**: `read_p3_current` はP3 capsuleのwatermark一致・model一致の版を選び、非current候補/履歴版のhealthを要求しない。応答checkpointはcapsuleのnext content/id/revision/digest/水位を合成し、現在CPとは分離。verifierはP3版のwatermark/item/原本/有効/CP連結/change eventを個別に照合し、頁chain digest（source/evaluation）も再計算して受理。非play frameは既に実効版なら再適用せず検証、stackの現状態はP3 watermark frameで照合。P3 next CPは現在chainの祖先として許可。item上限を26（25頁+対象）へ。契約function bodyを再生成。
- **現在**: P3/CSV純 **201 passed**、追加76 passed。26球→P3→27球目の保存は成立済み。lifecycle readの実DB縦断は反復中で、次の未達は verifierの後続段（`P3現head`/T5評価/履歴再構成）または end/reopen 接続。台帳の既知赤（`save_primitive_source` 本文不一致、`tenant_transaction_scope` 属性欠落）は変更前から赤。

## 2026-11-10 01:20 JST：P3後のlifecycle読取を候補版・履歴anchorへ接続

- **診断**: 26球→P3訂正→27球目はアプリ結果 `prefix=27` で保存成立。しかし `lifecycle-prefix-v1` はP3訂正直後・27球目後の双方で503。traceで `read_p3_current` の `P3 current read rejected`（line 159）を確認。原因は非play lifecycle readがP3候補版（`is_current=false`）を拒否し、さらに現在CPのみを選んでいたこと。
- **是正**: `read_p3_current` はcapsuleの `next_checkpoint_id` を履歴anchorとして選び、P3版がcurrentでない場合はcapsule/checkpoint/source束縛だけを検証してcanonical healthを要求しない。verifierは非anchorの候補/履歴版を受け、`p3_effective_nonplay_frame` は既に実効版のframeを再適用せず検証して保持、stackの現状態照合はP3 watermarkのframeで行う。`read_undo_prefix` はP3 next CPが現在chainの祖先である場合だけ許可。`read_p3_nonplay_current` のanchor行はpacket原本から供給。契約function bodyを再生成。
- **現在**: 既存P3/CSV純201 passed。`test_p3_function_product` の `save_primitive_source` 本文不一致と `test_nonplay_prefix_read` の `tenant_transaction_scope` 属性欠落は変更前から赤（今回差分外）として分離。
- **次の実行**: 26球→P3→27→終了→再開→追加→再終了→成績/CSVの再実測。

## 2026-11-10 00:10 JST：27球目503の原因確定とP3後縦断の再開

- **原因確定**: 訂正後27球目の503は、RG1 controllerが `LedgerOutcomeUnconfirmed` で終了しgateがclosedになったため。authorityのbinding lease channelが一般timeout（隔離fixture 2秒）で、30秒保持中の正当な無通信を切断→authority全体がblocked→controllerのidle確認が失敗、というliveness欠陥。DB bindingの30秒期限切れではない（失敗時も期限余裕24.7秒）。診断実行では27球目保存のbinding_age 5.5秒で同じ経路を再現し、controllerの終了理由とgate closedを実測した。
- **是正**: `authority.py` の受付channelを `sync_binding` だけ35秒（30秒総保持+余裕）にした。DBの30秒・immutability・sliding renewalの意味は変更しない。test-only binding brokerのapp channelも35秒へ揃えた。manifestのadapter/source SHAを実ファイルへ追随（adapterはHEAD時点で既に不整合だった）。
- **D11 rbi/runs/steals**: `ordinary-pitch-play-v1` は走者の得点/盗塁観測をwireに含まないため、score不変だけからcompleteを推定しない。D11 current_openの `source_unavailable` 期待へ整合。stats純 **395 passed**。
- **A（broker障害なし・訂正→27球目）**: 26球→P3 26件訂正→27球目の実HTTPが **成功**（app結果 `prefix=27`, controller running, gate open, 504旧assertのみ）。旧testのP3 snapshot DB照合が `打席結果` を見ていたため `打撃結果` へ修正した。製品経路は27球目まで書込み成立。
- **新規回帰**: `test_p3_fault_controller_liveness.py` を追加。P3故障取消直後とP3受理直後に `/sync/attempts/recover` でgate生存を照合する。第1故障後は200を実測。
- **次の実行**: 26球→P3→27→終了→再開→追加→再終了→reload→成績27項目/毎球ZIP/成績CSVの同一候補試験、broker再起動を挟む同縦断、D11実DB。


## 2026-11-09 03:20 JST：P3有限INSERTと訂正CSV0050を同一統合候補へ接合

- **引継ぎ照合**: `feature/mvp-integration-lead@743f137b` clean、固定候補は台帳どおり。新統合枝 `feature/mvp-integration-20261109` を `c327d7ee` から作成し、`d5e63831`（CSV共有0050）と `3952d2c0`（CSV P1後発）を通常mergeした。main/developへの直接変更なし。
- **接合内容**: P3有限37列/INSERT policy1/保護4列cleanと、CSV0050の17列append-only/5関数/既9列SELECT追補/世代束縛/動的列原本照合を同一資産へ統合。`first_ball_product` はCSV activation→P3 insert activationの順で両方を保持。公式helperからddl-elements/manifest/4関数body/runtime contract protected objectsを再導出（revision 34→35）。P3/CSVの対象129 passed、0050 current startup実PG 1 passed 61.51秒、P3/CSV storage純219 passed、backend Ruff/Ty 0。
- **UI是正**: 妨害公開口 `deriveInterference` 追加に伴うartifact spec 3件と、runner enum/artifact identityに追随していないschema spec 2件を現行正準へ修正（5 files）。root `tests/domain/gen/test_undo_selector.py` のbackend importを既規約（importlib）へ修正しroot Ty 0。frontend vue-tsc/ESLint 0。
- **実E2Eの停止と切分け**: 初球HTTPはowned実DBで `LedgerUnavailable`。broker観測では `binding_check` が0.4〜30.2秒に200回超、authority lease 30秒で失効していた。97a単独は同試験成功、c327単独は再現。P3 insert差分はapp role権限を変えないため、保存処理が30秒境界に達するliveness問題として切分け、次の3点だけを実装した。
  - 生存確認ごとに同一leaseを30秒延長するsliding renewalをapp/authority双方へ実装。非文字列/後退応答/期限切れは拒否し、DBの `publish_writer_binding` が持つ30秒上限・immutabilityは変更しない。
  - authorityのread-only接続をbinding中だけ再利用し、書込みは従来どおり呼出ごとの独立接続+commitを維持。
  - binding_checkの `_live_matches` だけを1秒に1回へ抑制。control原本照合・fence生存確認・期限・主体は毎回実施。
  - 初球E2Eはcleanup後の同sourceで **1 passed 236.95秒**、保存区間は約21.6秒（5秒目標には未達）。純14 passed。
- **P3訂正の現在地**: 有限INSERTは実P3入口まで到達し、前版CSVアンカーが0行になる原因を「P3変更後のcanonical healthと保存済前版T5版の混同」と特定。前版を `v.source_count=p_watermark` + 実checkpoint + 保存済primitive件数へ束縛する方式に修正し、純43 passed。頁読取のヘッダは `p3_projection_write_admissions.transaction_id=own_xid/state=consumed` とcapsule/headの同一TX束縛へ置換した。**P3 shortの応答本文は B14「P3変更内容が確定原本または有限対応範囲と不一致」**（confirmedContentなし、capsule/snapshot 0）であり、200でも訂正保存成功ではない。shortの置換結果は正式closed key `ball/called-strike` に合わせたが、対象/prefixが有限範囲外で拒否された。
- **P3 26pagedの実接続**: 26球変更は begin/finalize/CSVまで通過した。停止原因は4点で、いずれも比較条件を緩めず保存元の意味へ合わせて修正した。(1) `project_p3_direct` の打席結果はV7の `calculation.request.t1.resultId` が正本で、`observations.resultId` や最上位`t1`ではない。(2) P3頁CSVのwriter読取は通常Sの`canonical_s`を使うと訂正change eventの薄いpayloadからartifactを再計算して対象行を落とすため、頁確定と同じcapsule item優先の生成canonicalへ束縛した。(3) 回別スコアのtarget判定もP3対象だけcapsule itemの訂正payloadで行う。(4) `read_p3_current_header` はcheckpoint contentの実キー`version`と`#variable_conflict use_column`を使う。実E2Eは **ACK `変更受理`（d5・対象参照・confirmed_content）**、confirmation、capsule items 26件（corrected 1件）、head revision 1、page rows 26件、P3 CSV snapshot 26件、d1=26の直接列/入力項目まで通過し、故障2点の取消も通過した。26th通常球の旧42501は再現せず、begin/finalizeの42501/42703は期限切れではない。
- **27球目の通信断（30秒期限とは別）**: P3訂正後の27球目は **503**。原因は `RG1Unavailable` → `RG1ControlUnavailable` → `BrokenPipeError`（RG1 control channel）で、DB writer bindingの期限切れではない。commit前検査は **binding_age 5.303秒**、DB binding `expires_at=09:18:14.260`、検査時刻 `09:17:49.581`（余裕24.7秒）、authority期限`09:18:16.286`。27球目の書込みは成立せず、current `source_count=26` のまま（原子性維持）。次は同一D5再送・再起動・ACK喪失として復旧を検査する。**5秒目標は未達（5.303秒>5秒）だが、30秒期限による拒否ではない**。
- **broker再起動後の境界**: RG1 brokerをfail-closed後に同一socketへ再起動するtest-only supervisorを追加し、endpoint再出現を実測した。27球目の503後に同一D5・同一本文・同一attemptで再送し、`/sync/attempts/recover` も照会したが、復帰結果は **B7/503**（RG1 gate/right epoch不一致）。書込みは不成立のままで、再起動だけでは同一ゲート権利を復元しない。次は新epochのright再取得（再開/復旧handshake）を製品経路で接続する。30秒binding期限とは無関係。
- **正常lifecycleの再確認**: `test_actual_v3_two_ball_end_reopen_append_reend` は現候補で **1 passed 128.86秒**。終了→再開→追加→再終了の通常v3経路は成立。P3訂正後の同経路は27球目のgate復旧待ち。既存v2 lifecycle read試験は現行v3試験に置換済みとしてskipし、v2互換の再検証は別途保留。
- **独立レビュー指摘の是正**: 固定HEAD `5a5ccc93` のCodexレビューでP1/P2×2。P1はP3 CSV読取が `observations.resultId` を要求し、通常投球V7で失敗する点。T1 `calculation.request.t1.resultId` の共有helperへ寄せ、P3 coverageのDiskRows `append` 不在、change eventの`target_generation`、P3で置換された旧playの監査coverageも是正した。実26球訂正後の **`/exports/plays.zip` 200・26行・対象d1=26「ボール」** を実DB/HTTPで確認（**1 passed 339.66秒**。snapshot保存だけでは代替しない）。P2はv2 lifecycle skipで故障取消が失われる点と、broker再起動testがendpoint存在だけで偽陽性になり得る点。v3 lifecycleへ実故障注入→全取消→再終了を追加し、broker再起動testは新child PID一致まで確認する形へ強化した。
- **現行候補の横断スイート**: 0050現行で `test_stats_native_vertical_http`・`test_stats_basic_lifecycle_http`・`test_play_export_v3_product_http`・`test_play_export_score_vertical`・`test_play_export_substitution_http`・`test_viewer_live_owned` の **9 passed**（CSV/ZIP・27項目成績・交代後CSV・viewer実DB）。candidate DDLの二重適用を0050では行わず、viewer catalog期待を0050へ更新した。`test_game_lifecycle_v3_http` の終了/再開/追加/再終了も **1 passed**。これらは訂正後P3経路の完成を意味しない。
- **P1/P2再レビュー後の現在地（HEAD 99b4a0b5）**: P3訂正後の実CSV ZIPは **1 passed 332.17秒（200・26行・d1=26「ボール」）**。P3 coverage純18 passed。v3 lifecycle故障は **1 passed 146.67秒**（故障D5のevent/ledger/admission 0、stats版4、HTTP全取消、再終了）。broker supervisor新childは **1 passed 49.66秒**。Ruff/Ty 0。Codex再レビューはP2 1件（故障要求D5と照合D5の不一致）を指摘し、`99b4a0b5`で一致させた。
- **0050 legacy試験の分離**: `test_stats_appearance_http` の候補DDL再適用を0050では行わないよう分離し、`start-zero` は **1 passed 56.38秒**。ただし同ファイルの残り5件は故障注入とCSV候補DDLの旧前提が残り赤。`test_play_export_primitives`等のv2前提も未整理。
- **追加の旧試験**: `test_terminal_pitch_storage` / `test_sync_apply_idempotency_boundary` の同時実行は 2 failed/5 errors。内訳は旧v2 `OrdinaryPrefixError` と所有DB fixtureの後続接続拒否で、P3/P1の成功証拠へ数えない。個別のv3経路は別途通す。
- **実機準備**: `manual-rehearsal.md` に接続先・HTTPS/端末/データ/操作/期待/既知制限を固定。27球目はB7/503の未回復として明記し、実機成功を代記しない。
- **既知赤（最終統合前に是正）**: D11 `rbi` が期待`source_unavailable`に対し`available 0`（2 failed）。`test_stats_queries` 2件・`test_stats_appearance_http` 8件は現行v3/0050前提へ未追随（空診断のAssertionError）。旧v2/candidate DDL前提のbackend試験群（play_export_primitives等）は現行v3へ未整理。27球目はbroker再起動後 **B7/503** のままで、非0 gate/right epoch復旧が未実装。実TLS browser・実機・運用・3試合/10閲覧・バックアップ復旧は未実施。
- **30秒契約の確認**: `docs/design/data-model.md` は writer_bindings の期限を含む27列を不変とし、`state/close_id` のopen→closed一度だけを許す。`publish_writer_binding` は `expires_at > now+30s` を拒否し、`assert_writer_binding` は `expires_at<=now` を拒否する。したがってDBの30秒は**更新不可の総保持上限**であり、DB行の期限更新は単なる不具合修正ではなく契約改訂（data-model/SQL/trigger/レビュー）を要する。既存委任の範囲では実装しない。authority側のsliding renewalはDB行を延長せず、書込みを30秒超へ許可しない。
- **未了**: 26paged全体（P3本体と故障取消は通過、27球目はbroker再起動後もB7/503で停止）、broker再起動後のgate/right epoch再取得、同D5再送・ACK喪失・担当交代の復旧、閲覧3試合、正式corpus reseal（requirements pinが現行文書と不一致でcatalog checker停止）、7.7/seal/必須CI/通常PR統合、実機・運用復旧。`test_p3_candidate_compile_author` は0048候補DDLを0050 currentへ重ねる旧試験で、有限INSERTの失敗ではない。

更新: 2026-10-23。判断者: Codex主担当。根拠: 同日POの `/goal` 指示と例外委任（撤回または今回MVP終了まで）。山田正輝の個別実値確認・署名とは記録しない。

## 引受と固定点

全体目標・編集権を引受。各領域の現HEAD・作業状態は [takeover.json](takeover.json)。既存引継ぎを正として参照し、全保全物を読了したとは扱わない。P-6は役割・封印・曝露履歴を維持し、候補作成へ吸収しない。TSK-545はHEAD一致・clean、対象cwdの稼働なし。独立引継ぎ未受領の不足は残し、今回POによる主担当移管を記録する。旧担当への再許可照会は要しない。

- develop: `1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`。2026-10-23 fetch確認。
- #176/#174/#175公開HEADは報告値一致、Draft。#173は公開`dac2ff15`、ローカル`6af8c801`と未コミット36パス。既存引継ぎmanifest照合前に触れない。
- #176: `c1413b25`と未コミット3文書は引継ぎ通り。pytest/ruff等の変更・検査プロセスなし。停止記録と今回指示に基づき引受。旧担当通知はPRコメントを使う（agmsgは当該project未登録で既存担当との経路がない）。送付と受諾を分ける。
- #174未コミット引継ぎ文書、T2未追跡JSON、成績未追跡文書は原状保存。採用・削除前に確認。
- 初回MVP Pageは接続tool read_pageで取得済み: https://chatgpt.com/space/page_711a9b1ac7d88191a6b0bc313a60db01 。元正本への反映は未実施。

## 編集所有と順序

主担当管理worktree: `feature-mvp-integration-lead`（develop起点）。一括移植をせずPR単位を維持。

| 単位 | 編集所有/場所 | 現在の範囲 | 提供・接続・検証 |
| --- | --- | --- | --- |
| O5コア登録・委任手続 | 主担当worktree、担当をpath別指定 | 独立planと前提PRへ分割するPO委任判断。既存#176一件ステップへの押込みを避ける | 計画作成中。#176のO5製品runner成功は未成立 |
| #175 step3 codec接合 | 分離`feature/mvp-preparing-codec-connection`、product_connection担当 | 保存JSON復元と正式codec接合の2製品パス＋テストのみ | #174固定候補との隔離接続。正式統合とは別記 |
| #176→#174→#173→#175 | 主担当、共有正式資産は直列 | 各最終HEADの独立レビュー・受理・CI後通常merge | 全て未統合。チェック欄だけで成立扱いしない |
| T5/T6・成績CSV | 主担当（今回責任移管） | 既存U-X1と調査・計画候補照合後にstep単位 | 製品未提供。毎球CSVはU-D2調査/計画を再利用（製品実装は未存在） |
| P-6 | 独立役割、既存資料参照 | 封印物/期待値を候補作成担当へ渡さない | 新blind導出未実施。段階B一致を一般化しない |

## 製品到達点と残件

| 到達点 | 実装場所/提供版 | 状態 | 次の証拠 |
| --- | --- | --- | --- |
| A 試合作成・preparing再取得 | #174 resolver後続、#175 components後続、U-F8 | 候補部品あり・実画面→実API→実DB未接続 | 正式codec拒否を先に接合、resolver operation/read route/providerを順次供給 |
| B 開始・権利・1球保存と復元 | U-R1/T1/U-S1/TSK506 | 接合未成立 | 実権利・計算・永続providerを結ぶ |
| C 通常全操作・終了後訂正 | U-F8/T1/T2/U-S1 | 未検証 | 実製品1試合・版一貫性 |
| D 故障・再起動・再送・交代 | U-S1/U-R1 | 部品検査と実DB/HTTPを区別 | 隔離DBの原子性/復旧試験 |
| E 閲覧・基本成績・CSV・負荷 | U-F8/U-D2/T5/T6 | 未接続/未提供を含む | 暦年JST、終了確定版、毎球/成績CSV双方 |
| 実機・運用HTTPS・バックアップ復旧 | 山田正輝（運用責任）/主担当準備 | 未実施 | 実機版と機種、許可済環境を固定。エミュレーションと区別 |

MVP-FR-001〜017 / MVP-NFR-001〜012の個別対応は実装場所確認時にこの台帳へ追記する。現時点で正式受入を推定しない。委任外の未裁定意味、実機/運用資源は具体判断票へ集約予定。Goalは継続中。

## 照合の追記と判断票（2026-10-23）

- `/root/o5_registration`がUR1 manifest全46パスのSHA/集合一致、HEAD一致、後発差分0を確認。status通常36行は未追跡ディレクトリ集約によるもの。旧公開#173との差分を後続の正式受理時に扱う。
- U-F8は封鎖UIの統合と実接続/受入の未着手を分離。9パス追補は旧最終承認待ち、既存追加レビュー残0を保持。US1 C1/F1候補成功はF2/F3の実耐久provider完成を表さない。
- U-D1は544一次引継ぎで未承認計画/製品実装0。毎球CSVもUG1 A01で一時保留/製品0。どちらも実装済みという調査側表示を採用しない。
- TSK-545のE11/E07未裁定表示は2026-10-18の旧状態。T2 post-153引継ぎと `p8-human-decisions-and-receivers-2026-10-18.md`、planはE11=A/E07=B採用済みを保持する。再裁定を求めない。正本/正式契約反映は別条件。545からの個別受領回答は未取得だったため、これから主担当が版を特定して受領範囲を確認する。
- P6はALL-WORK-HANDOFF.txtの資格/封印注意のみ照合。結果JSON/期待値/封印物は未読。主担当・候補担当を新blind検証者にしない。
- 保存codec接合: 隔離候補HEAD `6ddbc341`。実体2パスの新差分だけを独立レビュー（P0/P1/P2=0/0/0）。対象pytest100成功。#174固定codec+#175既存成果を供給した候補で、正式API/DB/画面の成功ではない。patch/bundleはcache保全。正式基線統合後の再接合が必要。
- O5パス宣言: commit `6ca9d157`。対象pytest274成功/Ruff/ty成功。JSON登録は次ステップ、元#176には変更なし。引受通知: https://github.com/masaki1025/pitchlog/pull/176#issuecomment-6364057612 （送付済・受諾未確認）。
- 限定委任手続PR #177はDraftで準備中。計画第1回P1×2/P2×1全採用、第2回0件、PO委任で承認。人間チェックの代記は行わない。

### POの新意味判断を要する事項（同一事項の再照会を避ける）

| ID | 具体例・現在の根拠 | 選択肢と推奨 | 影響・再開条件 |
| --- | --- | --- | --- |
| MVP-D01 | 9回裏2対2→3対2、9回から1点差でコールド可という有効規則。サヨナラとコールドが同時成立。T2引継ぎはoutcome優先だけを未採用と明記。既採用E08はコールド対通常終了だけで、サヨナラには拡張しない | B推奨: walk-off（サヨナラ）を返す。A: cold-end（コールド）を返す。どちらも検知/ロック/宣言促しtrue、自動終了falseは既存方針維持 | 終了理由の正式値・画面表示・契約case/独立期待値が変わる。PO回答後にその範囲だけ正本/契約へ反映。未回答中は仮仕様で確定せず、保存接合・guard等を継続 |

実機/運用資源は製品経路準備と並行で具体化し、利用直前の委任外承認が必要なものだけ同表へ追記する。

## 接続・故障検証の証拠追記

2026-10-23、#174固定HEAD `e30edc79a7f90aa27cb14303910676e414c2cab6`（未コミット差分は既存引継ぎ文書のみ）のbackendで、既存使い捨てPostgreSQL fixtureを使った実DB検査を主担当が実行。Docker Server29.1.3、既存postgres:17.11-bookworm。共有DB/利用者データへ適用なし。

コマンド: `uv run pytest tests/db/test_stage_a_rule_candidates.py -q -k 'formal_stage_a_startup_preserves_closed_publication or formal_stage_a_startup_authz_failure_keeps_placement_closed or stage_a_staged_startup_from_empty_database_and_retry or stage_a_candidate_insert_fault_rolls_back_everything or stage_a_function_candidate_rejects_override_and_guc_mismatch'`

結果: **5 passed, 21 deselected in 33.82s / exit0**。正式段階起動、認可失敗の非公開保持、空DB→配置→再試行、配置途中故障の全取消、override/GUC不一致拒否を実測。DBの独立接続試験であり実HTTP/画面作成成功ではない。O5製品runner/実耐久provider完成/実機受入の代替ではない。

#178コード候補 `719bb308`は独立実装レビュー第1回可決（P0/P1/P2=0/0/0）。reviewer `/root/independent_review`、候補作者 `/root/o5_registration`と主担当。対象base1ab398cc、diff SHA256 `dab69624aad19aeaf093d8fc2968cb165c23808d4a5bbb14fb0bda989546c13f`（git diff --no-ext-diff --binary base head）。JSON登録時の旧試験1件失敗は隠さず51a030d3のステップ1範囲是正に記録し、公開履歴を書き換えていない。最終274件成功・履歴基線成功。root全件は実行中。#177手続実統合後の基線追随と最終版の限定確認を残す。

成績引継ぎ文書・台帳のSHA256はPO提示値とそれぞれ一致。未追跡は引継ぎ2＋候補4の計6文書で原状保存。現候補の配信層をT5/T6実装と混同しない。暦年は既決、登板/打者数など未裁定境界は既採用判断の追加照合を続ける。

### 成績の未裁定境界（既採用判断の照合後）

/root/o5_registrationのread-only照合で、次の意味を一意に定める既採用記録は確認範囲に見つからなかった。D1暦年、率のhalf-up・分母0null→−、既存得点/盗塁の計上原則は再裁定しない。CSV列・分割・表記の具体化は委任内で進める。

| ID | 具体例・選択肢 | 推奨・影響 |
| --- | --- | --- |
| MVP-D02 | 5試合区分を公式/練習へどう対応させるか。A=公式official+semi_official、練習open+intrasquad+other。B=公式officialのみ、練習残4キー。C=公式official+semi、練習open+intrasquad、otherは合算のみ | AをMVP判断案として提示（全5キーを2群に分割できる）。名前だけで採用はしない。全シーズン成績の母集団が変わる |
| MVP-D03 | 登板: 投手として出場し0球で申告敬遠だけを記録。A=投手出場試合1件、B=実投球あり試合だけ1件。再登板を別件に数えるか | A、同一試合の再登板は合計1件を推奨。0球牽制アウト等も同じ出場基準。登板件数が変わる |
| MVP-D04 | 打者数: 2-0で投手交代し救援が四球。A=既存責任帰属（前任1/救援0）、B=打席終了時投手（前任0/救援1） | Aを既存A-2との整合案として提示。A-2自体は走者責任なので自動適用しない。一般標準TBFの断定は根拠にしない。投手別打者数が変わる |
| MVP-D05 | OPS: 3打数1単打、四死球等なし。A=丸め前出塁率+長打率を最後に丸め .667、B=表示済.333+.333=.666 | A推奨。既存half-up/分母0規則を適用し、先頭0・注記は委任で具体化。成績値が変わる |

根拠: 正本183行の5区分、483行は投手交代表示、A-1（0除算/全試合区分）、A-2責任帰属、A-3出塁率/長打率、FR-022のOPS未定義注記。候補decisions.mdの推奨を承認事実として流用しない。

## Must要件ごとの接続状態（初回対応表）

提供部品の存在と正式受入を分ける。下表の『候補』は実接続/正式受入を意味しない。個別の正式受入証拠がないものは未受入とする。

| Page ID | 実装場所・供給単位 | 接続・検証状態 / 残件 |
| --- | --- | --- |
| MVP-FR-001 | develop: api/routers/auth.py、frontend LoginScreen/authStore | チーム共有認証部品あり。今回リハーサル経路未検証 |
| MVP-FR-002 | develop: repositories/roster.py、api/schemas/roster.py | 名簿部品あり。作成/開始への名簿供給と実画面接続未検証 |
| MVP-FR-003 | #174/#175、隔離6ddbc341/b4b8aaf2 | strict codec接合100成功、固定resolver operation69成功。実作成API/DB/画面未完 |
| MVP-FR-004 | U-R1 #173、新5 / U-G1 | 初期権利候補。開始同一取引と再取得の実接合未完 |
| MVP-FR-005 | U-F8 GameScreenPitchEvent / T1 / U-S1 sync | 封鎖UIと同期核部品。実T1計算・Port・保存接合未完 |
| MVP-FR-006 | U-F8 GameScreenSubstitutions / T1/T2 | 交代/特殊進行の候補。7/9回・延長・cold/TBの実製品受入未完 |
| MVP-FR-007 | U-F8 GameScreenUndo/PastCorrection / U-G2 / U-X1 | 候補あり。訂正後状態再導出・成績再集計接続未完 |
| MVP-FR-008 | #153 T2基盤、post-153/TSK545候補、U-G1 | 終了/再開/再終了の実接合未完。MVP-D01のみ新意味回答待ち |
| MVP-FR-009 | U-S1 durable provider F1〜F3、端末キュー | 候補部品。全通常操作の通信断継続は未受入 |
| MVP-FR-010 | 同provider/端末保持、開始時事前取得 | 未送信保持/再起動復元の実画面故障検証未完 |
| MVP-FR-011 | develop sync/apply.py、U-S1/TSK506 | apply核とHTTP候補。実登録/通知/耐久provider/結果不明・再送の受入未完 |
| MVP-FR-012 | U-R1新6、U-S1最終同期 | 通常交代の実2端末・旧権利拒否未検証。緊急交代をMVP受入へ追加しない |
| MVP-FR-013 | U-F8 live display/閲覧入口 | 保存済み版・最終更新時刻・10秒更新の実API接続未完 |
| MVP-FR-014 | U-F8スコア表示、T5、成績配信 | 公式試合成績の製品提供未完。fixture表示だけを完成にしない |
| MVP-FR-015 | 暦年整合4517a33e、T5/T6、成績配信候補 | 暦年は既決。方式/固定ベクタ/投影/集計未実装。D02〜05回答待ち範囲を区別 |
| MVP-FR-016 | U-D2/FR031 | 毎球/プレイCSVの製品実装なし。成績CSVとは別資源 |
| MVP-FR-017 | 基本成績配信候補/新CSV契約 | 製品実装なし。画面と同一対象版・集計条件を維持して供給予定 |
| MVP-NFR-001 | 実画面入力/単一計算 | 実機250球以上のp95/入力15秒測定未実施 |
| MVP-NFR-002 | 同期/サーバー確定時刻 | p95 5秒以内の実負荷測定未実施 |
| MVP-NFR-003 | 保存済み閲覧版 | 保存→閲覧10秒の同時負荷測定未実施 |
| MVP-NFR-004 | 1チーム3試合×記録1+閲覧10 | 同時負荷/15万プレイ規模は未検証 |
| MVP-NFR-005 | iPhone/iPad/Windows Chrome・Edge | 実機未実施。幅調整/ブラウザエミュレーションと区別 |
| MVP-NFR-006 | RLS/認証/記録権 | #174隔離DBでoverride/GUC不一致拒否5件群の一部を実測。全入口/旧端末/複数タブの受入は未完 |
| MVP-NFR-007 | 既存認証・HTTPS運用 | 秘密/鍵新発行なし。チーム用HTTPS配置・運用公開は未実施/委任外判断対象 |
| MVP-NFR-008 | codec拒否/停止/故障表示 | codec100、段階起動DB5の部分証拠あり。保存/同期/CSV/バックアップ全経路は未完 |
| MVP-NFR-009 | 同一取引/apply/冪等 | 規則配置途中故障の全取消を実DB確認。同期イベント/投影/冪等台帳の実原子性・二重適用0件は未受入 |
| MVP-NFR-010 | 運用バックアップ/実復元 | 日次外部バックアップ/RPO24h・アクセス制限の実運用証拠なし |
| MVP-NFR-011 | 復旧世代/RG1/D4 | 設計・候補あり。実台帳/端末保持回収・突合を含む復元演習は未実施 |
| MVP-NFR-012 | 画面自動escape/CSV無害化 | 既存規律維持。実CSV実装後の数式注入/保存XSS回帰と実入口確認は残る |

## 継続運用と連絡（同一台帳へ集約）

- 2026-10-23 PO補足『CIは40分程度』を受領。CI全件はこの所要を前提とし、同じ入力の再実行・短間隔pollを避け、独立作業を継続する。
- #177是正版c32439d7、第2回独立差分レビュー0件。新証拠 https://github.com/masaki1025/pitchlog/pull/177#issuecomment-6364693623 。実無認証API照合成功。GitHub生成マージ候補8e764b48（親1ab/c324）の隔離worktreeでtenant-boundary checkerとcore-guardを実行してexit0。raw単親HEADでPR受理modeを直接実行した際の2親要求拒否は、検査省略で回避せず実merge版で確認した。
- CI run39952551462はcore-guard/tenant-boundary等成功、harness全件待ち。旧run39950625656のCI設定変更起因失敗は履歴保持。是正はCIバイトの基線復元によって外部凍結差分を空にしたもので、8資産の再受理/検査弱体化をしていない。
- P6既存threadへ受領通知を送付。宛先01a15952-4e55-77f1-975b-1b41649d7660、期待値/封印内容の返送や新blind導出は依頼せず、版/資格/手続だけ照会。送付済・受諾未確認。
- 550既存thread01a133de-8208-7660-9105-136ced77cb05へ#176/TSK550主担当引受と並行編集停止維持を通知。追加編集/検査/公開は依頼していない。送付済・受諾未確認。
- T5/T6責任は主担当へ移管済み。現在のD-14-m例外はT1/T2限定なので、T5/T6に同一TS artifactを使う場合は限定正式追補を先行する。手書きの別言語計算/集計で迂回しない。公開artifactはpingのみ、formatter/公式27項目snapshot投影は未提供と確認した。

P6から引継ぎ受領・独立担当継続の実返信を受領。候補編集なし、期待値/封印内容の返送なし。版/範囲メタデータは `/home/ymdms/projects/pitchlog-tsk564-p6-report/20261023-independent-v20-lead-receipt/INPUT-SCOPE-METADATA.json` に固定された。正式受理には権限/対象commit-hash-ID-射影/未検証面/曝露留保/正式case・7.7対応と必要な未曝露担当が残る。受け手を主担当と明示したが、現時点はメタデータ受領だけでP6結果の正式受理・全成立ではない。既存純入力再発行の所在と版だけを追加照会し、新blind導出/比較は依頼していない。

## 再開後の固定点・完走結果

ユーザーの中断/モデル変更希望で編集を停止し、その後『作業を再開』により再開。中断前のCSV計画書は未作成だったため、再開後にrootが計画起案・独立レビュー・承認を行った。

- #177: 最終c32439d7、CI39952551462は全必須成功（frontend/backendは変更検知に基づきskip）。独立差分レビュー第2回0件、証拠6364693623と再照合し、PO委任によるCodex主担当判断で通常merge。正式develop統合は **28c5aee685b3cbf9792e903577fbe79d2dffd7d7**。本人確認や署名を代記していない。
- #178: develop28c5をeceedb4bへ通常mergeで取り込み、O5宣言/登録と#177検査を接合。共有正式凍結資産の値変更なし。接合後core対象356件成功/14.99秒、root Ruff/ty・文書20件0違反・正本突合成功。最終差分独立レビューと新証拠を固定し、必須CI後に通常mergeする。
- ローカル全件（O5コード719bb308・記録追記後、#177取り込み前）: **29,907 passed / 3 failed / 2 skipped / 2596.86秒**。2失敗はbackend/.venv/bin/python FileNotFound、測定スイート1失敗は子スイートexit1。成功へ読み替えていない。uv sync backend後、専用の使い捨てPG17.11（127.0.0.1ランダムport、利用者DB非接続）を用いて同3件だけ再実行し **3 passed/14.45秒/exit0**。単一の全件成功実行を主張しない。ログ: cache/pitchlog/mvp-o5-root-tests.log と mvp-o5-mutation-rerun.log。
- CSV共通部品: root実装7d3b2f18、最終候補762796ee（develop28c5取り込み）。54件成功・独立再実行54成功。最終HEADの第2回独立レビュー0件、diff SHA256263d5918ec978586f779184c38ea6c5d5d5cec1854945e73831248b8da9ad82c。正式資源の提供/実Excel安全性/HTTPダウンロードは未完。
- 新109入力の独立導出候補: fork_turns=none、配布dirだけを許可した/root/p6_fresh_derivationがAを封印。derivation SHA256 bb4fef2d5c73b204f4bfd6feb33329ad562ed824c99850e3fee120150584528d、seal SHA2565434712153b8fc733b78cfcee2e50f8242fc8faa0100076f1913b0ac442f1e76を主担当再計算で照合。可視材料に作者期待値/分類への曝露なしとの資格記録、潜在手掛かり不在は未保証。**新agentという理由だけでblind/P6正式成立を認めない**。対象は旧v2.15/ADR0.8/1e57ff02の109だけ。旧P6担当へBの機械比較を別役割として依頼、旧成果/新封印を変更せず、不足を推測補完しない。新版T1/T2全体成立へ広げない。
- U-S1旧担当から引受了解・停止維持の実回答。F2はe41f7c35の隔離構成承認済み、正本/DDL-ACL/必要7.7のゲートが残る。P7結果ID/wire/O4優先/J6型ACLの最終受理は未取得、B+D/除外Aの方針採用だけを確認。F2準備全体を止める条件へ広げない。

MVP-D01〜05のPO回答は未取得。待ちを承認に置換しない。Goal管理は再開時点でpausedを返すため、実作業の再開と自動継続状態は区別してユーザーへ通知した。
