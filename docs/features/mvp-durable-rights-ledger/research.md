# 復元外台帳adapterの起案調査

## 固定入力と今回の権限

2026-10-24、rootから限定計画起案を委任された。新branch/pathの同名不存在を確認し、実develop `31194a39c9083bbef6c14bde19c24a3e49d09f2e`から`feature/mvp-durable-rights-ledger`を新設した。今回所有/編集は本featureのplan/researchだけ。source/正式JSON/正本/DB/資格/共有環境は変更していない。

最新PO範囲は主担当の指示による。PO4/10は合意済保証を変えない型/API/保存/失敗具体化と隔離環境構成をrootへ委任し、PO3で運用責任者山田正輝が明示済み。したがって旧提案の未承認表記だけを理由に、二台同期台帳の隔離ローカル実装/故障検証まで新たな人間待ちにしない。外部方式を厳密保証を満たす技術候補として限定計画・非作者レビュー・root判断へ出す。運用配置/共有DB/有料資源/新運用秘密は未実施の別ゲートである。

## 一次原典と読取所見

| 固定HEAD / path / 行 | 所見 |
| --- | --- |
| 旧`0aaa22e09d7e1a0301d03f7c63d188d9bba76844` / `docs/features/ur1-recording-rights/plan.md:94,180–187` | 旧方式案未採用と親9ステップを保持。新5の初期付与primitiveと新7復元・新8実Port接合は別責務 |
| 同 / `connection-contract.md:42,53–55,71–79` | 事前非ロック、直前共有ロック、復元開始はRG1行だけ先行commit。復元外発行源・起動epoch照合・不可分解除の設計根拠 |
| 同 / `d4-decision-proposal.md:7–16,22–28` | 同期二台/成功応答前WAL保全/非同期降格なし/旧primary fence/両系最新不明で発行停止。配置費用を仮決めしない。nonceで保証を弱めない |
| 同 / `backend/src/pitchlog/recording_rights/initial_grant.py:72–113,275–287` | ReservedGeneration、DurableGenerationSourceのreserve/claim/current_recovery_generation、RecoveryEpochFenceのgeneration/assert_held。外部epoch共有lockを業務commitまで保持する。実adapterではなく参照Protocol |
| 実`31194a39c9083bbef6c14bde19c24a3e49d09f2e` / `docs/design/sync-protocol.md:1769–1774` | 復元後非再利用・連続復元・全旧世代fence・回収/閲覧条件と新D4同時確定。対象0件なら発行0件解除可、preparingには解除時初期権なし |
| 同 / `backend/src/pitchlog/db/recording_rights/models.py:41–60` | RG1現物はsingleton/stateだけ。外部epoch/復旧manifest/完了証明の物理提供はない |
| 同 / `contracts/authz/product/function-bodies/functions/FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid).sql:15–24` | tenant一致とFOR SHARE NOWAIT後も常にfalse。stateをopenへ直接書くだけでは通常成功しない |
| 同 / `backend/src/pitchlog/repositories/rg1.py:69–86` | true以外を拒否し、既存2token経由。同契約を試験専用openへ置換しない |
| 同 / `docs/development/dev-harness-design-2026-08-07.md:533–543` | 7.6唯一の決定表。外部永続資産/復元境界の構造的改訂は同一PR内7.3、実装追随だけならPRレビュー |

上記旧commitはgit showの参照だけで、履歴輸入はない。旧P6/期待値/封印は閲覧しない。旧173/156の受理・レビュー履歴をこの新計画へリセットしない。

## source/検査器の現況

基線のpsycopg 3.3.4は既存依存で、新しいdriver依存は不要。既存tenant-boundary base-allowlistは完全修飾symbol/signature/API ID/正例fixtureの対応を持ち、psycopg接続/実行を自由には許可しない。新adapterにもexact登録と拒否試験を適用する。既存方式で表現できないAPIが判明した場合の検査器改訂は本計画で先決めせず、具体差分を主担当へ戻す。全ソース検査の除外はしない。

