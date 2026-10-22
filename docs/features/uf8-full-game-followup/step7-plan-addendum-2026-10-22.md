# U-F8既存計画ステップ7の最小範囲追補案（最終承認前）

## 1. 対象・承認境界

本書は[既存9ステップ計画](plan.md)の**未完ステップ7だけ**を具体化する。原承認SHA-256 `935bac90426571acf1c9a66b8d41ff0097e14232421fc5f80ff966e9f5551cf4`、原計画査読3回/13件全採用/最終P0限定/最終反映未再査読、各製品PRの回数/採否を保持する。表を10ステップ以上へ改番したり、完了済み1〜6へ後発作業を追加したりしない。

2026-10-22のPO指示が許可したのは、提示済み9パスの追補起案と、その直接影響に限定した**追加独立レビュー1回**。本書の最終承認・7.7正式受理・正式反映・新規PR作成/公開・マージ・本人確認の代記は許可されていない。原計画frontmatterの承認済み表示を本追補の承認として使わず、承認前に9パスへ実装を広げない。

目的は、既承認の実App/Auth/専用DBによる封鎖ブラウザ検査を必須frontend CIへ接続するために必要な、共有凍結入力と既存生成物の限定整合である。新しい認可・SQL/operation・計算・Port・機能を追加しない。iPhone全操作・閲覧10秒・成績・CSVの不足は[供給表](supply-map.md)に残し、本追補へ抱き合わせない。

## 2. 追加する正式パス（上限9件）

原計画3節はCI/base-allowlist/census/history-snapshots/比較manifestの候補更新を認めるが、以下の正式9パスを列挙していなかった。この**パス許可の差**だけを追加提案する。全行のU-F8変更は、現在は**公開済み候補**である。#171に既統合なのはfeature内のコピーで、正式パスへのU-F8差分反映は0。対象パスそのものに別担当の既統合変更があることと混同しない。

| 正式パス | 目的・許す変更（既承認との差） | 編集担当 | 合格条件 |
| --- | --- | --- | --- |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | CI外部入力の追随。revision/identity/source_digest・受理履歴だけ（未列挙cache契約） | 引渡し後のU-F8が既存生成経路を使用 | 失効定義/負例不変、入力・digest・版が一致、全旧履歴/署名を保持 |
| `contracts/tenant_boundary/db-api-inventory.json` | inventory_revision/identity・履歴だけ（未列挙DB目録） | 同上 | SQL/許可行の追加削除なし、実目録との照合・snapshot保持 |
| `contracts/tenant_boundary/negative-fixtures.json` | fixture_set_revision/identity・履歴だけ（未列挙負例契約） | 同上 | 負例本体と拒否能力を保持。通過しない試験を除外しない |
| `contracts/tenant_boundary/repository-contract.json` | revision/identity/source_digest・履歴だけ（未列挙repository契約） | 同上 | operation/SQL許可不変、生成Pythonと一致、既存境界試験が通る |
| `contracts/tenant_boundary/runtime-authz-contract.json` | runtime revision/identity/source_digest・履歴だけ（未列挙runtime契約） | 同上 | CAP/route/rule不変、認可・tenant拒否と生成整合が通る |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | revision/identity/source_digest・履歴だけ（未列挙tenant文脈契約） | 同上 | bind/SQL許可不変、越境負例・生成整合が通る |
| `backend/src/pitchlog/authz/runtime_contract.py` | 契約からのrevision/SOURCE_DIGEST定数だけ（未列挙backend生成物） | U-F8が既存生成器を使用、手編集なし | 正規再生成とbytes一致、認可動作の新作なし、runtime契約試験が通る |
| `backend/src/pitchlog/repositories/repository_contract.py` | revision/SOURCE_DIGEST定数だけ（未列挙backend生成物） | 同上 | 正規再生成とbytes一致、SQL/Port追加なし、repository契約試験が通る |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | revision/SOURCE_DIGEST定数だけ（未列挙backend生成物） | 同上 | 正規再生成とbytes一致、文脈/越境契約試験が通る |

