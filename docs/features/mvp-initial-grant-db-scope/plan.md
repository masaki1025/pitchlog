---
feature: mvp-initial-grant-db-scope
status: active
承認: 済（PO委任によるCodex判断。既承認§6の専用手順、本文参照）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-initial-grant-db-scope
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 1
実行方式: 通常
反映周コミット: 適用
---

# 初期記録権の実DB scope接合

## 1. 固定された承認と今回の位置付け

実起点は`4b2db6907f329c3dde113c3b7e1c3515600fb915`（実develop、PR181統合点）。意味・物理範囲・受入条件は`6065063b:docs/features/mvp-game-start-connection/plan.md`の§6と末尾のPO委任承認を固定参照する。承認対象は`c6ebdd2b0b36966131ede76ff32b9aa3eac1090c`、plan SHA256 `62b46d084491aa22417cdc24e9973a6f8960a558d9313c2dfd645afdef946ac4`、research SHA256 `24491067bfd52a63b7bf1ae2cca5007ac381f8b455e1040143e832b0848a3192`。本書はその(c)を実装手順へ写し、既意味の承認を取り直さない。

新§6の初回`bc8fdf39`否決P0=0/P1=2/P2=0、全採用・反映1回、非作者による第2回相当P0=0/P1=0/P2=0を保持する。独立証拠は`/home/ymdms/.cache/pitchlog/review-start-scope-plan-c6ebdd2-independent/evidence.json`、SHA256 `62de47cbb58341044425923c9890395363f003972487f1087e592070dc815177`、標準binary diff SHA256 `f2c91f0e217a6764dbe9e9a4d8c63152e044b9a3526f46585818adb4b8ccf465`。frontmatterの計画レビュー周回1はこの限定計画の反映1回を引き継ぐもので、本写像への新レビューを実施したという意味ではない。

上流transportのステップ1/1・145成功・独立P1是正後0、親U-G1の8ステップ・U-R1の9ステップ・U-F8の承認/レビュー系列は各親のまま保持し、改番・再集計しない。本書の4段階は親U-G1ステップ3内の専用手順である。前の非作者`initial_scope_plan_review`は今回の作者へ役割変更したため、本書の独立判定を兼ねない。

今回の編集委任は本plan/researchの2pathだけ。rootによる固定版写像確認・必要な限定非作者確認とステップ指定前は、製品source・core JSON・正本・DBを編集しない。新たな本人承認待ちを作らず、既PO技術委任内のroot判断へ返す。

## 2. 実装ステップ

| # | ステップ | 担当・合格条件 |
| --- | --- | --- |
| 1 | 新corepathの先行宣言と捕捉漏れ拒否test | root単独shared writer。`scripts/core_guard.py`の追加層定数だけを先行宣言し、全31判定本文/拒否を維持する。`tests/test_core_guard.py`で後述の新path/帰属の欠落・同件数差替えを拒否する合成fixture検査を先行する。現JSONをこのコミットで変更せず、既捕捉の包含証拠も残す。製品実装は0件 |
| 2 | 宣言済みcorepathの別JSON登録 | rootが`.claude/core-areas.json`だけを先行testと別コミットで確定する。新scope/brokerの記録権・tenant境界を登録し、移行/DB試験等の既glob包含を実照合する。必要なcore変更レビュー・PO委任判断をrootが記録する。実source開始前に捕捉を確定 |
| 3 | 初期権の実保存・固定関数・私有actor scopeを実装し隔離検証 | exact4新表/2既存表列/2role/9固定関数/9method、私有actor engine・factory、bytes/nullableの有限型対応を実装する。供給前に型/DDL/単体/拒否を進め、rootのactor RG1固定供給後に正常grant/再交付/競合も完了する。正常実接合未実施のまま本ステップ合格としない |
| 4 | 正式asset・最小正本・完全実値を受理し独立coreレビュー/必須CI | rootがsource由来の有限共有集合・必要7.3/7.6/7.7を受理し、実source/DDL/権限/登録/censusの一致と全必須CIを確認する。非作者レビュー、結果・未達記録を揃える。実broker RPC/HTTP開始/MVP完成を主張しない |