core JSONを読み、backend/tests/db/*は対象3領域、正例fixtureはtenant-isolationに既存被覆があることをfnmatchで確認した。新packageと単体契約試験は3領域とも被覆が不足し、正例fixtureもsync/recordでは不足する。従ってsync/record各3件・tenant2件の領域別追加層を宣言→別JSON登録する4ステップ構成とした。実装開始前に実base登録を再確認し、正常initial候補供給後も旧登録を削除せず本層だけを追加する。

local検証は実primary/実standby/別業務clusterを構成し、同期応答・standby flush・primary停止後保全と連続業務復元を測る。local同host試験を別故障領域での本番耐久性証明としない。運用配置未実施を理由に、adapter/契約検証の着手まで止めない。

## 起案時の未達

この新計画はレビュー0回・未承認。実台帳/role/schema/複製/試験はまだ作成・実行していない。実DB・Dockerを起動していない。正常initial供給・実Protocol接合・7.3/7.7実値・本物のRG1成功・全非0復元/実Port/HTTPは未達。新意味/可用性保証の弱体化・新運用秘密は採用しない。作者`/root/independent_review`は後の独立レビューを兼ねない。

## 起案検証

docs-statusは21文書/違反0、局所plan同期は指定base31194でexit0。両新規文書の末尾空白/NUL検査、git diff --checkは成功。core被覆は現JSONからfnmatchで独立に照合した結果を上へ記載した。実装・DB・複製・故障試験は未実施であり、文書検査を製品成功へ読み替えない。固定後は書込を停止し、非作者の計画レビューへ渡す。

## 計画第1回独立レビューと採否

/root/resolver_ledger_plan_reviewの全文レビューはP0=0/P1=1/P2=0。実31194 policyに新branch対象がなく、core_guardが新実PRを拒否するP1をrootが採用。planへ実番号取得後の同PR/branch1組追加とデータ自体の非作者最終確認だけを追補した。全旧target/authority/失効/拒否は不変。第2回限定差分確認前で、まだ計画未承認/製品未実装。正本順序自体は7.6根拠に一律違反とはしないとの非作者判定を保持する。

計画第2回限定反映差分/影響は非作者/root/resolver_ledger_plan_reviewの可決0/0/0。rootはplan末尾に対象SHA/日時/PO委任採用を記録。計画承認で運用設備・費用・共有DB・新秘密・正本確定/正式値受理・RG1成功が成立したとはしない。製品は未着手で個別step指示後に進める。

## 承認ステップ1/4: 正常initial供給と台帳追加層の宣言

rootの個別指示を受け、承認`6288dfaab7aa58089d929172906c307f6eb7ccf2`から正常initial供給HEAD `95d766f5d20234b1d534538b96fc369eda1cc6f1`（PR180）を通常mergeした。供給mergeは`b1ab75cac62984106222c4ec51d0f1ec03a35d2c`、手動競合0、旧f48/0aaaを直接merge/cherry-pickしていない。これは隔離供給であり、実develop31194へのPR180統合済みとは記録しない。

merge直後はcore JSON/guard/旧試験/initial source/test/policyをsupplier byteと照合。権威履歴は26prefix＋180の計27件・末尾masaki1025/pitchlog#180、全202snapshotもsupplier blobとbyte完全一致だった。以後は本stepの宣言/既存core試験と本researchだけを変更し、initial/frozen assets/policyへ追加編集していない。

### 実供給Protocol

固定sourceは95d766f5の`backend/src/pitchlog/recording_rights/initial_grant.py`、SHA256 `c20d596ba80a7c9e792a472ddde295a261b0dee2977627e7f0391765bdca59c3`。`DurableGenerationSource`はcurrent_recovery_generation()→int、reserve(attempt_id, tenant_id, game_id, start_request_id)→ReservedGeneration、claim(同owner tuple)→None。`RecoveryEpochFence`はgeneration:intとassert_held()→None。ReservedGenerationはgeneration/recovery_generationとtenant/game/start_requestへ束縛する既存不変値である。本stepではProtocolを実装/変更せず、後続adapterの実署名接合の固定入力として保持する。

供給initial試験SHA256 `3f1009973bd890ce3ac6507117ec2227555d57ec4c7e8f4c9a009902acec8cdc`、供給policy SHA256 `86397671d61aaa9bafda562c0b1450db9a5ab68bec9ce4947e28e4d38cbe0d66`。これらもstep中byte不変。実台帳/role/複製/運用鍵/実Port提供をこの供給成功へ読み替えない。

### exact8追加と局所比較基線

新追加層は計画どおりsync-protocol/recording-rights各3patterns（専用package、contract試験、専用positive fixture）、tenant-isolationは前2patternsの計8追記分を宣言した。実core JSONは不変で、SHA256 `e555432f14c87524e5c3bf2bda86fa55b55ed59635345449713b662468b3d159`。新ledger package/contract試験/positive fixture/DB試験とsupportは作成していない。

initialのexact2×3登録は据置き層として保持する。旧initial段階の合成試験は当時の追加層を明示し、旧宣言の隔離checkerで実CLI/共変更拒否も残した。initialが末尾層から据置きへ移るため、旧試験の「末尾2件」だけは「一意な連続ブロック/宣言順」の検査にし、source/test実在・全3領域捕捉、旧全paths/順序保持を外していない。

実origin31194はinitial未統合のため、そのまま比較すると旧initial登録を取り逃した差として拒否される。局所core試験の比較元は、本feature planへの供給merge第2親95d766f5をGitの変更不能な親関係から一意に導出するhelperへ揃えた。無関係な可変branch先端や未登録をfallbackで許可しない。供給mergeを一意に特定できなければ試験を拒否する。テスト内に新しい実SHAを直書きして固定基準を増やしていない。

手動局所照合でhelperの導出値が95d766f5と一致し、verify_area_path_baseline(supplier95d,HEAD)は受理。対してverify_area_path_baseline(real31194,HEAD)は`sync-protocol.paths が merge-base の据え置き層と宣言済み追加層に不一致`を引き続き拒否した。これは期待する未統合差であり、局所試験greenを実PR/実developのgreenへ読み替えない。製品guard全関数/classのASTは供給95dと完全同一、共変更predicate/委任検証/BASELINE_DEFINITION_PATHS/人間確認条件の変更0。

### 検証結果

core全件 **411 passed / 26.43秒**（旧381＋新30）、失敗/skip/timeout0。登録前不在、別JSONのみ、将来のpackage/contract/正例実在と全登録、片側実在/未登録/部分/片側領域/対象外/順序反転/重複/旧削除/置換/未宣言/tenantへの余分なfixture登録拒否を確認した。合成Git履歴の宣言→別JSON実CLI、新8登録のJSON+基線定義同commit拒否、将来3実行資産の各単独変更の必須確認拒否/記入済受理を検査した。新実行資産は合成tmpにだけ作り、実wtでは不在を確認する。

root全体Ruff/ty、docs-status21件/違反0、design propagation/doc coverage、供給mergeb1abを局所baseとするplan sync、git diff --check成功。今回の検査に失敗版はない。core全件や静的検査は一度ずつの対象実行で、backend/DB/複製/故障試験を起動していない。

宣言/既存試験2pathsのfull-index binary差分（供給mergeb1ab→step1）SHA256 `77b18f66306102223198408f28826164fb2bfb69dcc4661469ba4123c511672b`。core_guard.py SHA256 `ac0dfbc97d492226a4a0172d2b9d9857b01f17c22c89f2efdc0d073bed23835d`、test_core_guard.py SHA256 `e4f0d09c9fa795a3238600f4820b6924edfe5138a0bfac368ebea21e00078999`。step1commit後にHEAD/全差分SHA/変更集合/局所履歴predicateを引渡しへ固定する。

JSON登録step2、ledger source/正本7.3/7.7/policy新target/新PR/pushは未着手。供給先が正常initialであることと、実originへの統合・運用資源・秘密発行・共有DB適用・MVP完成は区別する。旧レビュー/初回P1policy不足→第2回0の履歴と全未完条件を保持する。

## 同step1の比較基線是正（中間74c36a75を保持）

最初のstep1は`74c36a750938efbf5884d9d612e6a178ee2824ee`としてローカルcommit済み、未公開だった。rootのWIP確認で「全旧試験を供給95dへ固定し続けると、統合後に新しいorigin/develop基線を検査しない」不足が指摘され、全採用した。rootの個別指示により74c36a75と中間411成功/26.43秒を保持し、amend/rebase/force pushせず、同step1の是正を別commitへ記録する。これは計画scope内の試験helper是正で、製品判定/API/source追加ではない。

供給OIDのGit一意導出はそのままに、比較元選択を分離した。毎回の実origin/HEAD merge-baseが供給95dを含む場合は、その実merge-baseを選び、統合後の新しい共通基線保護へ戻す。供給未統合の隔離段階だけ、実merge-baseが供給95dの祖先であることをGitで検証して95dを局所比較に使う。独立分岐/検証不能OIDはfail-closed、固定供給への無条件fallbackはない。全旧比較呼出しと新実設定試験をこの選択へ接続した。

追加4例は、隔離段階の供給選択、供給統合後の新しいactual基線保持、独立分岐拒否、不明OID拒否。最終版core全件は**415 passed / 25.34秒**、失敗/skip/timeout0。是正後の全core対象実行はこの1回だけで、中間411成功を新版に転用していない。root Ruff/tyも成功。先の段階は所有2pathsの静的検査と最終root全体を確認しており、総計1回だったとする意味ではない。

実測時originは31194a39、actual merge-baseも31194a39、供給は95d766f5、選択した局所比較元は95d766f5だった。未改変の製品verify_area_path_baselineはsupplier95d基線では受理し、real31194ではsync-protocol.paths不一致を引き続き拒否した。全製品関数/class AST・JSON byte・供給initial source/test/policy/history27/snapshot202は保持、新ledgerのpackage/contract/positive/DB試験/supportは実wtで全て不在を再確認した。

是正test_core_guard.py SHA256 `f436e4a508525e80e77e22857a74b8b7c6654c3930f7efbc69e2fb72200059bb`。中間74c36a75から試験だけのfull-index binary差分SHA256 `673fe4c699ace35182028aa016d9e7aa37ec890de9a0eba5c955882e94464a5d`。core_guard.pyの宣言は中間版と同じ、製品判定の変更0。最終HEAD/全差分SHA/中間保持は引渡しで固定する。実develop未統合・step2以降/正本/正式7.7/policy新target/運用資源/push/PRの未達を保持する。

## step2のJSON候補と登録後fixture不足（未コミット）

rootは最終step1 HEAD7f75a2f1を確認してstep2だけを許可した。実core JSONへsync/record各3、tenant2のexact8末尾追記を行い、全旧paths/順序/guard_paths/metadata保持・宣言/試験/source/policy不変・新ledger全資産不在を機械照合した。JSON SHA256 `714b0605e1818b2fe2110f81110f2b6b5e3d0ab5153ce011e863617ecbe79aa2`、7f75からJSONだけのbinary差分SHA256 `ad9ba78bf65fe1fe5118fa6c56b85c82c88353ba42e7d5e01f3d6bec334230e9`。root Ruff/tyは成功。

登録後の全core試験は409 passed / 6 failed / 27.62秒。失敗はtest_durable_ledger_core_each_single_future_asset_requires_checkのchecked2×3pathsだけ。同試験がmake_repo_with_actual_core_areasで新8登録済みの実JSONを読み、さらに無条件commit_area_path_changesで同8を再追記したため、合成merge-baseのsync-protocol.paths重複で本来の未記入/記入済確認へ進めなかった。実wtのJSONには重複がなく、製品guardは重複を正しく拒否している。

試験は今回の編集所有外なので勝手に変更しない。rootへ、登録前/後を識別し未登録時だけ合成追加する最小是正を、step1の試験のみ別commit→step2 JSON commitの順に分ける案を報告した。JSON＋基線定義試験の同commit変更を再発させない。今回の6failedを履歴に保持し、stage2成功/完了とはまだ扱わない。step3 source/DB/正本/7.7/policy新target/push/PRは未実施のまま。

### root採用: step1試験setupの先行是正

rootは上記6failedの原因を確認し、plan契約を変えず「試験のみstep1是正commit→保全JSONを復元してstep2commit」の順を個別指示した。候補JSONを`/home/ymdms/.cache/pitchlog/durable-ledger-step2-preservation-2a8fx3op/`へmanifest付き保全し、SHA256 `714b0605e1818b2fe2110f81110f2b6b5e3d0ab5153ce011e863617ecbe79aa2`を確認後、実JSONの当該pathだけHEADのe555432fへ戻した。

対象試験は合成repoの実configを既存assert_durable_ledger_registrationで検証し、exact全8登録済みなら二重追記しない、未登録なら従来の別JSONcommitで追加する形へ是正。部分/重複/対象外は同helperが拒否し、任意欠落をskipしない。将来3資産の未記入確認拒否/記入済受理のassertはそのまま保持した。登録前JSONで当該6例を実行し6成功/3.41秒、対象Ruff/ty成功。先行是正commitの変更は既存core試験と本researchだけで、JSON/製品guard/sourceは不変。保全候補復元後の登録済み全core結果は次のstep2記録へ分ける。

### step2登録の最終結果

先行試験是正commitは`4bf26c3fa3605822e38907027d13c471cb892904`で、変更集合はtests/test_core_guard.pyと本researchのみ、JSONなし。保全JSONのSHA256を再確認してbyte完全一致で復元した。登録済み実JSON状態での最終core全件は**415 passed / 27.02秒**、失敗/skip/timeout0。この登録済み最終全件は1回で、中間409pass/6failを消去していない。登録前の対象6成功と、登録済み全415成功を別の段階として記録する。

最終root Ruff/ty、docs-status21件/違反0、design propagation/doc coverage、局所plan sync、diff検査成功。実JSONはsource glob/contract exact path/positive globをsync/record各3・tenant2の計8だけ追加し、全旧paths/順序/領域/guard_paths/metadataを保持した。新source/testは依然不在、宣言/既存試験/source/policyは先行是正4bfからbyte不変。step2commitはJSONと本researchだけとし、commit後の局所95d受理/実311拒否/履歴共変更0を引渡しで確認する。stage3adapter/SQL/DB/正本/7.7/policy新target/push/PRへ進まない。

## 独立先行登録レビューP1: 元供給mergeの実discovery是正

非作者/root/resolver_ledger_plan_reviewの先行登録全文レビューはb146f033に対してP0=0/P1=1/P2=0、独立415成功/27.84秒。対象b1ab→b146のbinary差分SHA256 `8f797abdcee4cc6fc61a04a6b4e9007b11d30ffaae7232ea3241ce969a6a3a9c`を再計算して一致した。旧レビュー/中間74/6failedと採用履歴を保持し、このレビューを416版の成功へ転用しない。

P1はsupplier discoveryが「planあり第1親/planなしsourceあり第2親」の全mergeを集めるため、正常供給のあとmainにinitialが統合され、branchがmainへ通常追随すると、元supplierとmainの2候補を返す問題。415成功では実discoveryを通す正常追随履歴を覆っていなかった。rootは全採用し、step3より先にtesthelperだけの同step1是正commitを指示した。

実Git回帰を追加し、supplier導入→main通常統合→branch通常追随を作った。実discoveryのcacheを更新間で明示破棄し、古いcacheで失敗を隠さない。source未修正でこの新1件を実行し、追随後の候補数2によるassert失敗を再現した。修正は「sourceが第1親に存在せず、第2親で初めて供給される元merge」だけに限定する条件の追加。元supplierを一意に導出し、統合後actual merge-baseへ復帰することまで同回帰で確認する。独立分岐/不明OID/部分登録/既存拒否は保持する。

修正後root Ruff/ty成功、全core **416 passed / 28.43秒**、失敗/skip/timeout0。今回はstep3のProtocol/inventory/同期取消調査だけで、新package/DBsupport等の実WIP資産はまだ作成していなかった。従って新資産を削除/隠さず、同wtの固定是正版で全件確認した。製品guard/JSON/source/正式資産/policyはb146byte不変、commitは既存core試験と本researchだけとする。

修正test SHA256 `fd610845f7b7c0986078ad77ea7670a4a5d835dda1ebd2295ef4b78e596bd462`、b146から試験だけのfull-index binary差分SHA256 `514fb1cda0a148359868b7a5a5576ec7acad2f736b5a1792e57d81591f91a7c1`。HEAD/全差分は引渡しへ固定し、その後root指示済みstep3の独立部分を継続する。取消APIのinventory不足は別の最小追補/独立確認待ちで、未知memberを素通りする実装はしない。


## 実資産出現後の先行core試験の順序是正

step3で実package/contract/正例が出現した接合検査は408 passed / 7 failed / 1 error / 273.66秒だった。6 failedと1 errorは全て既存Git/guard subprocessの30秒期限超過。重い実DBとcore auto並列を重ねてしまったため、以後直列・core -n2とし、既存timeout/判定を緩めない。backend同時版もprimary起動25秒期限超過で40 passed / 7 setup errors / 93.60秒、DB call未実行であり成功へ代記しない。

残るcore1件は実在後の全集合検査がglob入力順のcapturedとsorted(files)を比較していた試験setup不足である。製品matched_pathsは入力順を保持する。rootが最小是正を許可し、比較だけをsorted(captured)==sorted(files)へ変更した。要素数/重複を含め同一リストのexact比較であり、登録前/片側/partial/範囲外/未捕捉拒否・対象path/製品guard関数/JSONは一切変えない。今後も同種の機械的setup是正だけを別commitへ分離する事前許可を受けた。

同wtにはstep3の未stage source/fixture/契約候補WIPがある。この是正commitは既存core試験と本節だけ、JSON/新package/資産を含めない。step3実DBの中間/失敗記録は別のWIPとして保持し、後続のstep3固定時へ戻す。対象回帰結果は引渡しへ記録する。

是正後の台帳core対象35件は`-n 2 -k durable_ledger`で **35 passed / 13.88秒**。既存core試験Ruff成功（既存docstring連結warningのみ）。全coreはstep3最終候補で直列に一度まとめ、未実施をこの35件で置き換えない。


## step3実装中の正常pairと故障検証

承認plan追補bdfe27cf（取消API限定）はstep3へ供給された。依存追加なし、実clientはpsycopg3.3.4/libpq180000/cancel_safe capability成立。170000未満/不明capabilityは接続前拒否する。私有helperは`_cancel_commit(connection: psycopg.Connection[Any], timeout: float) -> None`、許可APIは`PSYCOPG_CONNECTION_CANCEL_SAFE`だけ。既存inventory駆動の型/alias/保守member検出で対応でき、取消検出のためのchecker本体変更は不要だった。新ID/保守member各1件と既存ID全順序を保持し、base許可は接続/固定操作/commit/取消のexact4関数・4正例へ限定した。

新packageのDDLはepoch共有ロック行と高水位更新行を分け、外部fenceを保持しながら予約を行える。claimは同owner/current epochに一度だけ、制御roleのepoch前進はCASである。全6関数はNOLOGIN owner/固定search_path、PUBLICとapp/controlの直接DMLは剥奪する。単一initial供給のReservedGeneration/DurableGenerationSource/RecoveryEpochFenceを直接importし、型コピーや常時成功発行源を作らない。

専用実primary/物理同期standby/業務別clusterの3コンテナ・3volume・1networkを各実行が所有する。公開済み試験専用の固定非秘密素材だけを使用し、運用秘密/TLS/署名鍵は発行しない。portはloopbackの専用番号、継承DSNは使用しない。既存verify_connection_identitiesを保持し、module専用fixtureのDSNを明示供給して実admin/app認証主体の検査を通す。後始末は自分が作った資源だけをfinallyで行う。資格文字列を本記録へ転記しない。

初回実DBは3 passed / 1 failed / 59.57秒。同期取消後のstandby再起動でDockerの自動公開portが変わり、fixtureの旧port待機が失敗した。製品成功条件は変更せず、起動時にOS選択のloopback portを固定して再起動にも同番号を使うfixtureへ修正。次の契約20+実DB4は24 passed / 35.52秒。DDL更新後にmanifest hashを追随し忘れた中間版は契約1 failed / 0.11秒・DB未実行として残し、実DDLのhashを再固定した。

実DBをACL全数/同期設定不一致/replay遅延/成功直後primary停止へ拡張した版は7 call成功 / teardown 1 error / 40.91秒。停止前の共通identity実接続が切れた後にlocal fixtureが暗黙COMMITしてAdminShutdownとなった。identity検査を無効化せず、当該module専用fixtureだけをyield/finally closeへ変更し、読取identity接続を暗黙commitしないよう是正した。最終再検査結果は後続へ記録する。取消新IDのexact正例/未登録receiver/alias/getattr/署名違い/他API拒否と既存正例・全拒否変異・inventory封印の限定対象は9 passed / 1.80秒。

正常pairでは実system identifier/timeline/postmaster起動時刻/peer addressとreplicator名を照合し、COMMIT後のprimary flush WAL以上を指定peerのflushと実standby replayで確認してowner-bound行を再読する。期限発火/取消発行後はCOMMITが正常に戻ってもoutcome-unconfirmed。接続を廃棄し、取消結果をrollback済み/未使用として扱わない。standby/primary再起動、promotion、identity不明は固定済みinstanceが発行を拒否する。

cold attach・正常process再起動・所有controller外の最新成功集合の証明供給Portは未提供である。2台が同じ古いbackupへ戻るとDB内sysid/epoch/高水位の自己整合だけでは最新性を証明できない。新constructorを運用のcold再開承認へ使用した、またはfresh pair試験を全adapter復元保証の完成へ置換したとは主張しない。後続に必要なのは、既存運用責任者に拘束された実制御主体から、対象system/timeline/起動identity、既成功累積集合/高水位/epoch、旧primary実停止状態、証拠の非巻戻し前後関係を同一取得で検証してライブ借用するPortである。型のauthorityと非巻戻し元が未提供なので、単純bool/任意JSON/自己署名を採用せず、新第3永続資産や秘密方式をこのstepへ追加しない。step3全DoD/step4/実RG1/本物Port/MVP完成は未達を維持する。

局所source検査で、新adapterの必須Protocol/generation署名にTB002が13所見発生した。既存initial47のsourcehash限定免除は別fileへ効かず、DB API許可もこれを解除しない。名前を隠したりProtocolを複製せず、adapter単一file/hash/exact所見と既存負例/censusの最小追補をrootへ返した。この追加のchecker/資産実装は未承認の間待機する。既存initial47/正式27履歴/202snapshot/policy/全親review・中間/6failを保持し、未受理checker赤を成功へ読み替えない。

### step3接合の再検査と固定点（正式提供未達）

重い検査を直列へ戻した後、契約20+実DB7は27 passed / 39.88秒、COMMIT後最初のprimary再読故障の秘匿/未確定回帰を追加した契約21件は21 passed / 0.21秒。さらに並列予約の実attemptを保持して旧epochの実claim拒否を検査し、他owner claim拒否・bigint MAX発行/次回枯渇拒否を加えた版は契約21+実DB7で **28 passed / 39.24秒**。sourceはfaa1ab04e2282a8654bedffd7053cb9062d9257d6d6d58488863d6b850bd1e90。この実DB版で全所有3コンテナ/3volume/1networkをcleanupし、既存共有資源へ触れていない。実identity autouseを通したままでteardown errorも0となった。

core最終直列`-n 2`は **416 passed / 36.16秒**。上記408/7/1と35対象結果を保持し、既存期限を緩めず再確認した。root/backend各Ruff/ty成功、docs-status21件/違反0、supplier95dを局所比較とするplan同期成功、runtime生成check成功。source未変更の既存長時間census/fullbackend全反復は実施しておらず、最終必須CIへ残す。origin/developがPR180の547d199eへ実統合されて95dとtree同一になった事実はrootから受領したが、実origin参照の更新/正式7.7受理をこのWIPで代行しない。

取消callbackのschedule遅延を再点検し、callback未実行でCOMMITが実期限を超えて戻る負例を追加した。旧faa1版は **1 failed / 21 deselected / 0.19秒**（OutcomeUnconfirmedを出さない）を再現。既承認の「期限到来後は見かけ上の正常戻りも未確定」の範囲で、monotonic実期限も判定する最小source是正を行った。最新版は **22 passed / 0.26秒**、backend Ruff/ty成功。追加のclassはtimer schedule遅延/故障分類の単体再現用だけであり、実source/実同期耐久性の成功証拠へ代用しない。影響する実同期取消1件の再接合結果は後続で追記する。

最新source SHA256は`53bdb9d54b9fa5ab0ece6787ab4824dfc02e9afbeea2a8d14ad132779ca2758d`。exact13所見JSONはrepo外cache `/home/ymdms/.cache/pitchlog/durable-ledger-tb002-53bdb9d5/findings.json`（SHA256 `f1929e42effce198d3abd2eb2a0d1727fc74eecb1faac61f2e63d688a97e067b`）と同dir source byteへ固定しrootへ渡した。旧faa1の同様cacheも保持。いずれも正規sourceの現所見であり、独立P6資料/封印期待値を読まない。TB002 checker/censusへの新免除実装はroot追補判断まで変更しない。

old inventoryの全API/memberと全順序を機械照合し、追加がcancel_safeの1ID/1保守memberだけであることを確認。initial source、core JSON、policy、正式履歴27行/202snapshotを保持する。変更は候補source/exact許可だけで、正式row/snapshot/policy新target/正本7.3はstep4後続・未受理である。

最終53bdb9d5版の影響実同期取消だけを直列で再確認し、**1 passed / 6 deselected / 29.03秒**。実standby停止→有限COMMIT取消→未確定→起動identity変更拒否/primary予約残存を再検査し、全所有資源をcleanupした。通常7件を含む28成功はfaa1版、最終53b版は契約22成功と影響実DB1成功であり、同じ全件完走と代記しない。実origin/developは共有ref更新後547d199e、実merge-baseは95d766f5で、製品verify_area_path_baseline(actual merge-base, HEAD)は95dを受理。局所供給fallbackだけによる成功ではなく、統合後actual基線へ戻った状態を確認した。旧311拒否はその時点の履歴として保持する。

### 条件2限定追補の実装とstep3候補引渡し

root承認8bd071a820aaab97d3e57f45c57689b87dd7ca19を読み、非作者rights_replacement_reviewのscope限定第1回0/0/0と、53b sourceの免除なし13identity一致を受領した。これは最終製品コード全体の独立レビューではない。既存initial47/source hashを互換保持し、新adapter単一path・source hash・正の行番号/完全symbolの13exact-setをchecker定数と新専用登録へ固定した。欠落/余剰/重複・未知identity・別path/別SHAを契約読取で拒否し、sourceの改変は免除しない。別条件/DB APIの違反を同時に検出する。condition2 owner_paths/既存検出ルールは不変で、module全体の許可は増やしていない。

実censusは新sourceに対して旧anchor checkerの除去11identityと独立AST候補1identityを別々に導出した（checkerの現13件とは粒度が違う）。新明示キー`ledger_removed_checker`=`661033093b9db4a1e8a51933edeb9e7f44f3c3f042fab6d9f85b56885858edb2`、`ledger_added_independent_ast`=`1a1a72edad14d9742b621516fa4c03bb80b214b6fa7092325640f83edb2f31c9`へ固定。旧`removed_checker_43`/`added_independent_ast_18`とその値は変更0。新旧path間の移し替え/欠損/余剰/改変digestは拒否し、独立AST候補の実13所見への帰属も検査する。導出した全identityはrepo外cache `durable-ledger-census-53b.json`へ保存した。

- 新API/新条件2の登録・検出/拒否と既存正例/全拒否変異等: 20 passed / 2.62秒。
- 新旧scoped digest/条件2限定census対象: 23 passed / 54.16秒。
- 全sourceを実測するcensus主述語1件: 1 passed / 82 deselected / 105.85秒。長いcensus全83件は反復せず最終CIへ残す。
- 既存bypass試験file全件: **383 passed / 3 failed / 166.55秒**。3失敗は`test_repository_is_green`（7資産IDと履歴末尾不一致）と、base35→36/inventory17→18の`test_every_frozen_baseline_asset_has_a_valid_chained_history`各1件。正式未受理を検知した赤であり、試験期待や履歴を変更して通さない。source/登録の正負例は成功し、全件greenとは記録しない。
- 最終変更固定版core全件: **416 passed / 33.79秒**（-n2、DBと直列）。先行中間版の全失敗/35対象/36.16秒版も保持する。
- root/backendのRuff/ty、runtime生成check、docs-status21件/0違反、design-propagation、doc-coverage、局所95d plan同期、diff checkは成功。既存supplier source/core JSON/policyはbyte不変。
- 正式bypass CLIもexit2、理由は履歴末尾と7資産IDの不一致。未受理を成功へ写さない。

9資産/外部8の実候補射影はrepo外cache `durable-ledger-step3-projections.json`へ保存。実base95dに対して8資産の射影が変わり、frozen-inputsは同値。外部変更はchecker/census試験の2files。JSON本文の編集は許可済みbase/inventory候補だけで、他7JSON・旧27行履歴・202snapshot・policy新target・正式7.7は変更0。生成3の入力は不変で、runtime checkおよび既存契約読取で整合を確認した。正式identifier/完全値受理と必要生成/履歴/archiveの最終整合はroot所有step4へ残す。

固定source SHA256 `53bdb9d54b9fa5ab0ece6787ab4824dfc02e9afbeea2a8d14ad132779ca2758d`、DDL `acdc77b44f8557bc1006f270a7fbee80c65ab345a15287144439b4f8097f35e1`、manifest `7657e982cc525956d711501424749a6cf189703eefd5bc981b73af9922b37326`。PG17.11-bookwormの専用実primary/物理standby/業務cluster、psycopg3.3.4/libpq180000を使用した。新source53bの実試験は契約22＋影響取消DB1、先行faa1の通常全DB7と区別する。

このcommitは正常pairのsource/DB候補部分の保存であり、step3全DoD達成を宣言しない。cold attach/正常再起動の非巻戻しauthority、業務identityの製品観測主体、所有controller外のlatest集合証明は未提供。全復元・昇格/両系喪失の故障行列、正式正本7.3/7.7/最終非作者コードレビュー・全必須CI、実RecordingRightsPort/RG1/HTTP接合とMVPは未完である。push/PR/共有DB/運用適用なし、運用秘密/TLS/署名鍵の新発行なし。所有DB資源は全cleanup済みで、共有containerは不変更。

## 再起動authorityの製品依存化に向けた限定追補案

rootは5a321b6a受領後、cold attach/正常再起動authority/business identity観測主体を外部回答待ちにせず本製品が実装する依存として、既存plan/researchだけの技術追補を指示した。source/DB起動/正式資産を変更せず、既存source内の再利用箇所に限定して調査した。

`backend/src/pitchlog/authz/runtime_contract_generator.py:433`の`_atomic_write`は短書込ループとfile fsyncを持つが、witness/起動間flock/append-only/親dir fsync/INTENT照合は無い。生成物の置換・unlinkをwitnessへそのまま流用できない。現在adapterのbusiness identityはpg_control_system直読で、隔離business adminへ依存する。これを専用subjectと固定SECURITY DEFINER関数へ替える。既存`product_provisioning.py:558`のsession_user/current_user照合原則を再利用し、appへの権限付与やSET ROLEでの代用をしない。

`product_catalog.py:1257`のカタログ要求は宣言schema/table/function/role集合で絞り、`:292`の危険LOGIN検査も製品集合への権限/所有を調べる。したがって専用observer schemaと製品表/関数権限0のprobeを別manifestで検査する候補とし、既存56関数の値を先行で変えない。実S3不変と新role/function/ACL全数の実検証をDoDへ置き、衝突が出た場合はactual path/fieldだけ戻す。

候補は保護された独立volumeのjournal、SQLite WAL、第3PGを比較した。最小候補はLinuxの実append-only保護を持つjournalで、fsyncとdir fsync/期限付き単一writer lock/INTENTと結果記録を実装する。SQLiteや第3PGへ問題を移すだけでは古い復元の最新性は証明できない。hash鎖は破損検出であり、旧正常prefixの巻戻し検出器ではないことを明記した。DBとhost image復元からwitness volumeを分離し、workerに保護解除能力を与えず、連続性不明/全設備喪失では自動再初期化せず停止する。運用rootが旧witness imageを復元した事実までsoftwareだけで検知すると約束しない。

plan追補は別UID authority/実peer認証/既存Protocol借用、SQL provisional値→INTENT fsync→同期COMMIT/peer実再読→CONFIRMED fsync→ACK、未確定D4のquarantine/単調reconcile、実restart identity更新を具体化した。witness自身に別の世代算出実装を持たせない。callerのexpected集合やbool/任意JSONで復旧を開かない。最初の実装候補は`witness.py`+既存manifest/contract試験/researchだけで、DB/source53bの変更を後段へ分離した。実append保護が使えない環境の正例をstub/skipで成功にしない。

正常全lease終端後の再起動と、業務writerを持たないmutationのcrash照合から実装する。authority crashで失われたleaseをheldと偽らず、未終端leaseは実RG1 close/旧writer fence接合まで発行停止とする。既存4ステップ/全故障DoDを消さず、正常pair/fresh controllerだけで完成扱いしない。新設enrollは通常openから分け、既存導入のwitness喪失を新設へ読み替えない。署名鍵/運用秘密は追加しない。

参照した一次資料: [fsyncのdirectory要件](https://man7.org/linux/man-pages/man2/fsync.2.html)、[FS_APPEND_FLとCAP_LINUX_IMMUTABLE](https://man7.org/linux/man-pages/man2/FS_IOC_SETFLAGS.2const.html)、[Python3.12 flock](https://docs.python.org/3.12/library/fcntl.html)、[PG17 control data functions](https://www.postgresql.org/docs/17/functions-info.html)、[SQLite WALの保存/共有制約](https://www.sqlite.org/wal.html)。独立P6資料/封印期待値/.env/運用資格は読んでいない。

旧初回plan2回/反映1周、取消追補1回、条件2追加1回、coreの各P1→是正/中間失敗と最終416、5aのbypass383成功/正式未受理3失敗、全source/DB版差とcold attach未達の過去記録は全保持。この追補案はまだ独立追加レビュー/PO判断前で、製品コード変更を許可済みとは扱わない。

通常pushはrootが許可した中断復元点5a321b6aefa7d11700b67a90f5e2bfefdac7ced1だけを`feature/mvp-durable-rights-ledger`へ実行し成功した。番号用PRは作成していない。製品未完成/正式未受理のラベルとなる本文を維持する。本追補案commitはこのpushに含めず、独立追加レビュー用にローカル固定して引き渡す。

本追補の検査はdocs-status21件/違反0、5a比較のplan同期、diff checkが成功。製品/source/DB/正式assetsは変更0、DB起動/新secret発行も0。追補は独立追加レビュー/PO委任前の案として記載し、既承認部分の承認状態を新source実装許可へ広げていない。

## 保護journalの最初のコード小単位

root承認873ab82e504c6df9b501dff860416960758e2776に従い、`witness.py`、既存manifest、既存contract試験、本researchの4pathsだけを実装した。新DB/依存/API ID/条件2登録/正本/正式凍結資産/plan変更は0。adapter53b/DDL/initのbyteと旧manifest全fieldを保持し、manifestは`witness`項目だけを追加した。cold attach/authority接合を提供済みへ変えていない。

`ProtectedJournal.open`は既存root-owned/immutable descriptor、固定device/filesystem/inode/mountとentry、owner/mode/regular/link count、実FS_APPEND_FLとFS_IMMUTABLE_FLを検査する。rootおよび実/実効/saved UID/GID不一致・root補助group・CapEff/Prm/Inh/Amb/Bnd残存・NoNewPrivs不成立を拒否する。pathの各親componentをdirfd/O_NOFOLLOWで開き、root所有かつ書込を他主体へ与えていないことを確認する。normal openにO_CREAT/再enroll/保護flag設定・解除は無い。descriptorのJSONはbounded/重複・未知key/型/版を拒否し、appの期待集合を復旧証明へ変換するAPIは無い。

writer.lockの実flockを期限付きで取得し、同一process/thread内の利用も期限付き排他で保護する。journalは固定magic/format版/payload長/ordinal/前frame digest/checksumを持つ単一codecで、最大payload65536bytes、読取はbounded memoryのiterator。完全追記と実file fsync後だけFrameを返す。open時にはdescriptor/journal/lockのfile metadataと親directoryを実fsyncする。短書込/InterruptedErrorを処理し、追記/fsync結果不明はtypedな未確定とbroken writerへ写し、続行・truncate・勝手な末尾修復をしない。Frame ordinalは汎用log位置であり、D4算出/予約/claim/epochの別実装ではない。

最初に専用named volumeでkernel append属性を実probeし、`chattr +a`の成立と解除/volume cleanupを確認した。Docker driverはoverlayfsだが、選択したnamed volume上では必要な実inode保護を提供できた。Docker内のbase OSは既存`postgres:17.11-bookworm`を使い、PostgreSQLは起動していない。新test image/依存追加を避け、現在のPython3.12 runtimeと対象source一つだけをread-only bindした。`.env`/運用資格/署名鍵を渡していない。

実試験は、rootの所有fixtureだけがCAP_LINUX_IMMUTABLEでvolume内の保護を準備し、workerはUID/GID20001・全capability drop・NoNewPrivsで実行した。root directory0750、descriptor0640(root/immutable)、journal/lock0600(authority)で検証。worker自身によるappend保護解除/truncate/unlinkのkernel拒否、別app UID/解除能力を残したprocessの拒否を確認。別container/processのwriterを実flockで拒否し、終了後に別processで同じinodeを再openして実frameを読めた。I/O故障は実保護worker内のsyscall境界へ制御注入し、短書込と途中EIOは実ファイルへ部分書込する。物理媒体故障/host電断を実施したとは主張しない。

初回は既存22件を含め **56 passed / 34.36秒**、失敗/skip0。flockを時間sleep依存から親による明示解放へ強化し、manifest閉集合との対応を加えた最終版は **57 passed / 32.45秒**、失敗/skip0。実保護を無効化した成功stub/skipは使っていない。各full実行は専用volume1個・同時最大2container（準備/後始末込み24短命container）、全資源を所有名/labelで分離してfinallyで属性解除/削除まで完了。終了時の所有label付きcontainer/volumeは0。単体codecのpytest tempは既存の世代管理を使用し、共有DB/container/host設定を変更していない。

backend Ruff/ty・root Ruff/ty成功、diff check、docs-status21件/違反0、873ab82e比較のplan同期成功。新witness sourceの現bypass所見0、API/条件2の免除追加0。旧anchorとの差TB007の12identityも、現sourceのASTを使う既存census緩和述語へ全件帰属確認済みで、新しい検査意味/metadataを足していない。台帳core対象は **35 passed / 15.23秒**（-n2）。全core/fullbackend/fullcensusは同入力で反復せず、既存の最終CI条件を保持する。

witness source SHA256 `e20e957d04a689bd595d229f657db9bcb550f3b68f7092588403e689030bb1db`、manifest SHA256 `0ed2390848ef94c3494910ddadf8f8dabf57084f6964beaa285e302cb74cb0ea`。旧adapterは`53bdb9d54b9fa5ab0ece6787ab4824dfc02e9afbeea2a8d14ad132779ca2758d`のまま。旧全review/57より前の版別結果、正式未受理/bypass3失敗、step3全DoD未達を保持する。作者の局所検査を独立コードレビューへ数えない。

次に実装する製品依存は、実DB初回enrollmentの判定、別UID socket authority、INTENT→PG/同期peer→CONFIRMED→ACKの接合、quarantine/CAS reconcileと正常再起動identity、専用business identity subjectである。今回の汎用journalはそれらの代用ではない。全復元/非0旧writer fence/RG1/本物Port/正式7.3・7.7/最終独立レビュー・全必須CI/運用配置/MVPは未完。新署名鍵・運用秘密発行/DB起動/push/PRはこの小単位では0。

### 実authority接合候補（873ab82e委任、正式step3/全DoDは未完）

固定供給witness `1e4381f8a4e5aec3acc2350e0075d7533042cbde` とrootの権限明確化 `798df0ba` を親に、実root launcher→capability全除去/NoNewPrivsの専用UID worker→実SO_PEERCRED client→保護journal→実primary/指定同期standbyを接合した。witness byteは `e20e957d04a689bd595d229f657db9bcb550f3b68f7092588403e689030bb1db` のまま。元53b/5a候補・旧全レビュー・失敗・非作者witness限定0指摘/独立57成功と402破損拒否/正常2の証拠を保持し、本作者検査を独立確認とは扱わない。

公開sourceは `DurableLedger(endpoint: Path)` とし、直接DSN/呼出者expected set/fresh pairの構築を公開入口から拒否する。rootが一度だけ登録したimmutable配置と固定inode/保護journal、実専用business identity observerを照合する。新しい署名鍵/運用秘密は発行しない。実callback/providerの常時成功代用はない。実session_user/current_userとprimary/standby/businessのsystem identityを実観測し、通常process再起動/同一系統の両台帳旧backup復元では、journalのowner-bound成功集合を固定256件cursorとindexed lookupで照合する。未知行/未知highwater/不正履歴は修復前に拒否し、既知の不足/古いclaimだけを単調前進させる。未確定INTENTは実peerで結果を確定できる場合だけCONFIRMED、それ以外は同予約をquarantineして再利用しない。journalを全件RAMへ展開せず、複数回のstream読取で照合する。大規模journalの起動性能は今回未計測で、運用規模の性能完了とはしない。

予約/claimは実SQL結果をINTENTへfile/dir fsync→実同期COMMIT→指定peerのdisk耐久/可視owner-bound row再読→CONFIRMED fsync→ACKの順にする。COMMIT/ACKの不明を未使用へ戻さず、source再newで回避しない。shared RecoveryEpochFenceは実transactionと同一Unix channelに束縛し、業務rollback/commit終了まで借用できる。lease開始/終了も耐久記録し、切断/未終端leaseがあればlive/再起動の両方を閉じる。通常lease中の別channel予約/claimは許可し、lease全期間でwriter mutexを保持しない。SQL前にも実standby起動identityを照合し、peer再起動の検出をCOMMIT後へ遅らせない。

**実故障発見と是正履歴。** 中間実DBは2成功後、probeのbuiltin権限期待1件が失敗した。PG17.11の`pg_control_system()`には既定PUBLIC EXECUTEがあり、明示GRANT無しでもprobeは実効EXECUTEを持つ。PUBLIC一括revokeで製品全roleを変更せず、追加明示GRANTはownerだけ、新設schema/identity()だけPUBLIC剥奪とした。rootが798df0baでplanを明確化し、実効PUBLIC許可とprobe直接ACL追加0を両方検査する。canonical migration/製品認可を同専用business clusterへ適用すると、既存製品DDLによるPUBLIC CONNECT剥奪で初回enrollも拒否された（setup error、pytestのDB対象call到達0）。必要なprobe CONNECTだけをbusiness_identity.sqlへ追加し、TEMP/製品表/authn/appへの追加権限は0とする。fixture内だけの業務rollback用subjectは公開固定資格でCONNECT/TEMPのみを持ち、製品app/observerを拡張しない。

別の中間実測では、初回/台帳PG再起動の実同期確認が有限2秒で拒否された。primary flush/peer flush `0/3008000` に対してstandby replayが `0/3007570` で停滞し、次の実WAL時に `0/30094B8` へ進んだ。raw flush位置と最後のreplay record位置の差を同一と誤認した比較であり、旧53bにも存在した。期限を伸ばさず、`pg_last_wal_receive_lsn()`のdisk同期済み受信位置と指定peer flushの両方をbarrier以上とし、実standby上のowner-bound row/epoch可視性を別に再読する。[PostgreSQL17の一次資料](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-RECOVERY-INFO-TABLE)はreceiveを「received and synced to disk」、replayを最後に適用されたrecord位置と説明する。正常台帳PG再起動直後に次WALが無い区間も有限確認できるよう、control専用`confirm_state(bigint,bigint,bigint)`を追加した。authority自身がjournalから導出したE/H/countのCASだけを照合し、高水位値を変更しないUPDATEを実同期COMMITする。保護flockの下で一回enrollまたは未終端lease拒否後のattachにだけ呼び、live leaseへ突然排他epoch更新を入れない。appへEXECUTE/直接DMLは与えず、D4予約/claim/epoch advanceを行わない。control roleの既存epoch APIを公開sourceから開くこともない。

同中間検査でfixtureの管理/被検査接続をcontext managerの暗黙COMMITにしたため、意図したPG stop後のteardownがAdminShutdownで失敗した。既存と同じfinally closeへ戻し、identity autouseは実接続で維持した。旧journal-only manifest期待1件（56成功/1失敗）とobserver SQL注記後のmanifest hash未追随1件（47成功/1失敗）も保持し、接合manifest/hashを実byteへ合わせた。backend tyのfixture DSN型5指摘は実str検証で是正し、型強制で成功を偽装していない。

**版別実測。** no-op barrier導入後の実両台帳backup/restore局所1件は1成功/62.80秒。canonical business/実peer主体/製品表とauthn実拒否/実ACL/正常restart/reconcile/未終端leaseの中間7件は7成功/104.51秒。fence中の並行reserve、no-op CAS/不変、peer停止/再起動の拒否を加えた中間9件は9成功/130.17秒。発行前standby照合と高水位不変回帰を加えた9件は9成功/138.02秒。いずれも成功した版を旧53bや最終全DoDへ代記しない。root launcherのreaped済みPID再kill防止を含む最終版の対象結果は下記に追記する。

**検査登録と提供境界。** adapterの旧53b/exact13免除は未更新。最終sourceの免除なし全18 identityとsource byteはrepo外cacheへ保存し、rootへ渡す。新authority/witness所見0。新18件を見込みで旧13定数/登録へ足さず、旧initial47/source hash/43・18digestを保持する。正式9資産/8外部識別値、旧27履歴/202snapshot/policy/7.3/7.7はroot所有で変更0。今回のmetadataはpackage候補manifestだけで、未受理赤を成功に読み替えない。昇格・運用配置・全設備喪失・非0件の全業務復元/RG1・正式RecordingRightsPort/HTTP成功は未完。businessのpostmaster identity変更は実close/drain proof無しでは閉じ、epoch advanceは公開口で常に拒否する。business正常再起動/復元後の再開を、このsame-business-instance候補の成功へ広げない。

**次の小単位: fresh activationの閉read/lease不足。** 現公開sourceはepochとlive RecoveryEpochFenceだけを返し、検証済みenrollment/business metadataを返す口は未実装。追加候補署名は`DurableLedger.fresh_activation()` context→不変attestation(authority_id, business_system_id, database, postmaster_started_at, pair_epoch, highwater, reservation_count)＋live RecoveryEpochFence。実daemonの引数無し`fresh_activation_open`が、保護enrollment/全journalで過去INTENT・過去activation無し/未終端lease無しと、実同期pair E1/H0/count0を自分で照合する。一度限りactivation開始fsyncとlease登録の不可分境界だけwriter mutexを保持し、その後は同一実peer channelと共有epoch fenceを保持しながら通常D4予約/claimを許可する。caller bool/JSON/ID/expected setだけを証拠にしない。ACK喪失やin-doubt/PastActivationがあれば再new不可とする。単に復元後にDB行0を観測した場合はfreshとしない。root側の専用RG1能力はこの実attestation/live leaseと同一business identityを照合して初回開放する別単位で、今回sourceからRG1を開いていない。実closeProof/epoch advance接合はその後の未完依存として残し、他の実装の停止前提にはしない。

最終sourceはadapter SHA256 `57c7d9691f8a6058554fde80ece940e75318943675ad15db8b03f78472e198a6`、authority `574f1dc1fc6ec9d69f3008d9b02e135bfa17c89c64b1facf90f84b873737e73b`、ledger DDL `3a49fea19ef5f699a8bc20bfdb3fb67a26d0655bb4d912431deac0ff73ab60ef`、observer DDL `a3218c0484dcdc765b4c8bdb71ab98dd63ab10e98c39f370f1127dbb4f091beb`。18所見全identityとbyteは `/home/ymdms/.cache/pitchlog/durable-authority-tb002-57c7d969/findings.json`（SHA256 `0888daf0d64c62c1fbb3f388de610dbafdb35c4fda9839d143fde670065504cf`、同dir source.py）へ固定した。authority/witnessの現所見0。旧53b/exact13登録は変更0。

最終実DBは **9 passed / 137.70秒、skip0**。root launcherのreaped PID再kill防止/異常終了非0を含む同sourceで、実UID/peer/ACL/並行lease/peer停止/正常restart/旧両台帳復元/結果不明の照合/未終端lease拒否を通した。専用3PG＋authority、public fixture資格だけのclient、専用control/witness/data/socket/backup volumeとnetworkを所有して全掃除した。workerはauthority container内の別UID子processであり、別の共有daemonを起動/停止していない。実PGの対象外は従来の共有DB1台だけで未操作。contract **67 passed / 35.12秒**、metadataへadapter/authority実byte hash照合を加えた既存1対象 **1 passed / 0.29秒**。ledger core局所 **35 passed / 13.61秒（-n2）**。root/backend Ruff/ty、runtime生成check、docs-status21件/違反0、design propagation/doc coverage、diff check成功。長い重複fullbackend/fullcore/census全変異83件は今回反復せず、最終必須CIへ保持する。

全`backend/src`の旧anchor/現checker/独立AST censusは **125.37秒、1回実測**。added15/removed1966/current200/独立AST32の全実集合と既存宣言述語の拒否を `/home/ymdms/.cache/pitchlog/durable-authority-census-57c7d969/actual-census.json`（SHA256 `425e22488ee3d6038d6c7f266c429b41cdc40664d25563081e2389d8a131b49d`）へ保存した。既存test helperの実測/述語を無変更で直接呼び、検出結果や期待値を置換していない。旧hash登録のまま`ReservedGeneration`のreturn型identityがexact独立集合外となり拒否された。新18を同sourceだけで抑止した場合の未受理の集合射影は、ledger removed16/digest `0c2ddeb46d20c0abfaa5f1b1db9fa0264d3f1fa10ede8a154b5749b53c3c0ec1`、独立AST1/digest `1a8408514daa51b0e0ee16462bdcbcc28fe16a18a9ef0b5f36d66b2d227d7c6e`。同dir `proposed-exact18-census.json`（SHA256 `58861f5c8f59a80343710ee645dda3921ed3429a886bcb5545c8a3dff834716e`）は候補射影だけで、採用/正式CI成功ではない。旧initial removed43/AST18の完全digestは `a869a0d893090d8da4d6061ed7584ace69e016f69503d668947b7998cc7f7189` / `203cb5691221e841acb1db63f559b83b2f0743b8292bf46bcda2b49054980881` のまま。新exact scope/digestの限定非作者確認と必要plan整合はrootへ渡す。

今回の実replay停止はlocal COMMIT済みINTENTの実再照会→CONFIRMEDを検証した。COMMIT前の実process/PG abortでquarantine枝へ入る故障試験、全write/fsync/ACK kill行列、business PG再起動/復元後の実closeProof再開、昇格/全設備喪失/2回業務復元/非0件全fenceは後続に残る。これらを今回9件やcomponent57件で検証済みとはしない。通常enrollは一度限り保護配置と実空同期pairを必要とし、復元後DB行0だけをfreshと扱わない。fresh activationの製品接合口自体も未実装で、実preparing作成（D4/V12/初期付与無し）の前提へ台帳全完成を追加していない。今回checkpointを保存した後は編集を停止し、rootの限定非作者レビュー/次小単位委任へ渡す。

### fresh activationの限定計画起案（source b9固定を保持）

rootからb9 checkpoint/実9件・67contract・35coreと全census未受理拒否を受領され、既存4段階内の次小単位としてplan末尾へ追補した。今回は既存plan/researchの2pathだけで、b9の製品source/試験/metadataは変更していない。同版の全source非作者レビューと候補18 identityの限定採否をこの計画確認と混同しない。

実装可能な境界を`fresh_activation()` context→不変metadata＋同channelの既存RecoveryEpochFenceへ限定した。authority_id＋開始frame ordinalを一度限り識別とする。実genesis/現在のbusiness identity/同期pair E1H0/全journalのINTENT・不明・過去activation無し/未終端lease無しをdaemonが自分で検証し、開始とleaseの単一frame耐久化後だけ返す。mutexを全open期間保持せず、epoch共有fence保持中に通常reserve/claimを可能にする。H0/count0は開始時のsnapshotで、後続の合法D4を禁止する根拠ではない。body例外/切断は正常closeへ補完せず実未終端を保持する。終了fsync後のACK喪失なら耐久終了を事実として保持し、未終端へ改ざんしない。いずれのACK/終了不明も自動retryせず、正常終了も含めPastActivationから新freshを作り直さない。RG1 open成功をclient bool/DTOだけから記録せず、rootの実consumerが業務commit終了までleaseを保持する。

b9のbindingを読取照合した結果、descriptorは汎用filesystem証拠、immutable configはbusiness DSN locator、worker内`_business`は実system/database/postmasterをpinするが、`_metadata`によるENROLLED/ATTACHEDはsystem_id/started_atの2fieldだった。よってnormal再起動時の当初database束縛は不足しており、同cluster/同postmaster内の別DBへroot configを差し替えた場合の区別を保証していない。この具体残件をroot/b9独立レビューへ返した。追補は新enrollのgenesis/attachmentへ実databaseを記録し、normal admissionでも全3field一致を要求する。欠落旧genesisの自動補完/再enrollはせず、既存journalをfreshへ昇格しない。汎用witnessや新しい秘密は不要で、既存observerが返すdatabaseを再利用できる。

実装は追加の独立限定確認とPO委任後。新しいDB起動/secret発行/署名/TLS/正式資産編集は0。COMMIT前abort→quarantineの実故障試験を含む残件、全DoD/正式step4/人間本人確認・署名/P6留保と過去レビュー/失敗を維持し、今回の文書固定を製品fresh成功や全MVP完了へ広げない。

### b9全sourceレビューP1=2の是正候補（fresh本体は未追加）

非作者resolverによるb9固定版の全sourceレビューは **P0=0/P1=2/P2=0**。証拠 `/home/ymdms/.cache/pitchlog/reviews/durable-authority-b9d5c457-review.json`、SHA256 `b3060ad41edaf78cb68ae3f63f816ba7ed6277ccf6f367162e9f8a4a33289e4e`をrootから受領した。独立48非container成功/18 identity一致/他条件0と旧initial47/43・18保持は、2P1を検出した同版の結果として保持する。旧b9の作者67/9成功をこの修正版へ転用せず、b9を未是正のまま全source可決とは記録しない。rootは両方を採用し、既承認step3内の通常是正を委任した。fresh計画00d2の限定非作者0/PO委任承認a74238b6は別系列で、fresh API本体はこの是正に含めない。

**P1 database binding。** 新enrollの保護ENROLLED/ATTACHEDに実observerのdatabaseを含め、normal admissionで当初のsystem_id/database/started_at全体を照合する。worker中の実identity再読も維持した。旧database欠落genesisは起動拒否し、config DSNから補完/旧frame書換/自動再enrollはない。実PG同cluster/同postmaster内へ別databaseと同じ正規observerを用意し、実peer/session/currentを保ったままroot fixture設定のdatabaseだけを変えて拒否させた。旧2field genesisは別の所有fixture dirへ保護された有効frameとして作り、startup拒否と旧/元journal byte不変を確認した。fixtureが作った不正旧imageを製品再enroll成功とは扱わない。両負例の後に元の正規設定へ戻した実startup/epoch読取も成功した。これに伴い起動拒否時に残るbind準備用0770が正規再試行を妨げないよう、既所有authority.pyの終了処理でroot run dirを0755/fsyncへ戻す通常cleanupを加えた。未知journalの解除ではない。

**P1 temp shadowing。** ledger SECURITY DEFINER全9関数を`search_path=pg_catalog,pitchlog_ledger,pg_temp`とし、state/highwater/reservationsと%ROWTYPEをcanonical schemaで完全修飾、統計viewもpg_catalogへ限定した。[PG17の安全要件](https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY)に従い、implicit pg_temp先行を防ぐ。PUBLIC TEMPは剥奪しない。実app/controlがtempの同名3表に偽epoch999/高水位8888/予約を作り、definerへの有効namespace USAGEと各表ALL ACLを成立させた。旧方式のunqualified session lookupが実際に偽値を読むことを攻撃前提の正例とし、全9 definer関数が正規値/正規owner行だけを読み書きし、temp値を変えず、不正epochのreconcileも拒否することを検証した。制御原語の正当なepoch/reconcile更新はtransaction内で試しrollbackし、全実canonical E/H/countの前後不変も照合した。関数owner/EXECUTE閉集合は維持し、PUBLIC TEMP実効ACLの存在も実カタログで確認した。

最初の修正版影響実DBは **9成功/1失敗・163.77秒**。失敗は攻撃fixtureの`GRANT USAGE ON SCHEMA pg_temp`がGRANT文のschema aliasとして解決されない準備不備で、製品関数の攻撃結果へ未到達だった。actual pg_my_temp_schema()へのdefinerの有効USAGEとtemp表への実ACLを確認する設定へ是正し、期待する安全性を緩めていない。修正後のdatabase/旧genesis/実temp攻撃対象2件は **2成功/83.87秒**。最後に同sourceの影響全件は **11 passed/172.03秒、skip0**。全所有3PG/authority/client・volume/networkを掃除し、共有DBは未操作。旧b9の9成功とこの11成功を別版として保持する。

新sourceはadapter SHA256 `bba427c7cfcc5706a09f8e1a86b2bb98ca183afe0633f061263e2b4b9f9f39f1`、authority `8451e90c828de5b10ca9f866a6153129b0ccd70678f578f0537ac38119121060`、ledger DDL `fdbc4b159895fc13020a5147f48ef1010420f2c4b65a4bc96f80cd3e28a7c5fe`、manifest `ba438509bb601bba27f7386421e2f9f4afef941de43fb29771f27983aaa0a0ff`。witness/observer/単一Protocolは旧byteのまま。adapterの免除なし全18所見はb9とsymbol/scope/code/message多重集合が一致し、別条件0、authority所見0。完全line/hash付きJSONは `/home/ymdms/.cache/pitchlog/durable-authority-p1-bba427c7/findings.json`（SHA256 `d816436a330e96311422f03799e9dc22f0bb0f2946a93a9cfd4477ea3c41bed5`）、同dir source.pyに保全した。旧53b/exact13・initial47/旧43・18digestと正式資産/履歴/snapshot/policyは変更0。旧全source census125.37秒の未受理拒否はb9版のまま保持し、今回fullcensusを反復/成功代記しない。fresh追加後の最終source/独立AST/census/exact scope採否は後続rootゲートへ渡す。

修正版の非container契約は **48 passed/1.00秒（real witness19件は今回未反復）**、ledger core局所は **35 passed/13.19秒**。root/backend Ruff/ty、docs-status21件/違反0、design propagation/doc coverageとdiff check成功。初期のty/fixture準備失敗と旧レビュー全数を保持する。通常database admissionとtemp遮蔽の作者是正/実回帰が到達した候補であり、新版の非作者code確認・fresh_activation本体/実RG1 open・公開epoch advance/全復元/正式7.3/7.7/最終CIはまだ未完。

### fresh APIの最小source checkpoint（残故障/影響検査は継続）

rootから86b12005の限定非作者レビュー **0/0/0** と独立48非container/0.45秒を受領した。証拠 `/home/ymdms/.cache/pitchlog/reviews/durable-authority-p1-86b12005-review.json`、SHA256 `bf96621c6966cb554e92fb88c467e623cba7b982339d0a1f72b04d7904c9ec31`。b9の初回P1=2と版別成功/失敗は保持し、このreceiptをfresh新sourceのレビュー可決へ代記しない。承認a74238b6の個別委任に従い、公開`DurableLedger(endpoint).fresh_activation()` context→`(FreshActivationAttestation, RecoveryEpochFence)`を実装した。metadataはfrozen/slotsの8field（authority_id、activation_ordinal、business_system_id、database、postmaster_started_at、pair_epoch、highwater、reservation_count）。ordinalは実開始frameの既存uint64範囲でありD4 allocatorではない。本人署名/新secret/key発行はない。

daemonが再利用した単一genesis/history検査・実business identity・同期pair E1H0/予約0・過去INTENT/activation/未終端lease無しを確認し、activation_open frameとleaseを不可分にfile/dir fsyncしてから返す。開始前後の実fence確認、同channelのcheck/closeを使い、body例外は正常closeへ補完しない。開始後の不明は未確定として閉じ、終了の耐久記録を失われたACKに合わせて書換えない。writer mutexは初期境界/短いmutationだけで保持し、open全期間は実共有epoch fenceで保護する。metadataの0は開始時snapshotで、後続の正常D4予約/claimを妨げない。DTO/識別値だけを認可証明にせず、root consumerがこの実factory/contextを所有する。SQL/observer/witness/初期付与Protocolと正式資産は86版から不変。

最初の局所実DBは **1失敗/36.27秒**。fixtureのdocker clientにinteractive stdinが無く、metadata受信後のbodyがEOFで例外終了したため、host側排他lock期待を満たせなかった。実interactive pipeへ是正し、lock期待/認可/source期限を緩めていない。修正後の局所 **2 passed/80.87秒・skip0** は、実metadata/同channel fence、凍結DTO、caller追加proof/既存active leaseの拒否、host実PGの排他epoch lock拒否、lease中の3並列reserve→claim、正常終了後の再fresh拒否、および実ACK読取遮断→未終端/live/startup拒否を確認した。全所有3PG/authority/client・volume/networkはcleanup済み、共有DBは未操作。非container契約は追加14件を含む **62 passed/0.49秒**、Ruff/ty成功。初期wire境界ty指摘はexact dict確認後の境界castとDTO runtime検証を維持して是正した。

root controller接合用の最小support入口は既存`isolated_authority_database()`→`AuthorityDatabase`。`.database.network/.business/.business_socket`、`.control`（endpoint `/control/public/endpoint.json`）を使う。authority server UID/GID20001、許可client20002:20002、business socketは`/business-socket`、専用probeは実OS witness_authority(20001)→PG peer pitchlog_ledger_identity_probe。genesis/ATTACHED businessはexact `{system_id,database,started_at}`、system_idはPG::text、databaseはcurrent_database()、started_atはpg_postmaster_start_time()::textの未再整形値。独立シナリオは旧所有cluster/contextを閉じてから別の新cluster/witnessを作り、既存pairをfreshへresetしない。

このcheckpoint時点で残るrestore0/body例外/pastINTENTの新3ケース、既存11件の影響検査、最終独立source確認/新exact source登録/census、root実RG1 controller接合と全DoDは未消費/未完。これらを上記2成功へ読み替えず、同sourceの直列検証を継続する。最初の実COMMIT前abort→quarantine等の既存fault行列/非0全復元/正式7.3/7.7/最終CIも維持する。

### c07 source不変の追加実証receipt

checkpoint `c07f508df6bdcec815e311e5a81c25feeba08610` と同じadapter byte `10906d157598b21f730665965c4231a64bfdfcadf057288cdd5e60e0255190e2` で、残fresh3ケースは **3 passed/146.53秒、skip0**。旧両台帳backupへ実復元した後に実H0/予約0でもPastActivationから再freshを拒否し、通常D4は継続可能だった。body例外は正常終了へ補完せず実未終端/live/startup閉鎖、既存INTENTもfresh拒否を確認した。先行2件と合わせ新5ケースが到達した。同sourceの既存影響11件も **11 passed/131.76秒、skip0** で、normal database/旧genesis拒否・PUBLIC TEMP実攻撃・再起動/両台帳復元/旧normal lease拒否を再確認した。各群の所有3PG/authority/client・全volume/networkはcleanupし、DBslotをroot/csv_reviewの実controller接合へ引き渡した。共有DBは未操作。検査によるsource再初期化や同pairのfresh resetはない。

core局所は **35 passed/14.42秒**、root/backend Ruff/ty、runtime生成check、docs-status21件/違反0、design propagation/doc coverage、commit後plan同期成功。非container62/0.49秒は同sourceの先行結果を保持し、旧67や旧b9/P1版の検査を新版完走へ転用しない。generic witness19実containerは同一witness byteのため今回反復していない。root controllerは別単位で実freshへの接合を進めており、そのRG1成功を本ledger5+11成功へ代記しない。長寿命consumerにはendpoint.timeout未満の同channel assert_held heartbeatとassert/closeの直列利用が必要で、既存有限期限を延長して隠していない。

同sourceで全backend/srcの旧anchor/現checker/独立ASTを **100.06秒、1回実測**。現checkerのledger所見は単体/全snapshotとも **TB002=17、別条件0**。全集合added15/removed1973/current199/独立AST32、既存宣言述語の拒否を `/home/ymdms/.cache/pitchlog/durable-fresh-census-10906d15/actual-census.json`（SHA256 `96569f7622b3820b13a693c4903ea761cfa47a10a6740ccce8edf4fc5a579d52`）へ保存した。拒否は旧anchorから消えた`_AuthorityRuntime._start_lease`内の`RecoveryEpochFence.generation`等に対する既存census述語であり、現checker所見へ架空に追加したり型注釈を消して回避しない。現在17所見の完全line/symbol/source bytesは `/home/ymdms/.cache/pitchlog/durable-fresh-10906d15/findings.json`（SHA256 `767caf4b0d6b86bc444703b6b330976bff728a6ccc91f3ff510ba7b4397edb32`）、全snapshot ledger集合は同census dirの`full-ledger-findings.json`（SHA256 `ff97bf99e2e6bcb9b854236269f427bcc1f9cf32a5a74303946a6c5b19fd14c7`）。

現17を当該sourceだけで抑止する未受理射影では、ledger旧anchor removed22/digest `7d1a7d3f7b92731b4a3c934e6767a25cb27601f8fa8b00bf5e5c62e2497ddcf1`、独立AST1/digest `0dbd512ac5095251e3391de5d4e33cca080ee3e4450c2a3a6921c01b758c8972`。同dir `proposed-exact17-census.json`（SHA256 `72b94f358b13da85b65d2118f6df2605a3cffc7e72502946c46b3dc588855429`）へ全identityを固定した。射影後の非ledger current182と、旧initial removed43/AST18の完全digestは旧版と不変。これはsource固有の候補集合だけで、登録/期待値/正式9・8値/履歴/snapshot/policy/7.3/7.7の変更や正式gate成功ではない。旧exact13は未更新のままroot限定非作者採否へ渡す。

最小fresh APIの作者実装/検査はここまで到達した。残るcommit前abort→quarantineの実故障行列、終了fsync後ACK喪失の全境界、business再起動/非0全復元の実closeProof/epoch前進、全設備喪失、最終非作者source確認/正式受理/CIは未完で、元4ステップ/全DoDとP6留保を保持する。人間の署名・逐行確認やMVP全完成を代記しない。


### 正式resolver基線追随とfresh17exact登録候補

rootが実develop4b2へ通常merge89830dc1。5競合は旧全登録/実main受理履歴を保持し、ledger有限追加とread/resolverを合流。guardの全31関数/class ASTは両親と同一。merge作業中の初回core408成功10失敗はHEADが旧基線の9件と、旧preparingの合成試験が現在ledger宣言を使った1件。前者はmerge確定後の実共通基線、後者は当時の宣言を明示する歴史fixtureへ是正し、拒否/timeoutを緩めず418成功/40.31秒。初期Ruffで新fixture定数の宣言順エラー1件も位置修正後に成功した。

非作者が既に再導出した実17全集合を限定登録へ反映。旧initial47と旧全censusは不変、台帳だけ除去22/AST1へ追随。正式before/after識別値・9/8・受理/履歴はこれからであり、旧13の不一致を元から成功だったとは記録しない。source本体は10906のままで、同入力の重いDB故障系を反復しない。まず影響範囲のexact拒否/censusを検証し、最終独立と正式7.7後に全必須CIを行う。


17exact追随の局所はchecker登録正負11成功/6.27秒。census/digest初回19成功1失敗/40.67秒は失敗messageの旧13regex1箇所の追随漏れで、実17拒否そのものは作動していた。文言1箇所だけ是正し当該1成功/1.21秒、同入力の残19は再実行しない。ty/Ruff成功。checkerとcensusの外部blob実変更により9射影中8だけ変化（frozen-inputs不変）、実4b2の値から各1増分を候補化し、source_digestと生成3moduleを全fieldへ追随。backend生成面/台帳契約134成功/12.44秒。既存history29/snapshot206の正式追記は0、旧全値を保持し、正式7.7未受理を維持する。


### 外部台帳の最小正本7.3候補（初回レビュー前）

対象はdata-model実4b2の1.1からの新1.2候補、§3-2-A外部3表/4主体・業務観測2主体・保全と失敗/fresh境界。既存表/履歴/意味を維持する。RG1枝3deの別1.2とF2枝2c391の別1.2は未統合候補として保持し、本枝で採用・上書きせず、実統合順で次版へ機械整合する。今回は本ledger plan§4/step4の既承認範囲だけ。

適用7.3はapprovedハーネス1.19、条文コミット2c214649（in-review化の第一親）を暫定固定する。初回敵対レビュー受付時に版を照合し、その版で本ゲートを運用する。finalize-doc手順と今回PO4/5の独立subagent/委任承認代替を使い、一般の検査/拒否/対象pathsは変更しない。本候補の初回は全文、反映時は従来の計画counter/反映周を継承する。本人の確認/署名を代記せず、現時点approvedではない。


2026-10-24T01:13:53.456718+00:00、PO委任によるCodex主担当/root判断で、実PR182/8569f14a・実4b2の完全9/8提案cac281d2200f60d266bb688215ddee5b7b69d3ff272d118361c5bb89b4836adaを受理。非作者rightsの2c214限定0・全9/8独立計算（証拠c49c6273）と実8569を再照合し、後発norm/索引/policyにより受理値が変わらないこと、宣言/移動方針/全前後値も一致することをrootが確認した。提案へ承認者/日付の2fieldだけ追加し、旧29履歴206snapshotを保持して新182 row1と必要snapshotを反映。8射影だけ実base+1、frozen-inputs不変、外部はchecker/censusの2blobだけ変更。本人署名/個別実値確認を代記しない。normの初回指摘・最終diff/委任policy/受理記録の非作者最終確認・全必須CI・全故障受入は未完了で、通常mergeはまだ不可。旧schema1履歴にはacceptance_idがないため、最初の重複確認用scriptは書込前に停止した。旧形式をgetで保つ工具是正後に反映し、最初のexit2を成功へ転記しない。


### 正本初回レビュー採否・反映1周目

ledger data-model新1.2候補8569f14aの基本2回枠・初回全文は、適用approvedハーネス1.19/条文2c214649（SHA12753078ce7804f401d55101c4f2fffa30ce9a537d3c646873bfc3e1af5adbd5）を受付照合し固定。非作者rightsの判定は否決P0=0/P1=1/P2=1、証拠6e0f7602821dcaf66a2eab066704485bf2aa93b7ffbf3f74f90bdbd356ad6d7e。既存ledgersource・RG1/F2各ゲートの回数/採否は別に保持する。

- P1・起因・(-)を採用。§3-2-Aのpeer EXECUTE限定は追加明示grantであって実効権限の排他保証ではない。固定business_identity.sql:2/11/22/24とmanifest:165–166のbuiltin PUBLIC維持を典拠照合し、専用schema/関数PUBLIC剥奪・追加明示grantの有限集合・builtin既存実効権限を区別した。既存builtin ACLを撤去/再裁定せずsource変更0。
- P2・非起因・(-)を採用。§3-2の規則解決owner重複2行のうち具体列grant/lock/本文DML禁止/撤去を持つ後行を保持し、一般行1つを整理。旧RG1norm9038の同先在P2・別da78採用反映（未統合）は保持し、本枝へ他RG1/F2の未統合改訂を一括採用していない。履歴行にもこの限定整理を明記した。

不採用/未終結/送り(B)は0。採用反映1周により本plan counter0→1、反映1周目commitにする。次は同適用版で反映差分＋影響節だけの第2回。正本approved・最終CIはまだ未成立。

正式tenant checkerは7.7履歴反映後、backend/srcの新static資産SQL2/JSON1をPython AST解析できずTB000×3でexit1となった。これは未達として保持し、拡張子除外やsource移動で回避しない。既存の宣言asset機構と必要最小検証の調査を非作者CSVへ依頼した。既受理182の全前後値/履歴は書換えず、新しい検査変更が必要ならその実変化だけ再導出/追補受理する。


static資産専用検証の限定追補を起案。既存の全変更母集団/未知TB000拒否を維持し、固定3byteを独立レビュー済み定数とmanifest相互整合で検証する案である。汎用拡張子skip/移動回避はしない。正式checker全経路の確認より先に182受理を反映した順序は早すぎた。新checkerによる実値変更が具体化したため、旧正式29/206を保持しつつ、未統合候補受理だけを保全・通常差戻し・再導出する案を明記した。旧受理を元からなかったとはせず、receipt/commit全履歴を保つ。現時点は起案のみ、checker分岐・受理候補差戻しは未実施。


### 正本第2回・委任確定

非作者rightsの第2回（基本2回枠、946f0c09反映差分＋影響節）は可決P0/P1/P2=0。適用approvedハーネス1.19/条文2c214649 SHA127530を維持し、証拠A-norm-round2.json SHA4910c2d88b5714c6a1bc6419d52e0920db6602af580a82102a3c8ddd7a20527dを受領した。初回P1/P2は採用反映によって解消。これは採否記録上の不採用取り下げではなく、全採用・処理済みであり、未終結/不採用/送り(B)は0。旧RG1/F2のレビュー/承認・未統合候補は保持する。

2026-10-24T01:20:34.173362+00:00、Codex主担当/rootはPO4/5/8/10の委任に基づき、946f0c09/docSHA52edd8072f7201e7d9f0e0e77a7a844977ff7afe730c9a0b0070860bdafe522dの採用反映差分と2回の独立結果を照合し、data-model1.2を本枝で確定した。業務の既存7製品用/移行込み8の提供数を据置き、未登録の観測2主体・外部4主体を分離する境界を保持する。本人の個別実値確認・署名は代記しない。source/ACL再裁定なし、正式develop/DDL全profile/7.7新最終値/CI/運用公開/MVPの完成を確定したとはしない。索引を同1.2/2026-10-24のapprovedへ整合。


### 未統合182受理候補の保全・通常差戻し

新static検証のコード変更が実受理値を動かすため、承認済み追補手順に従い、b94の未統合受理候補全byte・旧receipt/proposal・新10snapshotをcache/durable-ledger-acceptance/withdrawn-candidate-182へ保全した。元acceptance.jsonは改変せず、supersession.jsonで未統合候補のsupersededを記録。authorityは新182行だけを除いた8569の29履歴状態へ通常commitで戻し、新候補10snapshotのみGitの差戻し対象とした。正式developの旧29履歴206snapshotは全保持・変更0。b94 commitと旧受理事実はGit/cacheに残し、元から無かったとは扱わない。同PRの最終1受理は新sourceの完全9/8・非作者照合後とする。frozen_history/重複拒否/一PR一受理の規則は変更しない。


### 固定static3資産の専用検証候補

承認1c1123f8に従い、全変更母集団を保持し、固定3pathの通常file/親を含む非symlink/実SHA/閉manifest重複key/9関数4role3表/DDL相互hashを検査する分岐を追加。台帳adapterがHEAD又は比較元に存在する場合は3資産を非空行に依存せず検査へ残し、全資産削除も拒否する。未知path/拡張子/byteは元TB000で、既存Python解析・検出・frozen_historyは変更0。manifest自己申告やSQL移動で回避せず、一般SQL parser/配備強制済みとは主張しない。

新正負31成功/0.70秒、実製品変更母集団10fileのsource部分走査0違反（正式履歴確認の代替ではない）。初回checker全件は425成功12失敗/91.24秒。5件は合成repoがPythonだけ複写し新static3を欠損させたものなので、台帳adapterの複写時に実3byteも同時供給するfixtureへ是正、旧4実コミット変異の拒否を維持し新31＋旧5の36成功/36.08秒。残7件は新識別値/新外部sourceに対する正式受理前の履歴末尾不一致で、検査を弱めず最終受理後の全件で閉じる。全件中の候補履歴差戻しも別記し、混在した初回結果を最終成功へ扱わない。Ruff/ty/diff成功、root formatは未使用。source新分岐の非作者レビュー・新9/8受理・corpus追随・最終全件/CIは未達。


### static候補の独立0とcorpus通常追随

非作者rightsは4b8c0eb5の新コード/3固定SQLJSON・全9/8提案b6a98cde・旧受理撤回保全・policy182・corpusを独立確認し全0/0/0。独立31成功/0.64秒、実diff純削除→行0/file0でもadapter補完で3TB000、既存Python未登録connectのTB005を確認。新専用dispatch以外の既存scanner ASTは不変。証拠review-ledger-static-4b8c0eb5/evidence.json SHA272a317a8e73939aa730b8db14eed9938c092e7b3ba064e3232122a1ab19a86f、values.json d22fc938fe72d0c87f6c6d895e24ef90a2d40255b4f3709321463ffd8576f8f8。source検査拒否と全8変化射影/2外部blob/29旧履歴206snapshotの独立一致であり、正式再受理はまだしていない。

corpusは既存runnerと独立Gitblob長さ付きframingの両方がaa80aa5e2eb44ad65828d693edc21c55b81fb3d32176fc3153b656305e77fde0で一致（旧246→250入力、追加4/変更11、証拠corpus.json c60bd344e35c780d70de17ab7291ccb81aac44799f81d65f62c08e38699dd160）。manifestのdigest1fieldだけ通常生成追随し、pinned履歴6/全snapshot名/比較版/全case/runnerを保持する。これは追加7.7受理ではない。own step4で未完のCOMMIT前abort→quarantine/close fsync後ACK喪失の実故障を新2caseで先に閉じ、source実変更がなければ同じ独立値を使い、変わればその実差分だけ再導出する。


### 実COMMIT前取消と終了ACK喪失の追加2境界

csv_reviewが既存backend DB2pathだけへ、normal/freshと別critical resource keyの実故障を追加。**2 passed/44.46秒**、旧16caseは再実行していない。実reserve DML→INTENT fsync後のdeferred COMMIT取消でlive閉鎖/DB rollback0、trigger撤去後の通常restartでquarantine1/highwater1・同attempt拒否・次D4=2、primary停止後のstandby保全まで実測。fresh closeは同peerへclose送信→ACK読取遮断→実lease_close耐久終了→通常restartで終了保持・過去activationの再fresh拒否を確認した。close fsync前の故障や全昇格/全設備喪失の運用受入へ広げない。

JUnit cache/ledger-critical-4b8c0eb5.xml SHAc0248baa8ecde043ad5ac1d9ba61d175b462bf399d9bd6a634d499cd98548c74。testSHA5719afc7b09923885a15d5ea03a69c3770a63135586fc6de477bb15fb9fb4457/supportSHA6158f08ff8392eb2807e5547f205f2cf42aa7641707701ed1e7793ecaa0e1e8e、製品source/全9/8/corpus入力は変更0、所有資源0/共有DB不変更。作者側検査であり新2境界の非作者確認をこれから受ける。旧未完表示のうちこの2境界だけを閉じ、他の復旧/実closeProof/親全MVP未達を維持する。archive再検査の初回27成功2失敗/19.95秒は正式受理前の末尾識別値を補助合成fixtureが同期して旧履歴との比較に失敗したもの。補助検査を緩めず、最終受理後の区切りで全件再確認する。
