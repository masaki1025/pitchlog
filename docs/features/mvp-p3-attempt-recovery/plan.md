---
feature: mvp-p3-attempt-recovery
status: active
branch: feature/mvp-p3-attempt-recovery
承認: PO委任によるCodex主担当/rootの2026-11-07移管・閉P3接合指示に基づく技術具体化（最終source採否は別）
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# P3元本文の結果不明復旧と標準controlへの閉接合

既採用のsync-protocol 6-3-A/DI1〜DI5と既P3契約を実接続する追補。新しい野球意味、D5/拒否優先順、取消範囲を決めない。P1/P2復旧6058888b89824be35bee19f75af80bb03cae4763を不変更で保全し、本専用WTでP3固定4d43e08c8d10e44eda40fa3bf611529b38479d6cへ接合する。既候補/既レビュー回数を保持し、実Port/DB完成を型/契約具体化の開始条件へ追加しない。

## 既成立と不足

- P1/P2は真正E1 receiptから原本文全値（V12込み）の独立body digestを導出し、control原本/journal、業務同鍵遮断、control同鍵の再照合/永久retirementへ束縛する。旧登録NULLの現在本文からの補完は禁止。39adの最終owned4case、605の実browser閉鎖2モード/実旧live・認証越境を候補証拠として保持する。
- P3は同じ真正receiptと既`D1lessPhaseBinding`/`freeze_wire_source(d1less=True)`を持つ。既`/sync/change`は同attempt再送で、P1/P2用recoveryの対象外。
- P3の標準control SQLは未供給。旧実測はcache `mvp-past-correction-product-20261106/p3-d1less-control-functions.candidate.sql` SHA256 a306da167df929d3e150b9f66da8e90d12abb0c44a712cd175f5e31025255ef2 の専用register/read 2関数をowned fixtureへ適用したもの。標準配備済みとはしない。

## 編集所有と境界

本WTのみを本担当が編集する。共有`writer-binding-control.sql`はroot移管により本担当を唯一writerとする。P3作者のWT/共有台帳は編集しない。

対象は既P3と復旧の接合に必要な `api/routers/sync.py`、`sync/{apply.py,attempt_recovery.py,source_binding.py,wire_source.py,wire_fingerprint.py}`、`sync/control_provider/{evidence.py,binding_control.py,writer_binding.py,sql/control-phase-schema.sql,sql/writer-binding-control.sql}`、`durable_rights_ledger/{adapter.py,manifest.json}` と専用試験。FE共通 `api/{recoverableSyncPost.ts,syncAttemptRecovery.ts}` と `lib/syncAttemptBarrier.ts` の閉P3分岐を接続する。P3 FE本体はP3作者所有を維持し、`postP3Change`接合差分をcache patchでrootへ渡す。P3計算/投影を複製・再実装しない。

P3固定点と復旧起点が異なるため、復旧topic7commit（b3de166c/68a4a459/ad90662e/e1f8f6ea/a207d4a4/39ad4f20/6058888b）の差分だけを3-way接合する。計算/NP/断中画面/artifactの基線差分は取り込まない。復旧topicの既承認対象52pathを依存として再利用し、新しいP3の正式資産の衝突/不一致はrootへ渡す。生成module/正式authz・tenant・seal・7.7は手作業で受理しない。標準current起動/移行の正式追随はroot所有。appへDB表権限を追加せず、body source pinは実byteからの候補再計算として分離する。

## ステップ

| # | 実装単位 | 完了条件 |
|---|---|---|
| 1 | 固定P3＋P1/P2復旧のsource接合、P3専用control 2関数の標準供給 | 旧EventPhase/d1=1を維持。P3だけD1less/NULL-D1の閉union、unknown kind/混在/余剰拒否。専用register/readも同attempt advisory鍵/retirement guard/body digestを持ち、旧NULLを補完しない。計算/投影/既D5指紋を変更しない |
| 2 | P3真正原本文の登録・照会・後着遮断とHTTP入口 | P3元change/recovery_generation/V12/target全値を真正receiptから独立digestへ束縛。P1/P2とP3を型由来で区別し、専用control原本とbusiness tombstoneを閉照合。借用/全旧RPCの終結・後着遮断の証拠を維持。DI2をV12/内容検査の後ろへ動かさない |
| 3 | 共通端末barrierの閉P3接合、FE差分受渡し、owned実対向と候補固定 | 元本文/D5をstrict保存し、retry_allowed後だけ新attempt。P3 FE本体はroot直列で接合。P3のACK喪失/故障/未登録/旧live/異内容・越境とP1/P2回帰を実PGで確認し、実装のない成功・固定応答を使わない。独立レビューへHEAD/全diff/全値/試験証拠を渡す |

