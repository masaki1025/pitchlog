# 初期記録権DB scope専用手順の根拠

## 固定参照と役割

2026-10-24、実develop `4b2db6907f329c3dde113c3b7e1c3515600fb915`からrootが作成した専用worktreeで、plan/researchだけを起案した。固定`6065063b:docs/features/mvp-game-start-connection/plan.md`の§6と末尾PO委任承認を、4段階の実装手順へ写した。既意味の承認を取り直す作業ではない。

承認対象`c6ebdd2b0b36966131ede76ff32b9aa3eac1090c`のplan SHA256は`62b46d084491aa22417cdc24e9973a6f8960a558d9313c2dfd645afdef946ac4`、research SHA256は`24491067bfd52a63b7bf1ae2cca5007ac381f8b455e1040143e832b0848a3192`。旧初回`bc8fdf39`否決P1=2、反映1回、非作者第2回相当0/0/0と親U-G1/U-R1/U-F8の通算を保持する。旧transport145成功/P1是正後0は別の既達である。

前の非作者`initial_scope_plan_review`は今回のplan/research作者へ役割変更した。本書/planの独立最終判定を兼ねず、rootが必要な限定確認・対象版写像判断・source委任を行う。前の独立証拠は`/home/ymdms/.cache/pitchlog/review-start-scope-plan-c6ebdd2-independent/evidence.json`、SHA256 `62de47cbb58341044425923c9890395363f003972487f1087e592070dc815177`。本人の実値確認/逐行確認/署名を代記しない。

## 実baseのsource照合

| 実source | 観測と手順への写像 |
| --- | --- |
| `recording_rights/initial_grant.py` | InitialGrantScopeは9methodのProtocolのみ。既issuerはlock_valid_device→existing_start→precheck→reserve/claimの順で、既V12Box/単一発行器を変更せずadapterを提供する |
| `repositories/transaction.py` | 私有registryにSession/ExitStackを保持し、ハンドルの真正context/tenant発行証跡/失効を実照合する。run_functionは固定registry/閉bind/実体化を使う。actor状態の有限集合と私有factoryをここへ追加し、公開app scopeを広げない |
| `repositories/binding.py` | 真正TenantContext、未使用Session、一度限り束縛、autocommit拒否、with session.beginによるcommit/rollbackを既実装する。追加編集不要 |
| `db/engine.py` | create_database_engineの実session_user/current_userと期待属性はapp固定。actor期待roleを引数追加して兼用しない。新broker内の別私有入口でactorを実観測し、既transport検査/URL正規化を再利用する |
| `repositories/function_operations.py` | _canonical_bindはUUID/str/int/boolだけ、戻り型はexact比較。bytes入力とnullable結果は未対応。既登録の許容/拒否を保持した新9tokenだけの有限型対応をsource scopeへ追加した |
| `repositories/base.py` / `tokens.py` | 不変実体化は既にbytes/datetime/Noneを扱う。第2executor/共通scalar拡張は不要 |
| `db/all_models.py` | modelsモジュールを自動走査する。既recording_rights/models.pyへの4表追加は別の手登録口を必要としない |
| `migrations/versions/0034_stage_a_rule_defaults.py` | 実baseの最新revision。0035候補の作成直前にrootが供給sourceのhead/競合を再照合する |

新9tokenのnullableは固定列単位（device revoked_at、pending時generation等）で宣言する。bytes bind/bytes結果、timezone付きdatetime、NULL許可列以外へのNone拒否、UUID/intのexact型/正bigintと暗号長を閉じる。旧登録が新型/NULLを暗黙に受け入れる変更をしない。新規のSQL型/任意Python型/TypeDecorator/汎用実行器を追加しない。

## core先行作業とroot所有

