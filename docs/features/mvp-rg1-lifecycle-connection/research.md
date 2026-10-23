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