各委任は指定した1ステップで停止する。最初のsource委任はステップ3の実保存/実actor adapter一式であり、空method・常時拒否endpoint・常成功権利/RG1stubを成果物にしない。ステップ1/2はrootの境界登録作業で、actor供給待ちを理由に前後を一括化しない。実装コミットの件名は対応する完全トークン`(ステップ k/4)`をちょうど1個含める。確定ゲートの反映コミットは別に`反映r周目`を使い、親/旧featureの回数を置換しない。コミット・merge・pushはrootが規約と既委任に従い担当する。

## 3. 影響する正本

反映対象は`docs/design/data-model.md`と`docs/README.md`。rootが4新表の列/tenant複合PK・FK/ライフサイクル・immutability、`recording_generations`のproof_digest/recovery_generation、`rg1_restore_gate`のrecovery_generation、2role/function_only境界に必要な有限節だけを扱う。スキーマの構造的変更に必要な7.3と7.6の判断・確定はrootが担当し、既意味への承認再取得や全設計の版作り直しへ拡張しない。確定が必要な部分はその適用前に受理し、最終照合をステップ4で行う。

`docs/requirements/requirements-pitchlog-2026-07-22.md`と`docs/design/sync-protocol.md`は反映なし。野球ルールの意味変更を行わず、side/9-DH10/単一名簿検証は後続start serviceに残す。実装由来の他正本変更が必要になった場合は、sourceで根拠と有限対象を示してrootが別に引き受け、本書の作者判断で編集範囲を広げない。

## 4. 編集scopeと所有

### 4.1 ステップ3の指定source

| パス | 許す変更 |
| --- | --- |
| `backend/src/pitchlog/repositories/initial_recording_right.py` | 新設。final `InitialRecordingRightScope`、私有凍結`StartOwner`、exact9token/decoderと既9methodの実adapter。既issuer/DTO/暗号を再利用 |
| `backend/src/pitchlog/recording_rights/initial_grant_broker.py` | 新設。actor専用の私有engine/実登録runtime、短intentと業務scopeのcommit所有に必要なprocess内部分。root保護設定からだけ接続設定/既V12Boxを受ける。今回RPC server/HTTP/Cookie再検証の全経路は供給しない |
| `backend/src/pitchlog/repositories/transaction.py` | 共通token検証/結果実体化を再利用する私有actor factoryと状態別の閉じた許可集合。公開app factory/role条件/Session非公開/失効/一度限りtenant束縛を維持 |
| `backend/src/pitchlog/repositories/function_operations.py` | 新9token登録に必要なbytes入力・bytes/datetime/nullable結果の有限対応。既登録は現行のexact型・拒否を維持。詳細は4.3 |
| `backend/src/pitchlog/db/recording_rights/models.py` | exact4新表と既2表の承認済み列/制約/lifecycle/immutability。既rowsへ仮値を補完しない |
| `backend/migrations/versions/0035_initial_recording_right_storage.py` | 上記の実migration候補。実起点の最新revisionは0034_stage_a_rule_defaults。作成直前にrootが最新head/他担当番号を再照合し、必要な番号差替えだけを宣言して衝突を避ける |
| `backend/tests/db/test_initial_recording_right_scope.py` / `backend/tests/db/initial_recording_right_scope_support.py` | owned隔離DBの実保存/権限/資格/暗号/lock/正常・故障・競合検査とfixture準備。共有DB/秘密を使用しない |
| `backend/tests/test_game_preparing_components.py` | 既componentを保持し、新scopeの既issuerとの署名/呼出契約・局所正負例を追加。別の権利発行計算を作らない |
| `backend/tests/test_function_operations_boundary.py` | bytes/nullable等の新閉型登録と旧全登録の型/SQL拒否不変を検査。登録外の拡張型・偽型・余分列・bind型差替えを拒否 |

