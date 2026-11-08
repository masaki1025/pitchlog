---
feature: mvp-p3-target-position-range
status: active
承認: PO委任Codex主担当/root（2026-11-09、既26対象承認の通常不具合修正として2path所有追加）
重さ分類: コア領域
branch: fix/mvp-p3-target-position-range-20261109
created: 2026-11-09
計画レビュー周回: 1
---

# P3読取の対象D1と頁件数25を分離する

起点21ca8f17cf35410ea3f88fc303e778f2fec4a562。GC修復接合の実画面は26保存/GET/DB26closedを通過したが、26対象GET待ちで停止。readP3TargetOffer/readP3ChangeConfirmationのHTTP前`d1 > 25`が残り、26を送信前にthrowする具体的な不整合を確認した。旧23球EOFの実因・根治は未証明のまま。

backend既read_change_target_snapshotは水位25超を全頁訪問し真正対象を保持する。confirmationもpaged読取を再利用し、routeは1以上2**63未満。JS側の既positiveは安全整数1..2**53-1で、同期wire_original/modelの_MAX_SAFE_INTEGERとも整合し、backendbigint以内。25はread頁件数であり対象D1上限ではない。

編集はfrontend/src/api/pastCorrectionProduct.ts/同.spec.tsと本計画のみ。両読取入口の`d1 > 25`だけを除き、既positive安全整数、UUID、tenantBound/C2、signal、原応答全値/対象一致/D5/receipt照合を保持する。controller/Vue/queue/#current、製品期限/認可/SQL/正式資産/唯一artifactは変更しない。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 読取2入口の位置範囲修復と正負固定 | 25/26/安全整数上限は真正応答一致時だけ読取可、上限超/非正準/小数/bool/未知はHTTP前拒否、不一致応答拒否・既C2保持、型/lint/対象pure成功 |

PGはINT担当終了後rootの順序許可まで開始しない。純試験成功を26訂正/後続終了/CSVの実測成功とは記録しない。前runは封印保持し、次実走は固定修復をroot非作者確認後1回へ。


## step1候補

製品差分はAPI読取2関数の`d1 > 25`除去だけ。正準25/26/Number.MAX_SAFE_INTEGERを両GETで照合し、正準安全整数外15種はHTTP呼出0、不一致対象/game/D5応答拒否を追加。既API・controller・UI・同版頁4suite44passed3.32秒、vue-tsc/対象ESLint0。テストの別game照合はtenant分離自体の実証ではなく、tenantBound指定と既C2経路は不変更。PG未実施、26訂正以降の成功へ読み替えない。


## 同family耐久保存の追補

rootがp3AttemptPersistence.ts/同.spec.tsの所有を追加し、同じ25件上限の混同として追補採用。実26再走前の残存走査で、verifyにもNumber(target.d1)>25が残り、対象GET後の送信前耐久保存を拒否することを確認した。編集へ当2pathを追加し、この1上限のみ除去する。正整数/安全整数、tenant/game/D4/D5/attempt、原JSON/hash全値は保持。25/26/MAX_SAFEの再起動復元、MAX_SAFE超/小数/bool/非正準拒否、API26→offer→原要求耐久保存→confirmation26を実codec/実IDBで接続する。ページ25とbackend非paged分岐の<=25は不変更。PGは引続きINT担当後のroot順序待ち。


## 同family追補の検査結果

両APIと耐久verifyの3箇所だけで位置25上限を除去。25/26/MAX_SAFEの原文/hash/attempt再起動復元、非正準13種の保存拒否、API offer26→実IDB strict保存→再起動同原文/D5/attempt→confirmation26を実codecで通した。既UI/controller/頁と合わせ5suite64passed3.72秒、全vue-tsc/対象ESLint0。初回pure64成功後の型検査で試験側readonly代入3件、2回目は置換漏れ1件を検出し、immutable copyに統一して最終0を確認（失敗log保全）。実DB/実P3訂正は未実施。frontend同familyの位置×25残存は解消し、page_size25とbackend非paged≤25は保持。framegate/#current/queueのtrue化はしていない。
