# RG1製品成功の接合メモ

2026-10-24、rootの担当引受。base547d199eの製品2関数はstateを読んだ後常にfalseを返す。作成65598dadのservices/game_creation.pyはread_rg1_open(scope)で停止し、POST /gamesはscope外で503へ変換する。ここにD4/V12/台帳・初期権の依存呼出しはない。必要な供給は安全なRG1成功/制限制御経路であって、記録開始・全台帳故障検査ではない。

台帳作者creation_pathはidentity専用observerの維持、別能力の実closeProof照合、close commit後からauthority INTENT→同期PG→CONFIRMEDまで再openを防ぐ実lease保持を必要境界として提示。通常enroll/startupだけで自動openしない。rootが新sourceをこのworktreeへ分離し、既存authority packageの同時編集は行わない。現在はplan/researchだけでsource・正式資産未変更。

実business identityはsystem_id/databaseだけでなくpostmaster started_atも束縛する。台帳作者の追加確認: business postmaster変更は同systemの古いbackupとの識別ができないため、別の実close/drain proofを受理するまで停止する。ledger pair/daemonの正常再起動照合と混同しない。現source未追加・plan独立確認前。


## ステップ1：新3sourceの先行宣言

実JSON/全guard function・class ASTは正式base547と同一。追加層を新3source×sync/recording/tenantへ回転し、旧initial2pathの定数・登録/拒否履歴を保持。旧初期付与の歴史的試験は同じ当時の宣言を明示したCLI/照合器で検査する。既存SCRIPT monkeypatchの挙動も保持する。旧登録の末尾固定は後続が増えるため、旧blockの位置/順序と全JSON差分の完全照合へ分けた。

初回全coreは398成功/10失敗/1error/212.75秒。9件は既存git/subprocess30秒timeoutで、T1候補のcore同時実行も全体遅延していた。2件は本root追随の実不具合（合成repo内へのimport pyc混入、default引数がSCRIPT monkeypatchを固定）として修正。タイムアウトは伸ばさず、一時ファイル/宣言CLIの対象だけ是正した。新/影響54件の直列検査54成功/6.51秒後、専用tmp/2workerの最終core全件409成功/26.84秒。Ruff/ty成功、guard関数/拒否変更0、実JSON/source製品追加0。原失敗と最終結果はcache/rg1-lifecycle-connection/core-step1*.logへ保持する。


## ステップ2：別JSON登録

先行05631c1c/標準diff66c131c0は非作者resolverが0/0/0、独立56成功/7.01秒と追加4拒否変異を確認。rootは承認済み順で6c338328へJSON1fileだけを別commitし、新3sourceを三領域へ完全追記。旧paths/順序/guard/metadata保持、製品sourceはまだ不存在。実547→6c338の履歴検査は547を返し、追加後全core409成功/28.16秒。

その後、正式175がa10bcd5eへ通常統合された。現branchは当時の547固定であり、次の製品候補化前に新正式基線を通常mergeしてAPI read登録/受理履歴を保持し、追加層を回転する。新しい意味の承認を繰返さず、変化した値と接合だけを再確認する。


## ステップ3最初の固定候補

実Unix clientと制御SQL7関数を追加。clientはroot管理config/inode、kernel peer UID、有限frame・閉じた型、同DB四要素とscopeの同一channel生存を要求する。未設定は常閉。SQLは専用actor/owner、controller key1/open key2、同DB/同PID/actorの実lockを要求し、未確定closeをopen/release証拠にしない。SQL単位19成功、client単位39成功/2.35秒。これはtransport/SQL構造の候補であり、実fresh API、controller本体、scope保持、実PG ACL/競合、実UI新規201はまだ未提供・未検証。旧open行を安全成功へ読み替えない。


## 同scopeの実借用・確定順候補

正式175/a10を通常mergeした1e8f9f12で3core競合を旧全pathsと新RG1層の完全和に解消。初回408成功/2失敗はpreparingの旧宣言末尾を現在宣言と誤比較したfixtureで、当時の宣言へ固定して410成功/25.83秒。非作者rightsは全31guard関数/classの本文・AST不変と実a10履歴predicateを独立確認し0/0/0、局所62成功/7.15秒。証拠review-rg1-main-core-1e8f9f12-evidence.json SHA f4965633bc7b63f5294a3de44e915a6821aaddcd4b80029c5617b2e2b8c960da。拒否・タイムアウト・旧レビュー系列を保持する。