実baseのcore JSONでは新brokerは未捕捉、新scopeとfunction_operationsはtenant-isolationのrepositories/*が捕捉する。新DB試験/supportとmigrationは既globで5領域に入る。rootは新scope/brokerの記録権・tenant境界・要求再送の帰属を先行宣言/拒否testへ落とし、別JSONコミットで実source前に登録する。JSONの件数合わせや既登録縮小をしない。

rootの有限shared集合は既authz product生成/登録、repository/function登録、tenant_boundary、data-model/README最小節、必要7.7/core/policy実PRである。実DBscope検査に必要な固定SQL/権限/登録は検査前に供給し、最後にsourceと正式asset全件を突合する。fixtureの別ACLや未登録SQLの免除は使わない。

## 正常実接合の供給境界

現app/control2+observer2の正式RG1登録を先行独立に保ち、その後rootがactor `(UID20002,pitchlog_initial_actor)` exact1組と実epoch/bindingを供給する。型/DDL/単体/拒否は先行できるが、正常grant/再交付/競合前にはこの供給が必要である。既RG1 `5ee75156adabdb7a43fbd1393c5b62337e6e770a`はapp専用制限の根拠であり、actor供給候補ではない。ledger/RG1は供給元の正常統合済み固定候補をrootが個別通常mergeし、巨大assemblyを輸入しない。

初期device行と公開vectorはfixture準備である。隔離3系DB/実台帳・peer/実actor関数/実資格比較/実V12Boxの成功を、実enrollment/実Cookie再検証/実broker RPC/製品開始の成功へ拡張しない。未供給正常系は未実施と記録し、常成功RG1/app偽装/stubで埋めない。

request/attemptの排他はlock_valid_device内の実資格照合成功後、同Session resolverからreserve/claim前に取得し、business commit/rollbackまで保持する。committedは同一現権利再交付、pendingは新規候補、欠損/owner不一致/不正戻り値/他outcomeは閉じる。不明pendingの自動解消は行わず、rollback後処理/再起動解決のpositive gateは開始全経路前の後続義務として保持する。

## 起案時の未実施

本候補は2文書だけで、Git/index/製品/core JSON/正本/DB/共有assetを変更していない。source/台帳/RG1のmerge、DB/pytest/重いcore、運用秘密/新鍵発行・共有DB適用は未実施。T1/P6/P7/実Port/HTTP/全非0復旧完成を型/DDL/拒否の着手条件に追加しない。新しい野球結果・個人account/役割の意味判断は0件である。


rootの写像照合で、段階1の先行宣言を実装する既scripts/core_guard.pyの定数層pathを明記補完した。新しい判定器や拒否変更を加えず、全31本文不変・先行宣言→別JSONという既手順の実source配置である。2docs以外の変更は0で、必要な限定非作者写像確認の前に固定する。


## ステップ1: scope/brokerの先行core宣言

2026-10-24T05:11:30.333027+00:00、rootが要求再送・記録権・tenantの3領域へscope/fixed-operation/brokerのexact3pathを宣言。JSONは不変、判定31定義はHEADとAST全一致。既初期付与/作成登録は履歴fixtureへ分離し、旧負例を保持した。初回398成功/2失敗は旧preparing回転前の宣言を現宣言へ混同した検査で、歴史的宣言を明示するfixtureへ是正。再検査400成功/30.73s、ty0。ログ /home/ymdms/.cache/pitchlog/initial-grant-scope-core-step1{,-fixed}.log。最後のRuff2行長は改行だけ是正。source作成0、既coreの範囲/拒否を縮小しない。


## ステップ3の途中source固定（正常接合未達）

2026-10-24T05:44:36.371632+00:00、作者csv_reviewはsource編集/検査を停止し、rootがcheckpoint601ffcbaf75fced1a2c7084f92391dc90b158b6071db9ea319c526921d9dfd8cの全8source byte/既baseline SHAを照合。実9method/phase token/owner束縛/私有actorと既issuer、4ORM表+2既表列/0035、bytes/aware datetime/nullableの有限型と既265局所を途中固定する。全既2testファイル265成功0.97s・8path Ruff/ty/format0、DB0。source8と全patchは /home/ymdms/.cache/pitchlog/initial-grant-db-scope-40808178 に保全。正常actor RG1 scope_binding/正式9SQL・2role・ACL/RLS・既guard新列供給、正常DB/競合/故障、Cookie/RPC/enrollment/startサービス/HTTP/UIは未達で、step3合格・開始/初球/全MVP成功を宣言しない。空DBtest2ファイル/常成功Portを作らず実供給後に実試験を追加する。内部trigger/旧guard追補の具体範囲はplan末尾参照。以後作者はcache-only SQL/role候補へ移りrepo sourceをrootと並行編集しない。


## 固定126の独立確認と旧同期readの射影追随

2026-10-24T05:57:38.633453+00:00、新規非作者initial_actor_source_reviewは126cd7af source8全SHA/差分2827a62b12f9e9341aaefc5b5b092528188c3258f7a7c265ca3ba4eccd736b68を確認、265成功0.91s・phase/app/DML/savepoint/失効/ownerの7拒否probe、途中checkpointとして0/0/0（/home/ymdms/.cache/pitchlog/reviews/initial-actor-126cd7af-independent/evidence.json SHA256 3dadb204978eabb2f5edea385296a941a6f5b06a01bcfba01a64d54c42782807）。正常DB/旧guard/正式供給の未達は維持する。

作者の後続供給調査で、ORM追加が旧Generation read/by-number/lockへ新2証拠列を投影するため、rootはplanの最小追補に基づき当該3登録を旧12列/旧順序へ固定した。tenant述語/フィルタ/row lockを保持し、新証拠2列を通常app読取へ流さない。旧read12列の根拠は基線schema-manifestのGeneration列集合。全既2unit268成功0.96s、追加Select型guard後の3case成功（initial-grant-old-read-projection{,-narrowed}.log）。最初のRuff import空行/ty Select union診断を、import整列と実Select assertionで是正、最終Ruff/ty0。正式APP列ACL追随はcache候補・別受理が必要で、現migrationを適用したとの記録ではない。APP Generation INSERT一般撤去は未採用、既担当交代契約との照合を求めており自動拡張しない。


## RG1前提の通常接合と未適用移行候補の接続

2026-10-24T07:49:11.249959+00:00、rootは4bb5dd47へRG1 0ed61d16を通常mergeし62723b8eへ固定。競合4pathは非作者ではなく候補作者initial_sql_independent_reviewがcacheに組立、rootが正確4byte/両親のguard全top-level関数AST一致を確認して適用した。根拠handoff40197970c7dc5878dd2b93334abcf563f810343695a7b15cd774e9bf55c5c909、作者core475成功45.87s。独立最終確認はinitial_scope_plan_reviewへ別依頼し、未受領時点で成立とは記録しない。新しいcore例外を加えず、ledger→RG1→initial3の宣言層とtransaction両状態辞書を保持する。

既606/c58供給順に従い、初期側の未適用0035を0036へ改番しdown_revisionを0035_rg1_initial_fresh_epochへ接続、gate列/制約の二重追加を除いた。新4表/Generation2列/内部保護trigger/全履歴保護は保持。alembic headsは0036の一意head、共有DBや利用者データへの適用0。局所は最初265成功3失敗（固定登録表にscope_bindingが供給された期待・欠落負例の作り方・旧down_revision期待）。負例は不変登録表を直接消せないため、その失敗1/error1も残し、moduleの別mapへ欠落を注入する形へ修正。登録表自体の不変性を緩めていない。Ruffはimport改行/92文字行の局所是正後0、ty0、最終268成功1.00s（initial-rg1-merged-components-registered-final.log）。これはmigration graphとcomponent接合で、初期9SQL正常DB/開始HTTP/UI/正式7.7は未達。


## 実台帳補助の通常起動接合と限定実DB結果

2026-10-25T08:16:28.654974+00:00、PO委任によるCodex root判断で既ステップ3の補助1pathを限定採用。作者initial_sql_independent_review固定handoff SHAae23690c96b37988d25f6f30b8d672e1fbacbd2f966c27595e0e806885f16e3f、after SHA30ef3bb8f5508b8d1accf86d0e0dc3c73cdbe799aefa1be6ae9c150fffc56071。非作者rootは全top-level ASTを照合し、変更が_install_product_business/isolated_ledger_databaseだけ、AuthorityDatabase/UID20002/故障injectorを保持することを確認した。既正式LOGIN/NOINHERIT ownerの実DSNで0033を適用し、正規advance_stage_a_from_s0で0035/profileへ進める。生成済identityのraw二重適用を除き、実function owner/SECDEF/probeのみEXECUTE/app/control/initial/PUBLIC拒否を追加検査した。

root専用検証wt cac43c43+exact helper patchで実 test_real_roles_and_business_observer_are_limited が1成功17.55s、source after SHA一致、所有containerはcleanup済み、共有pitchlog-db-1未変更。receipt /home/ymdms/.cache/pitchlog/initial-ledger-support-startup-candidate-20261025/root-review-real-pg-receipt.json SHAae3ce364d5379241bbd867fd0e57a4e63fcba14328041d64cdc9a4d5b016edf0。作者mock4成功は実DBと別記録。これは台帳基礎fixtureと最小ACLの実証で、controller/actor両UIDの同時接続・初期grant・0036/9API・開始HTTP/UIは未実証。別endpoint案の非作者確認や正式profile/7.7/CIを代替しない。


新DB試験2pathはcreation_path作成候補として凍結受領。handoff /home/ymdms/.cache/pitchlog/initial-grant-db-test-candidate-20261025/handoff.json SHA78048292e42bce862684a303ede14521fd9b3d1582598061925b3b06a8653ff6。test SHA f4f7bfcf1a2a7dea847d4e2490f899e8b097ca90dcd9541f574fa3567f0b57ee、support SHA eea4b33ec2aaa7d248ad6c2ec5d569c9acab444205b822d8252dd236cf8bc542。Ruff/ty/9子program構文確認、12収集・実DB0（必須DB実行guard exit1）を保持。候補として途中保存し、別作者レビュー/正式profile・0036・役割別endpointの供給後に実DB接合する。手書きACL・仮のbroker成功・事前投入deviceをenrollment成功へ広げない。


## 初期保存構造1.4の限定確定

2026-10-25T08:58:57.487486+00:00、PO委任によるCodex主担当/root判断で59966185本文を確定。初回9465の2P1は全採用し、索引の誤置換を旧行同値へ戻し、app世代直接INSERT剥奪を追記。非作者反映1の最終0/0/0、review SHA002d0b2abd4096467537a1af8354246d09acf38f828af3306bf8407d6616fe44、evidence SHA2c5923e082dbe83760d4a0bed5361f5ad5bc910f74501dd959ed198fdb8d9e23。旧1.3/両1.2以下の承認/採否履歴と初回否決・反映1を保持。normのstatus/現1.4履歴/索引のmetadataだけを確定表示へ更新し、本文を追加変更していない。receipt /home/ymdms/.cache/pitchlog/initial-storage-norm-1_4-acceptance-20261025/receipt.json。

これは既606の4表/2列/専用主体の物理構造確定で、50表profile/75関数/最終SQL/0036/正式7.7・実DB/開始UIは別の未成立条件。実provider/HTTP完成を構造整備の開始前条件にせず、運用秘密/共有DB/人間本人署名を代行していない。


## 二主体ledger接合の限定採用と実DB五件

2026-10-25T09:04:19.087053+00:00、PO委任によるCodex root判断で作者creation_pathの5path差分24868b4e141533f5f2d8c3b1d8f29572dc4cebff43f7a75ab95a674861dd8a93を有限採用。source authority74288d27fccc4a217870affce4ee17b17f12c07efe1404131510718fcdc4b28b、adapter4d1cc4c5c955a5bdcc5d459583a7a8b8b9d9923375c5e86393d013ab42941c2e。非作者t1_ci_followup_independentのsource証拠1cb9f8bf39547c95464d2a2cc1db8157098133637780e5dca8270a8f7f38a9a9/所見0、pure138成功。manifestは実sourceへ2hashだけ接合した候補byteを使い、他field不変を確認。v2の正式metadata/7.7は別に残す。

rootは既data-model1.3/profile13の隔離composed wt11f662d6+exact5patch+hash-only manifestで、実dual_peer5件を実行して全成功117.50s。初回fresh中のgeneration操作/lease、操作と実kernel主体の相互拒否、controller未終端の共有blockedと再起動拒否、片endpoint配置失敗、実business peerとroot配置値不一致を検査。6fileの実行前/後/現在SHA同値、receipt /home/ymdms/.cache/pitchlog/ledger-dual-peer-author-candidate-20261025/root-real-dual-pg-receipt.json SHA402678a1b4c33b7d1d761078e68df6c6adf34a831c4dc9e5a5792c5776d46a7b。非作者追補570d8e94d189601a5047708631a008fa095b72042e849884d4f512a08e8fac1fでログとbyteを再照合。共有DBは未使用、所有containercleanup済み。

単一worker/runtime/journal/mutex/blocked/admissionを保持し、v1の公開形は維持。これは二主体の実supplier接続の有限実証で、旧v1全故障行列/初期9SQL・0036・50profile・正常grant/画面開始を完成扱いにしない。旧17C2行/source bindingの正式追随と完全値受理/全件CIも未了。