`db/engine.py`・`repositories/binding.py`・`base.py`・`tokens.py`の追加編集は不要とする。app engineは実roleを`pitchlog_app`に固定しているため期待role引数を増やさず、actor接続はbroker内の別私有入口に置く。通信経路は既`require_database_transport`/URL正規化を再利用し、actorのsession_user/current_user完全一致・LOGIN/NOINHERIT/NOSUPERUSER/NOBYPASSRLS/NO*ROLE/DB/REPLICATION・membership0・開始時tenant GUC未設定・DB identityを実検査する。検査の失敗/再checkout時の属性変化は接続を失効させる。既`_tenant_transaction`は真正`TenantContext`・未使用Session・autocommit拒否を既に扱い、結果実体化もbytes/datetime/Noneを扱える。これらをコピーした第2汎用executorを作らない。

### 4.2 root単独shared writerの有限集合

rootはステップ1の`scripts/core_guard.py`（追加層定数だけ）/`tests/test_core_guard.py`、ステップ2の`.claude/core-areas.json`、ステップ4に向けた既authz productのclassification/capability/DDL/exposure/application-steps、repository/function operation登録、tenant_boundaryの実影響資産、最小正本、必要7.7とpolicy実PR1件を引き受ける。9関数のSQLは既product認可資産の生成経路へ置く。新たな未登録SQL資産をruntime検査から免除しない。ステップ3の実検査に必要な生成/登録/権限資産はその検査前にrootが有限供給し、ステップ4では全件の正式実値を照合する。fixtureの手書きACLを正式assetの代用にしない。

実baseの包含照合では新brokerはcore未捕捉、新repository/function_operationsはtenant-isolationの既`repositories/*`のみ、DB試験/supportとmigrationは既globで各coreに入る。rootは新scope/brokerの記録権・tenant分離・要求再送の意味帰属を6.3で確定し、既捕捉は削らない。新pathの不在/同件数差替えを拒否する先行testは実sourceの書込前に置く。

### 4.3 新9tokenの有限型宣言

`function_operations._canonical_bind`は現状UUID/str/int/boolのみ、戻り値も`type(value) is expected_type`のexact照合である。新関数のbyteaを通すため、任意SQL型/TypeDecorator/任意Python型を登録できるようにはしない。新9tokenの固定registryだけに必要なbytes入力を組込のbinary bindへ正規化し、戻り値はbytes・timezoneを持つdatetime・明示nullable列に限って対応する。

nullableは`lock_device.revoked_at`と`resolve_start_attempt.generation`等の固定列単位の宣言とし、旧登録に暗黙にNULL許容を付けない。pendingのgenerationはNULL、committedは正bigintを別途結果契約で照合する。StartRecordRowは承認済みexact10列、nonce12/ciphertext48/digest32、UUID/intのexact型、正bigint範囲、過不足行/列をdecoderで閉じる。boolをint、memoryviewをbytes、日時文字列をdatetimeとして黙認しない。共通executorの再構築/SQL拒否は旧全登録で維持し、拡張型を選べるのは新固定registryのexact宣言だけとする。

## 5. 実装する物理単位と順序

承認済み§6.2/6.3の表・列・exact9 SQL署名/列権限・9method対応が固定契約である。追加は`trusted_devices`・`game_start_requests`・`game_start_attempts`・`recording_right_deliveries`、既2表列、2roleだけ。tenant付きPK/FK/FORCE RLS/function_only、PUBLIC EXECUTE剥奪、固定search_pathと実session_user照合を維持する。appのgeneration直接INSERTを剥奪し、無関係なread/update ACLは変えない。原資格/Cookie/原V12/鍵をDBへ保存せず、論理削除/変更可能列を有限宣言する。

9関数は`lock_device`・`read_existing_start`・`read_start_game`・`lock_preparing_game`・`lock_current_start`・`check_business_epoch`・`insert_initial_grant`・`begin_start_attempt`・`resolve_start_attempt`のみ。9methodは既`InitialGrantScope`と構造的に一致させる。`assert_bound_tenant`はPython実scopeの真正性、`assert_open_before_commit`は既RG1関数を使い、新関数へ数えない。第2発行器・任意callback・公開Session/engine/任意SQLを追加しない。