6 JSONの実差分はhistorical公開候補で履歴を除けば版/identityと4件のsource_digest、3 Pythonは定数だけと機械照合済み。実基線の再導出で上限を超えるパス/内容が生じたら実反映せず、具体差分を改めて判断へ戻す。先行PRが所有する新登録や製品動作をU-F8変更へ混ぜない。

## 3. 既承認部分との最小の接合

既承認の `.github/workflows/ci.yml` の変更は、既存必須frontend jobのまま専用使い捨てPostgreSQL・実App/Authを使う `pnpm run test:browser`（sealed-ui固定）を追加し、その依存のpath filter/環境準備を接続する候補である。新しい任意jobへの逃避、continue-on-error、失敗/skipの成功化、既存harness/backend/認可/負例の対象削減はしない。frontend/backend依存を使う既存試験経路が根拠で、依存のない製品機能追加はない。

- package/lock・GameScreenの試験設定/支援は#171で統合済み。現時点ではその不変部分を作り直さない。既存の1 worker/固定projectと失敗時の秘密DOM・credential非出力/owned DB片付けの境界を維持。
- CIの成功はsealed-uiだけの成功。実Port未提供のreal-gameをskip/fixture成功で代用しない。実試合・GAP-05・原子性・iPhone実機・全体DoD完了とは別。
- CI外部入力が凍結契約のdigestへ波及するため、上表と既承認base/census/履歴/snapshot/manifestを同じ候補単位で照合する。9パス単独で基線だけ進める正式反映はしない。
- 既存生成器/検査器/認可境界のロジック変更、core登録パス追加、DB migration/grant/共有DB適用は本追補の範囲外。必要が生じた場合は実装せず判断へ戻す。

## 4. 所有・編集・統合順と固定基線

[順序票](step7-sequencing-2026-10-22.md)の実測/担当回答を再利用する。#174は9対象中8件、#173は9件全てと重複。D/#175の正式read登録も同資産を使うため、U-F8は**#174実統合→#173の再導出/受理/実統合→Dのread登録実統合・引渡し→U-F8**の順に自分の正式編集を後置する。#175がDTO/componentだけで先に統合されても、read登録の実引渡しがなければこの条件は満たさない。Dがread登録の提出単位を分けた場合は実提供単位のSHAを記録する。

#174/#173は取得時点で番号取得資料だけのDraft、#175はpreparingの部分実装を公開したDraft。既存のU-G1分担受理を保持し、Dのフォーム/provider/APIを並行実装しない。PO指定#174→#173順はU-R1担当も記録し、#174統合前に衝突資産をpush/最終7.7値確定しないと回答している。各実merge/所有引渡しは未提供であり、通知や候補HEADを所有解除/製品提供としない。

現調査基線はdevelop `760c04d540b22190cab076165f1b4e35ae473a1f`。**最終7.7に用いる基線Bはまだ未確定**で、上記実統合/引渡し後のdevelopから固定する。B中の全受理履歴・署名・全snapshotをprefixとして保持し、25件など旧固定件数へ切り詰めない。未統合枝や昔の候補after値から導出しない。

## 5. ステップ・コミット・提出単位

### 現在（計画資料のみ）

追補案・査読結果/採否・作業ログを既存追跡枝へ計画系コミットで保存する。ステップトークンは付けない。#171はMERGEDであり再利用/再開しない。`cf9702ab`等の追跡コミットはdevelop未統合のまま識別し、既統合扱いしない。今は資料だけの新規PRを作らない。

### 正式変更を届ける予定単位（未許可）

範囲の最終承認と上記引渡し後に、**U-F8ステップ7「正式CI接続」の必要実差分を持つ単一の後続Draft PR**として、既承認CI/base/census/snapshot/manifestと追加9パス、関連する検査/計画・採否記録を一緒に届ける。現追跡枝の未統合資料も必要分だけ同じ提出単位へ含める。資料PRと正式資産PRへ二重に分けず、#171番号を新7.7受理IDに流用しない。

新規PRの実作成/番号確保は、その具体的な提出差分を用意して別途許可を得る。番号取得が許可された後は、同じ提出単位でBと候補C・全前後値・実PR番号を固定して7.7へ提示し、本人受理前は候補のまま保持する。受理/署名欄を代記しない。正式反映・公開・Draft解除・マージはそれぞれの既存ゲートに従い、本追補承認へ抱き合わせない。