## 検証と未成立の管理

source固定した各WTで共通owned PG/browser/network lockを全寿命保持し、外側の共有DSNをunsetする。作業中は影響範囲、統合候補固定後に必須全件を実行する。旧caseの期待値を現在出力から作り直さない。P3候補計算の一般化/旧世代/長prefixと、共通復旧の成立を別に報告する。

候補source成功、正式受理/通常統合、実機/運用TLS/復旧、MVP全完成を区別する。本人逐行確認/本人署名/P6 blindを代記しない。rootのPO委任採否/最終独立レビュー/正式manifestと7.7は別ゲートとして保持する。


step1接合記録: 4dへの605全mergeは起点差により無関係な約170pathを含むため未commitでabortした。復旧7topicだけを接合し、C2登録はP3 3操作とrecoverの両方、client資格の閉URL集合はevents/change/attempts-recover、交代POSTは既耐久barrier/C2経由を保持。P3 phase_kindと復旧body_fingerprintを同じ私有phaseへ保持し、business bindingへは両方を混入しない。既artifact/数学/保存値vectorには差分なし。標準P3専用2関数へ元候補SHAを照合して同鍵遮断/body保存を追加し、旧first-ball EventPhase分岐は維持する。正式受理/実PG/独立source確認はまだ。

step1検査: backend関連307件・Ruff/Ty成功。FE関連51成功、Undo8件は起点4dのfixture artifact 4e8b3252…に対し実artifact ce622726…の既存不一致（対象資産の差分0）。期待値は変更しない。標準control owned初回は共有DSN未設定のままdefault admin fixtureが先に解決されたsetup errorで、DB確認には未到達。既owned admin/tested-role fixtureを明示importして再検証する。標準関数catalog照合は非作者cache patch 1da9acfd…を元byte照合して採用したが、正式受理・独立source採否は未了。

step1実PG追補: c6a43313 detachedで標準関数catalogまで到達したが、専用control PGには業務app role自体が存在せず、提供catalog検査のhas_function_privilege(text)が42704となった。app roleを作らず、to_regroleがNULLならEXECUTE不可(false)、存在時だけ実oid権限を検査する。欠落関数/他role grant/owner等の拒否は維持する。

step1固定結果: 3876ba3d detachedの標準control+実P3 HTTPは1 passed/168.07s、verify WT clean。cache CREATEは使用しない。run3ログは ~/.cache/pitchlog/mvp-p3-attempt-recovery-20261107/standard-control-run3/pytest.log。

step2接合: recover入口だけが元本文のS-1閉unionからP3を解析し、真正receiptのbody digestをP3登録にも毎回導出する。既events入口と旧d1=1 readerは不変更。P3だけread_p3_attempt_recovery_stateでNULL-D1 phaseを閉照合し、journal phase_kindとの一致を要求する。retirementのbody digestにはrequest.pathが含まれるので、他phase/旧NULLから現在本文への再束縛はしない。

P3のcontrol/event FP（wire原値）とD5台帳FP（既operation_fingerprint(event, P3, None)）は異なる。式を変更せず、真正P3から既式を適用したD5 FPを私有d1less packetへ別値として渡し、observe_d5だけが使用する。control原本/journal/business binding/tombstoneのevent FPは既wire FPを維持する。旧Event recovery packetへこのフィールドを追加しない。

実装追随source pinはadapter.py実byteのSHA-256のみ: 旧d9fcdfde31aeb49ab23d242fd7ef1bd913b5a9f412a4016a29ba38768c4c15c6 → 40d9b070365ffb1f6fdd583c46e3438fdd934ec869d9914537c54c1e418e228a。数学期待/正式authz/tenant/seal/7.7の受理は行わない。P3原本文digestの5対向とevent/P3両phaseの終結/異内容/他phase拒否の純粋試験を追加した。ownedの未登録/後着・T2/T4全取消・実受理後のACK喪失/同D5再掲・別V12拒否を既真正P3縦断へ挿入する検証を用意し、固定sourceで次に実行する。