最初のsource委任では、型/固定token/実DDL/閉じたactor接続とscope/9method/既issuer呼出しを上記pathで実装し、unitと実DDL・拒否の検査へ進める。root供給まで正常実接合だけを未実施と明記する。正常DoDを減らした完了宣言やstubによる穴埋めをしない。

業務経路は、外部epoch共有fence→短intentの耐久commit→同業務Sessionのdevice FOR SHARE→実credential digestの`hmac.compare_digest`成功→`resolve_start_attempt`でrequest→attempt排他→既issuer reserve/claim→game→現generation/delivery→RG1 FOR SHARE NOWAIT→同business commit/rollback確認。後続start serviceのteam/player/U-M2は承認済み位置に残す。短intentのlock継続や別Sessionのresolverで代用しない。無効資格はresolver/予約へ進めず、固定owner/欠損/不正戻り値/許可外outcomeを閉じる。pendingだけ新規へ、committedは同一現権利の再交付へ進め、現権利欠損ならreserveしない。

broker process内所有者が業務commit成功を確認してから既`InitialGrant`のV12を返す。game lock中に別sessionのFK書込/同request更新を待たせない。資格失効はdevice行だけを更新してgameを待たない。復元制御はclosed commitを先行し、外部epoch排他を待つtransactionでgame/世代を取らない。外部fenceと実business bindingはcommit/rollback確認まで保持する。

## 6. source供給と開始条件

rootはledger/RG1の供給元で正常統合・独立検査済みの固定候補を受理し、そのsourceを本branchへ必要単位ごとの通常mergeで供給する。巨大assembly全体や未受理annexを取り込まない。供給元HEAD/受理証拠/merge後HEAD・差分はresearchへ記録する。RG1の`5ee75156adabdb7a43fbd1393c5b62337e6e770a`は現app専用制限の照合基準で、actor対応済みの供給候補と偽らない。ledger/RG1の具体供給HEADはrootがその受理時に固定する。

現在進行するapp/control2+observer2の正式RG1登録は先行独立である。その次のroot所有限定差分で旧`(UID20003,pitchlog_app)`を保持し、`(UID20002,pitchlog_initial_actor)` exact1組のscope_binding/controller peer/実backendのrole・DB・PIDと実epoch/bindingを供給する。設定/identity mismatch、別role同UID、別UID同role、失効backendを拒否する。これはステップ3の正常grant/再交付/RG1競合検査の前提であり、型/DDL/単体/拒否実装の開始前提ではない。app偽装/常成功RG1/権利stubを渡さない。

T1/P6/P7/実Port/HTTP/全非0復旧完成をステップ1〜3の着手条件に追加しない。運用秘密/新署名鍵・運用配置・共有DB適用は今回の委任外で、必要なら実行直前の有限判断へ残す。enrollment/revoke、実broker RPCとCookie再検証全経路、rollback確定後処理/再起動後解決のpositive gateは後続単位であり、通常再試行をMVPから削除しない。既意味の確認のための新PO質問は作らない。

## 7. 検査と完了条件

ステップ1/2はcore guardの先行拒否test、JSON差分捕捉、root Ruff/tyと対象pytestを行う。文書2pathだけの起案ではUTF-8/NUL/行末空白/末尾改行・差分・固定参照hashを確認し、DB/重いcore/pytestを再実行しない。

ステップ3はowned business/台帳primary/standbyの3系、実source/peer client、実限定actor、既公開vectorの資格/AEAD keyをfixtureだけに用いる。初期device行はfixture投入と記録し、実enrollmentの成功とはしない。正常条件は9method署名、実reserve/claim、D3/prefix0/issuance_order1、実V12Box、同request同V12再交付/追加予約0、全commit/全rollbackである。