**実装は未完ステップ7の続行**として、正式反映が許可された段階の1委任/1実装コミットで上記不可分差分を反映する。件名は例えば `ci: 封鎖ブラウザ検査を正式CIへ接続 (ステップ 7/9 正式接続)` の完全トークンを1個だけとする。将来の検査是正も同じステップ内の是正として記録し、完了済み別ステップへ押し込まない。8/9の製品接続をこのコミットに含めない。7.7の正式受理記録の実反映は本人ゲートの指示に従い、事前の計画コミットに成功済みと記入しない。

### 宣言・JSON登録との整合

9正式パスは既存の `contracts/tenant_boundary/*`、`backend/src/pitchlog/authz/*`、`backend/src/pitchlog/repositories/*` のtenant-isolation登録範囲内。CIも既存guard_paths。新しい実行入口/登録パスを足さないので、core宣言/JSON登録コミットを今回新設する必要はない。JSON契約の値更新と `.claude/core-areas.json` の新パス登録を混同しない。先行D/#174/#173の新パス宣言→別コミットJSON登録は各所有計画のまま保持する。再導出で新パス宣言が必要になったら、本追補では実装せず別判断へ戻し、宣言とJSON登録を同一コミットに詰めない。

## 6. 合格条件と検査

- B/C・生成器source SHA・全正式入力blob/逆依存閉包、全13相当の完全before/after bytes/hashと識別子/外部入力、snapshot/corpusを同一提出単位に固定。数13も固定上限ではなく、パス増があれば別判断。
- 既存履歴/署名/snapshotの完全prefix保持、追加行の受理前人間欄は空。隔離Gitで通常apply --check/実applyし、生成3本の正規再生成一致・契約/認可/越境・凍結/archive/corpus検査が成功。既存の拒否/失効/負例本文・対象範囲を弱めない。
- 正式反映後は変更に応じたroot/backend/frontend品質・全必要pytest/Vitest、CI frozen/tenant/core/document検査と必須frontendブラウザ段が成功。旧#171の29419/1793/隔離84件を新基線の成功へ流用しない。harness等のCIを許可なく取消/中断しない。
- 実App/Auth/専用DBのsealed-uiで正常・拒否・通信失敗・遅延・再読込/再起動・複数タブ/tenant切替を既存試験のまま確認。real-game未接続は未達のまま。本追補の承認/CI緑を開始・取消/訂正/確定/保存/送信/再開の封鎖解除へ使わない。
- 原計画の全体DoDとステップ8〜9、GAP-05/原子性/実1試合は未完を保持。追加独立レビューの実対象/採否・反映後未再査読範囲を人間へ提示し、本人逐行確認は代記しない。

## 7. 追加レビューの固定方法・残判断

今回の追加枠は**この追補案と9パスの直接影響だけ、1回**。基本2回/原計画査読のやり直しではない。固定対象HEAD R、起点 `cf9702abfc35b6a8d4dac157da60784993e9a7ea` からの完全binary diffとSHA-256、候補patchとSHAを外部固定manifestに記録してから読み取り専用で依頼する。

参照する候補は[公開済み完全patch](step7-candidate/candidate.patch) SHA `5a012348e3a08b47513804f3a6740094182a025065dbb285c37fa0af12d8306b` と[9件抜粋](step7-nine-paths-published.patch) SHA `b666700c7a1ad4ea152e35a41425fb281a992f80afed87f8ea0a0b102c5a73ee`。[v3](step7-scope-extension-v3.md) SHA `1002b6ca303948aed454ed0207b2bbcdabd9e466475657f86e1b6a6ae8730da7` と[既存査読証拠](step7-review-evidence-2026-10-22.md)を再利用する。候補はhistoric161ab基線/旧24履歴のままで、最終7.7値として再承認を求めない。Rで凍結し直すのは追補の射程/責任/合格条件であり、新しい正式候補値ではない。

査読後は指摘を採否記録へ反映し、最終案F/Rの差を未再レビューとして明示する。1回を使い切った後に確認のため再実行しない。最終承認、後日B/C固定後の7.7本人受理、正式提出用PRの許可、必要な人間逐行確認・公開/マージ判断は別途残る。