既存RG1の2token/2factory署名を保持し、固定scope_bindingだけを追加。実scopeは同じSessionの固定観測を使ってborrowし、commit直前に既存FOR SHARE NOWAITと実peer生存を再照合する。scope終了ではPGのcommit/rollback/closeの後に借用を解放し、結果不明を正常201へ補完しない。通常read/authは借用しない。初回59成功/1失敗は旧exact2登録の期待追随不足で、新しい1読取だけを追加し旧bool2関数のexact期待/拒否を保持した。client/SQL/登録67成功/1.26秒、Ruff/対象ty成功。6件のscope順序probeは正常/本文失敗/生存喪失/commit不明/release不明/read無借用を確認する単体検査であり、実authorityや実DBの安全成功には数えない。

controller daemon/fresh供給・実DBとscopeの接合・app startup設定・正式認可/tenant metadata/7.3/7.7は未実装または未接続。正式登録が未受理の候補を正式成功にしない。画面で新規作成した試合の201/GET/reload証拠はまだない。


## controller候補・実SQL接合と結果不明是正

56b8の非作者rights全文はP0=0/P1=2/P2=0。PG commit/rollback/close例外でも通常releaseする問題と、test_function_operations_boundaryの旧2ID期待残りを実再現した。証拠review-rg1-client-56b8f654-evidence.json SHAd813ce95f013a18a824ec6cbd34045874936e89bfbf11639e7c5ae0c72f3d4c9を保持する。PG終結例外は新abandonで同channelをACKなし切断し、controller側の未終端・閉鎖へつなぐ。本文失敗でもrollback/closeが確認できた場合だけ通常release可。commit/rollback/close不明3経路とEOF検査を追加し、新1登録だけのexpectationを追随、既存2登録/DMLは保持した。後発非作者再確認は別条件として残る。

controller候補はroot保護の非秘密configからsocketをbindし、専用UID/空補助group/NoNewPrivsへ降格、実business Unix peerのserver UIDとactor session/current_userを照合する。同じPG sessionで排他lease/close commit/実識別を取得し、固定製品packageのDurableLedger(endpoint).fresh_activation()が実供給する8fieldとlive fenceだけを照合してopenする。app borrowはkernel UID・同channel・同DB識別に束縛し、継続中のfence/PG lease喪失や未終端を停止へ写す。既存socketのunlink・自動再fresh・globalcloseProof/epoch/nonzero restoreは提供しない。実supplier未供給をfakeで補完しない。API startupはrootclient設定未配置ならreadを維持して書込常閉、内部制御/PG不明はscope終結後に固定503で非漏洩。機械manifestは候補宣言で正式登録の代用ではない。

同じSQL SHA8b8b36e9ea97bf2f22c0f6c9dcdc44e692e0d56d6bd38dd8a19ce1e157a26f99を実正式S3/実PG peerへ適用し、専用1シナリオ13.98秒成功。appの制御6関数/DML/membership/TEMP拒否、実binding、旧open/app偽同key/別PID/別DBの拒否、再入lockcount、未commitcloseからのopen/release/read拒否、実共有lock排出、server再起動後のstoredopenとlease消滅を確認した。旧read2の常falseを保持し、これを実freshや新規201と混同しない。途中のport再取得/psql行protocol2失敗はsourceを変えずtest transport是正。全所有container回収済み。

初回SQL試験は共通autouseが既存admin接続を使用し、試験placeholder role unusedのCREATE後にrole接続失敗、finallyのDROPまで例外なく実行した。隔離境界違反として原setup1error/0call/0.70秒を保持する。削除の直接catalog証明は追加照会禁止により未取得で、source/finally完遂による確認である。以後test processの既存ADMIN/ROLE DSN環境を除去し、局所autouseは所有S3の実admin/app/actor認証を全て検証する。既存DBへの追照会/追加適用なし。非作者側の別DBファイル誤指定は未markの専用disposable経路だけで既存admin経路に入らず、exit130/51成功1失敗を保持、自前container残存0。markerだけに頼らず通常検査を実非DBファイルへ限定する。

