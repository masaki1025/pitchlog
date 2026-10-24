---
feature: mvp-initial-grant-db-scope
status: active
承認: 済（PO委任によるCodex判断。既承認§6の専用手順、本文参照）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-initial-grant-db-scope
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 0
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
