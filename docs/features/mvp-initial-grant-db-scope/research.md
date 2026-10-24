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