最終局所149成功/1.30秒（6実非DBfile）、Ruff/対象ty成功。新controllerの実fresh接合、起動後の実scope/正常201/画面reload、正式authz/tenant生成・正本7.3/完全7.7/最終独立/全CIは未成立。source固定後に隔離組立へ進み、候補成功と正式develop成功を分ける。


## data-model1.2の限定確定ゲート（開始）

対象はdata-model3-2のRG1制御2主体/同Session読取/安全な成功条件とロール数参照だけ。固定直前HEAD91e90cf15abbb253f4915a2f7acb3274784965a4のdata-model1.1を改訂基線とし、初回敵対レビュー適用条文はapprovedハーネス1.19、条文コミット91e90cf15abbb253f4915a2f7acb3274784965a4（同時in-review化の第一親、暫定）。初回開始時に版を照合し固定する。finalize-doc手順を使い、今回PO指示4/5の独立subagent・委任承認代替を適用、一般規約/検出/対象paths/拒否条件を変えない。基本枠/起因/採否/(B)送り/反映周を既存7.3どおり保持し、人間本人の確認/署名を代記しない。初回全文レビューと採否はこれからであり、approvedではない。

91e90最終限定非作者0の証拠review-rg1-controller-e280fd18-91e90cf1-evidence.json SHAb2f888ab216ac8c2d290a26e15f5eafafd14c6b71b246eb045c182cc24ec9aebを受領。別の固定隔離候補69836e33ではcsv_reviewがactualsupplierc07→rootbind/20002降格listen→実app20003 PG peer/binding→borrow/held/3.2秒idle保持/release→再borrow/abandon→PGclosed/lease消滅/保護journal未終端拒否まで1成功48.59秒で確認した。sourceは供給2候補のbyteを保持し、fakeauthority/常trueを使わず、全所有資源回収済み。test/supportは隔離枝だけ、正式受理/HTTP201/画面成功ではない。


### 正本ゲート第1回の採否・反映1周目

9038全文/基本2回枠の第1回はP0=0/P1=1/P2=1、否決。非作者rightsの証拠review-rg1-data-model-9038cba8-evidence.json SHAa53ce2facfc763f64d60306a0a7a362854aabde03e363787cf3a7e5e239a62daを受領、適用approved1.19/91e90条文は受付時同一。P1・起因・(-): data-model1.2履歴行の『実装時に確定する範囲』欠落を採用し、有限DDL/適用撤去/認可tenant生成/正式7.7値/実DB HTTP検証を既存step3/4で具体化する境界を履歴行へ追記した。7.3-7の条文/当該行の典拠を照合し、plan参照で代替しない。P2・非起因・(-): 3-2の規則解決owner2行重複を採用し、既採用の明示列grant/ロック/owner隔離/本文DML禁止/GUC限界を持つ行を残して重複1行を整理した。新意味や権限を追加せず、(B)送り/不採用/未終結は0件。採用反映を伴うのでcounter0→1、反映1周目とする。次は本反映差分+影響節の第2回を同適用版で実施する。付随read2コードの独立0/0/0と非DB22成功/2.28秒は正本の否決と別に保持し、正式201/7.7へ転写しない。


### 正本ゲート第2回・PO委任による確定

da78a862/差分8714419cの第2回（反映差分+影響節、基本2回枠）は可決0/0/0。前P1/P2は採用反映で双方解消、未終結/不採用/B送り0。非作者rights証拠review-rg1-data-model-da78a862-round2-evidence.json SHA6813167e3f0733a986c5a3b9dc77fa05abf45f02a7f5df74f1a7da3d0a44f7e3。適用harness1.19/91e90を最後まで保持し、反映回数1を増やさない。

2026-10-23T22:36:26.379898+00:00、PO委任によるCodex主担当/root判断。対象da78a862の最終反映差分/採否/既採用列grant保持/actor分離/同scope実保持/未供給fail-closedを確認し、今回PO4/5の委任範囲でdata-model1.2を確定する。旧正本/既決意味の再裁定や本人署名の代行はない。approved反映後の正本SHAa8dbd05c75957a9d4c8ca48018c84ffab09621cabef6a4298cc60f071b9c6126、索引は現行1.2/2026-10-24へ追随し旧全履歴を保持。正式role/function/tenant生成と完全7.7/CI/正常201は別条件で未達、正本確定だけで製品完成を主張しない。