負例/競合はappの9関数EXECUTE・4秘密表読取/DML・generation直接INSERT、actor直接DML/membership/別tenant、無効/失効/別端末資格・変更payload、偽/派生/失効scope、片側INSERT故障、commit失敗全取消、rollback後D4非再利用、claim不明停止、credential失効との直列化、RG1事前/直前両競合、外部lease喪失を含む。同request並行2本はrequest→attemptで直列化し、先行commit後は追加予約0、結果不明ならpendingを勝手に解消/新attempt発行しない。短intentのlock継続・別Session resolver代用を拒否する。

backendはRuff format/check・ty・対象pytest（component/関数境界/実DBscopeと既tenant scope）を実施する。ステップ4でroot Ruff/ty/pytest、docs-lint/局所plan-sync、core-guard、tenant-boundary、authz/model/migration/7.7の実影響検査とCIが要求する全必須checkを完了する。既検査を除外・件数だけ一致・census免除で緑にしない。source確定版に非作者coreレビューを受け、実source/SQL/権限/正式登録/最小正本と検査証拠を対応付ける。

完了は初期権DBscopeの実接合まで。実broker/API/画面開始・side/単一名簿・1球保存・非0復旧/MVP全体は未完成のまま後続へ明記する。actor供給前の部分成功を本ステップ3や製品開始の完了に繰り上げない。


## PO委任による実行手順の確認

2026-10-24T05:06:21.279441+00:00、Codex主担当/rootは既PO委任に基づき、固定ce53702cb9f29f21ba7f9fe49f12fe413290b050の本計画（SHA256 2b13ded75054c069d4e3142bee48a8ba70262e876dc7ffe4dbe77cdc64264070）とresearch bb8c571f2e4cc08a72806bbefdb57270a94b1b20b2c25d5ff53b01d7ecf56c11を、既承認6065063b §6の有限実装手順として承認する。非作者csv_reviewの独立写像確認0/0/0（上記cache、SHA256 426780966d078e2b2a84e9aa3b056c00d7b8a4737b534a117dfcbac89448a967）と固定diff c5cf34cdb6606336315d6f444fce6a4e83745740ade2fc10581976524cd82513を根拠とする。過去の意味承認を再取得したものではなく、山田正輝本人による実値確認・逐行確認・署名ではない。rootにステップ1の宣言/拒否試験を指定し、別ステップ2のJSON登録が成立するまで新sourceを作らない。actorの正式供給は正常DB接合前の条件とし、型/DDL/拒否設計の新規開始条件へ前倒ししない。


## ステップ3の有限実装具体化（既PO委任）

2026-10-24T05:44:36.371378+00:00、rootは採用済み保存保証の実装具体化として、opaque端末資格の無正規化UTF-8を単一private helperでSHA256へ写す方針を記録する。原資格をSQL/ログへ渡さず、既契約/実Cookieへの束縛を維持する。enrollment/RPCの完了を意味しない。新4表の論理削除/保護列不変を守る内部単一trigger public.protect_initial_right_storage()（owner pitchlog_owner、SECURITY INVOKER、固定pg_catalog/pg_temp、PUBLIC EXECUTE剥奪、UPDATE/DELETE row trigger4本）を0035の範囲に含め、公開9APIを増やさない。正式function-body/catalog/RLS/ACL登録と独立検証はrootが供給する。既0008 guardへ新proof_digest/recovery_generationを追随する必要はcache候補だけとし、旧6列判定を不変保持して最小追補/独立確認後に正式適用する。TRUNCATEを新主体へ付与せず、履歴を失うdowngradeは拒否する。新たな意味/保証削減や共有DB適用を認めたものではない。


## ORM新証拠列による旧同期readの最小追随

2026-10-24T05:55:02.903104+00:00、rootは実source126cd7afの供給調査で、旧`repositories/sync_apply.py`のread/by-number/lock3登録がselect(table)により新proof_digest/recovery_generationまで投影することを確認した。既役割の認可・read DTOを保つため、編集範囲に`backend/src/pitchlog/repositories/sync_apply.py`の当該3読取の旧12列固定射影と、既`backend/tests/test_function_operations_boundary.py`の射影/tenant/lock保持検査だけを追加する。新API/意味/Portを増やさず、他表のquery・古いGeneration列順/型/フィルタ/D3更新を変えない。rootが既recording_generationsのAPP ACLを旧列集合へ列単位化する必要を正式供給に含め、新証拠2列へのapp SELECT/UPDATEを与えない。3列追加は既存2表へ合計3列（Generation2、gate1）であり、省略表現の「2既表列」を列総数2と読まない。正常DB/正式ACL/step3合格は依然未達。既POの通常不具合修正委任による実装追随で、既承認の意味を再取得しない。