step2固定: da7a933c、backend関連333件/20.74s・Ruff/Ty成功。owned実証はdetached verify-mvp-p3-recovery-step2@da7a933cで共通lockを保持して実行中。結果前に成功とはしない。

step3端末候補: 共通barrierは既D1付き要求を保持し、P3のchange/recovery_generation/V12/target/expected_version全原値をstrict IDBへ固定する。送信前再起動後も同body/D5の旧attemptだけを照会し、retry_allowed後だけCASで新attemptへ更新する。unresolvedはchange再送/成功を作らない。P3 wrapperは専用change URLのみ、元P3をeventsへ変換しない。入力getter/JSON補完/未知混在を拒否する。

FE検査: 対象5file/66件成功、vue-tsc/ESLint成功。HTTP/IDB doubleであり実PG/実画面の証拠ではない。P3 FE本体は編集せず、cache ~/.cache/pitchlog/p3-recovery-fe-intake-20261107/candidate.patch（SHA d6a5576c4c34e717aaf6cbbb6f3963e9538b7a011173c8019d3f3f6d3438f645）をroot/P3 writerの直列接合用に渡した。適用/実画面/非作者再確認/正式受理は未了。P3 old-live/tenant及びP1/P2最終合成回帰も残り、step3全成立は宣言しない。

step2実証結果: da7a933c detachedのtest_p3_original_body_recovery_uses_standard_controlが1 passed/171.41s。実login/開始/3球/真正P3に、未登録旧attempt退役と後着503、T2/T4故障後の同原本照会、実受理後ACK喪失からの新attempt同D5再掲、各段の別V12拒否を追加して通過した。標準control実catalogを使用し、cache CREATEは無い。元のP3再取得/後続球/越境の期待とDB照合も維持する。verify WT clean。

step3追加対向（次固定で実施）: 同じ実P3のT4旧writerを実thread Eventで保持した間はunresolved、その実終結後だけretry_allowedとする。未ログイン/実端末違い/資格違い401、実別tenantのrecovery404を追加する。control既逆順競合・登録先勝ち/退役先勝ち・旧NULL/別body/後着の同じcaseをP3にもパラメータ化し、P3/旧Eventの互いのreaderが混同しないことと未知phase/混在D1の拒否も固定する。成功は実行後に追記する。

step3候補追補: P3/receipt関連とAPI appの回帰で、既P3 3routeがappへ登録済みなのに起点4dの完全期待集合へ未掲載だった差を確認した。routeの削除/部分一致化はせず、既実装のchange-target/change-confirmation/change 3件とoperation IDを完全期待集合へ追記し28件が成功した。barrierの配列要素getterがArray.mapの値読出しで検査前に実行される問題を、descriptorだけを調べるArray.fromへ修正し、getter未実行の対向を追加。FE対象5file/67件成功（1件追加）、既wire/数学/認可の成功条件は変えない。

追加owned run1@f32454e6結果: 1 failed/2 passed、221.61s。controlのEvent/P3両caseは成功し、旧NULL不可/別body拒否/未登録後着/登録先勝ち・退役先勝ちの実advisory競合/相互reader非混同/未知phase・混在D1拒否を確認した。P3HTTPはold-live未解決・実終結後復旧・未ログイン/端末不一致401・別tenant404まで到達したが、作者が追加した最後の404 JSONをFastAPI既定detailと誤認し、実際の共通error envelopeとの不一致で失敗した（compiled行1028）。成功扱いにしない。製品応答を変えず、同一試合の既GET越境404本文とfull equalityに修正してP3HTTPだけを再実行する。成功済みcontrol2caseは同じsource/inputなので反復しない。

製品sourceはbackend/controlがda7a933c、FE共通helper/barrierが31b95027から変更しない。rootの限定非作者確認は該当差分だけで、旧605レビューを保持する。最終合成/全path/人間逐行確認やP6 blindへ拡張しない。
