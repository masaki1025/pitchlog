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

最初のstep1は`74c36a75d...`（完全OIDはGit履歴で参照）としてローカルcommit済み、未公開だった。rootのWIP確認で「全旧試験を供給95dへ固定し続けると、統合後に新しいorigin/develop基線を検査しない」不足が指摘され、全採用した。rootの個別指示により74c36a75と中間411成功/26.43秒を保持し、amend/rebase/force pushせず、同step1の是正を別commitへ記録する。これは計画scope内の試験helper是正で、製品判定/API/source追加ではない。

供給OIDのGit一意導出はそのままに、比較元選択を分離した。毎回の実origin/HEAD merge-baseが供給95dを含む場合は、その実merge-baseを選び、統合後の新しい共通基線保護へ戻す。供給未統合の隔離段階だけ、実merge-baseが供給95dの祖先であることをGitで検証して95dを局所比較に使う。独立分岐/検証不能OIDはfail-closed、固定供給への無条件fallbackはない。全旧比較呼出しと新実設定試験をこの選択へ接続した。

追加4例は、隔離段階の供給選択、供給統合後の新しいactual基線保持、独立分岐拒否、不明OID拒否。最終版core全件は**415 passed / 25.34秒**、失敗/skip/timeout0。是正後の全core対象実行はこの1回だけで、中間411成功を新版に転用していない。root Ruff/tyも成功。先の段階は所有2pathsの静的検査と最終root全体を確認しており、総計1回だったとする意味ではない。

実測時originは31194a39、actual merge-baseも31194a39、供給は95d766f5、選択した局所比較元は95d766f5だった。未改変の製品verify_area_path_baselineはsupplier95d基線では受理し、real31194ではsync-protocol.paths不一致を引き続き拒否した。全製品関数/class AST・JSON byte・供給initial source/test/policy/history27/snapshot202は保持、新ledgerのpackage/contract/positive/DB試験/supportは実wtで全て不在を再確認した。

是正test_core_guard.py SHA256 `f436e4a508525e80e77e22857a74b8b7c6654c3930f7efbc69e2fb72200059bb`。中間74c36a75から試験だけのfull-index binary差分SHA256 `673fe4c699ace35182028aa016d9e7aa37ec890de9a0eba5c955882e94464a5d`。core_guard.pyの宣言は中間版と同じ、製品判定の変更0。最終HEAD/全差分SHA/中間保持は引渡しで固定する。実develop未統合・step2以降/正本/正式7.7/policy新target/運用資源/push/PRの未達を保持する。