## 先行RG1供給との移行順の接合

2026-10-24、rootは既606§6・RG1 c58f83beの非作者確認済み最小供給順に従い、初期側の未適用0035候補を0036_initial_recording_right_storage.pyへ通常改番し、down_revisionを先行0035_rg1_initial_fresh_epochへ接ぐ。RG1が所有するgate.recovery_generation列/制約の追加を初期migrationから除き、初期側は4新表・Generation2列・内部保護triggerだけを保持する。既移行履歴/利用者データを書き換えず、ORMの同一gate属性は両単位で一致させる。既test_game_preparing_componentsの候補pathを同じ新名へ追随し、関数境界/合成prepareの局所検査と移行graphを確認する。これはPO委任によるCodex rootの技術接合判断で、本人の実値逐行確認や正式DDL/7.7受理ではない。


## 実DB補助の正規供給接合（2026-10-25）

PO委任によるCodex主担当/rootの通常接合修正として、既ステップ3の実DB補助に `backend/tests/db/durable_rights_ledger_support.py` を追加する。固定接合HEAD cb3c0f49を起点に、既0033初期化後は正規advance_stage_a_from_s0で0035と製品profileを適用し、生成profileが所有するbusiness_identity.sqlの二重直接適用を除く。既実peer・最小ACL・保護identity・故障検査を削らず、immutable SQL本文/製品source/共有資産を変えない。作者initial_sql_independent_reviewが当該1pathだけを所有し、rootがGit/本計画を所有する。非作者の最終確認と所有disposableでの検証前には実接合成功としない。

controllerと初期actorの実UIDを分離したまま単一ledger endpointが両方へ必要な点は未解消として保持する。fixtureのUID偽装・任意bool・多主体一括許可で埋めず、必要な製品主体接合は別の有限差分・非作者確認へ進める。0036と初期9API/fullprofileの供給も未完であり、この補助修正だけで正常grantを成立扱いにしない。


## 分離されたledger利用主体の接合（PO委任による計画受理済み）

固定cb3c0f49の実source照合により、controllerは初期actor UID20002と異なるUIDを必須とする一方、authorityの既v1 endpointは単一client UID/GIDだけを受理すると確認した。初期actor自身もcurrent/reserve/claim/recovery_fenceを必要とするため、fixture UID変更では正常接合できない。rootは既PO委任の技術具体化として次の有限案を提示し、非作者確認後だけ実装する。新たな記録結果・D5・耐久性保証の変更ではない。

- 単一authority worker・同一ProtectedJournal・同一runtime/mutexを維持し、別authority並列起動やjournal複製を作らない。既schema_version=1の閉じた形と拒否条件は保持する。
- 新しい明示v2設定に限って、rootが固定するgeneration actorとfresh controllerのexact2 peer/endpointを別Unix socketへ配置する。actor UID20002とcontrollerの別UIDを要求し、authority/app/DB主体との衝突、同UID/GID、重複socket/endpoint、未知role/key/operationを拒否する。共有group付与やUID偽装で分離を弱めない。
- kernel peerを端点ごとのexact UID/GIDへ照合し、generation側には既epoch/reserve/claim/fence_openだけ、controller側にはfresh_activation_openだけを許す。lease内の既fence_check/fence_closeは同channelに閉じる。callerのrole文字列では選択しない。公開epoch advanceは引き続き拒否。
- root配置/immutable endpoint/owner・mode・peercredentialの検査と、生成/claim/結果不明/journal順・再起動時停止を維持する。root保護v2設定だけを新たな供給入口とし、任意callback/常成功応答を追加しない。

有限編集候補は既core glob捕捉の backend/src/pitchlog/durable_rights_ledger/{authority.py,adapter.py,manifest.json}、既 backend/tests/test_durable_rights_ledger_contract.py と backend/tests/db/{durable_rights_ledger_support.py,test_durable_rights_ledger.py}、当plan/research。新主体接続のメタデータと実影響正本・tenant9/8受理はroot単独で必要分を導出し、source hash更新だけを検査成功の根拠にしない。DBの権限/SQL/保存表や旧契約意味は変えない。

非作者はv1後方整合・v2実peer/operationの閉集合・単一journal/失敗時停止・endpoint混同拒否を先に確認し、実装最終差分も別確認する。実端点の正常両主体/相互拒否/未知主体/切断・再起動はowned環境で実証するまで未成立。初期9SQL/0036/fullprofileの供給は別の残件として保持する。


2026-10-25T08:19:26.059374+00:00、PO委任によるCodex主担当/rootは254c9fa4上の計画SHA90e1f6b19fc1e6e48d5d326ba9c48fb1e16354cf896c0d6cebefb9dd817cfb52を限定受理する。非作者t1_ci_followup_independentのレビューSHA07b79a46006120e9aebd4f5a9ade501f3ac3cb380e4887cd1206de820a76ebee、証拠SHAf28190301eaf134325daff02fbfbf608fff9b9b1432cd72e011a7ca5963a2d07、所見0/0/0。両端点完全準備前ready禁止・全端点共有admission/blocked/active/mutex/journal・固定listenerと実kernel peerだけからのrole決定・role拒否はPG/journal以前・lease内check/closeは元channel限定を実装確認条件とする。新PO意味判断/人間本人の署名を代記したものではない。

rootはcreation_pathへ既ステップ3内のsource authorとして authority.py/adapter.py、既contract test、既DB test/supportの計5pathを専用wtで委任する。manifest.jsonと共有資産/正本/Gitはroot単独writerを維持し、作者は必要値をcacheへ出す。未知pathは編集前に戻す。新2path初期scope試験は固定候補のまま別所有とし、並行編集しない。独立実装レビュー・実peer試験・全正式値/必須CI前に提供完了とはしない。


## 初期4表の正本最小整合（2026-10-25）

rootは既承認6065063b §6.2/6.3の4表・世代証拠2列・2主体の既役割を、data-model現1.3から1.4候補へ写す。影響は既宣言済みdocs/design/data-model.mdの3-2役割表/6-1初期記録権の保存節と変更履歴、およびdocs/README.mdの当該索引だけ。4表のsource_sectionsは6-1へ閉じ、初期scopeの全lock順/9関数/再送・結果不明の採用済み意味を維持する。gate列は既1.3のまま。side/名簿/enrollment/実broker/開始statusを今回の4表へ混入させない。

この候補は構造正本改訂の限定7.3へ渡し、非作者確認とPO委任によるroot確定前はin-reviewを維持する。既1.3/旧1.2両系列の承認と旧レビュー/指摘/反映履歴は全保持する。正式50表profile/9API/内部triggerの個別SQL/ACL・schema-manifest/7.7実値・隔離実DBは別の提供証拠であり、本文の確定でそれらを完了扱いにしない。rootが正本/shared/Git唯一writer、候補テキスト作成もroot。


### 正本1.4初回2P1の採用・反映1周目

固定9465c8a7787e96db6452e4a58b3d3402b8ffa11dへの非作者initial_storage_norm_reviewはP0=0/P1=2/P2=0で否決（review SHA54d711429a422d926e583cbc01d2a3aa95e38d260252fdaf7e6707f7c143b792）。rootは既PO委任で両件を採用し、索引の過去approvedを変更した誤置換を実11f662d6の旧行へ戻して新版候補情報だけを先頭へ追加した。旧行は追加prefixを除けば全byte同値。世代のapp直接INSERT剥奪/専用owner経路と旧read/update不拡張も既6066.1から本文へ追記した。

候補作成者rootの採否であり、初回否決/2指摘/反映1を保持する。同じ非作者へ限定反映差分と影響を渡し、再確認とroot対象版確定前は正本statusをin-reviewとする。新しい本人承認待ちを作らず、正式1.4承認・50profile/DB成功をまだ主張しない。


## 50表の正規認可/0036供給を閉じる有限source範囲（2026-10-25）

data-model1.4確定後、rootは既PO委任の通常供給具体化として次の既存sourceをステップ3/4へ含める。authz配下はclassification.py/product_catalog.py/product_control_access.py/product_function_acl.py/product_table_access.py/product_table_rls.py/product_provisioning.py/product_role_contract.py、加えてdb/stage_a_startup.pyと既0036 migration。先頭はbackend/src/pitchlog（migrationはbackend/migrations/versions）。必要差分がないpathは変更しない。shared JSON/正式SQLbody/正本/Gitはroot唯一writerを維持し、作者は未適用候補をcacheへ固定する。

範囲は13roleの属性/旧権限を保持した8schema/50表/75関数（新9APIと内部trigger1）・56policy/最小列ACLだけ。初期ownerの列ACL撤去を同じ閉集合へ接ぎ、unapplyで0036が元から持つ4表のFORCE RLS/default-deny・内部trigger PUBLIC剥奪を壊さない。0036へ旧世代guardの新証拠2列追補を入れ、旧保護列/旧D3判定を保持し、生成関数bodyも同じ供給源へ接ぐ。既migration履歴は変更しない。

本初期単位での正規段階起動は0033→既規則0034→既RG1列0035→初期0036→全profile→S3完全照合へ進める。新53依存と旧17依存のexact70 IDsだけを前段から保留し、未知DDLや任意将来migrationを自動保留/適用しない。これはPR184の0035単位へ初期4表を混入させる変更ではなく、後続初期単位が供給する次の正常bootstrapである。固定規則5行・owner/RLS/一時権限なし・未知revision/欠列拒否を保持する。

対向/追随試験は既test_authz_product_classification.py/test_authz_product_function_acls.py/test_authz_product_table_access.py/test_authz_product_table_rls.py/test_product_authz_provisioning.py/test_product_authz_catalog.py/test_authz_product_control_access.py/test_game_preparing_components.py/test_recording_rights_models.py/test_schema_manifest.pyとdb/test_stage_a_rule_candidates.py/db/test_rg1_startup_epoch.pyの必要範囲。先頭はbackend/tests。既否定例/全数比較/旧v1の意味を弱めない。実DB/新初期scope試験2pathはrootが接合し直列実行する。

作者は専用隔離wtの上記source/testだけを編集し、1.4からの6-1正本写像/4表の完全manifest・既quote追随/新exposure引用/全75bodyなど必要JSON案をcacheで作る。正本にない引用を捏造せず、完全値/旧prefixの例外（世代guard1の証拠2列だけ等）を明記する。scope外のsourceが必要なら変更前にrootへ戻す。独立レビュー・実DB・正式7.7とCI前に正常grant/開始提供済みとしない。


上記source供給の実照合で、scripts/check_authz_catalog.pyが7schema/旧owner-ACL/関数集合を閉じていることを確認した。rootは必要最小の正式入口追随として同scriptとtests/test_check_authz_catalog.pyを同じ候補作者の有限編集範囲へ追加する。8schema/50表/75関数の採用済み集合と実originだけを受理し、未知schema/任意owner/余分ACL・grantable・PUBLIC・source不一致拒否を維持する。全域比較の緩和や生成値のソース直書きで凍結を外さない。正式JSON/7.7/root最終採否は引き続きroot単独で行い、source/testは非作者が最終確認する。

初期9SQLの単一sourceは既product_function_acl.py内の固定定義/builderとし、正式bodyはそこから生成する。Generation guardの唯一sourceは新0036定数とし、古い移行0008を改変せず、新0036と正式bodyで同じ既保護＋証拠2列を出す。他64functionのbodyを変更しない。別issuer/別SQL実装/未登録SQL sourceを作らない。
