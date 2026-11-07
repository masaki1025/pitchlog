---
feature: mvp-runners-batted-completion
status: active
branch: feature/mvp-runners-batted-completion
承認: PO委任Codex/root、2026-11-07、対象c862a2e3、計画SHA 9fe83b5e922a23c482d959d28cb894103bfaeeb34ff077e8221129c1f7098447
重さ分類: コア領域
計画レビュー周回: 1
確定ゲート周回: 0
---

# 明示走者観測の4安打を同候補の実画面・保存へ通す

起点b72d2531。旧fdab2a64/31d9f303 spikeは比較原本で、現b72は既に複数走者/HRのdomain・provider・物理保存と一二塁HRの実画面caseを持つ。旧「一塁一人/単打二塁打」制限を再実装しない。現物を再利用し、未実証・実接合不足だけを閉じる。

今回の操作は、記録者が各在塁走者の実到達/停止を選び確認した通常安打4種。失策なし・妨害なし・第3アウトなしを既閉観測で確定できる範囲に限る。フォースは既唯一artifact、得点/打点は既RBI-06/RBI-08の採用範囲を維持する。追加因果・第3アウト時機が必要な操作をnot-appliedへ推測補完しない。D07既定は二死二三塁単打の既1行から拡張しない。現時点でこの範囲の新意味裁定は見つかっていない。原典で閉じない箇所が実測で出た場合は、その箇所だけrootへpacket化し、依存しない操作を続ける。

## 専有編集path

まず既製品sourceを変えず、既3画面caseを同候補で実行する。以下の範囲だけを本担当が編集する。
- `frontend/src/domain/{battedHit.ts,battedHit.spec.ts,state.ts,state.spec.ts}`（実不具合が判明した場合のみ。新計算核を作らない）
- `frontend/src/api/runnerAdvanceWire.ts` とその専用spec
- `frontend/src/screens/GameScreen{BattedHitObservation,OrdinaryPitch}.vue` と各既spec
- `frontend/src/screens/GameScreenOrdinaryPitchProvider.ts` とその既spec
- `backend/src/pitchlog/domainrt/lineup_prefix_source.py` と既走者観測照合の専用test
- `frontend/src/screens/GameScreenRunnersBattedHits.e2e.ts`/同playwright.config.ts
- `backend/tests/db/test_runners_batted_hits_screen_e2e.py`
- 本plan

contracts/正本/根幹SQL/manifest/pin/fixtures/唯一artifact/共有台帳/root startupは編集しない。実修復で不可分の正式契約・SQL admission・artifact再生成が必要なら、差分とSHA/既case根拠をcacheへ渡しrootで直列接合する。P3作者とのartifact所有はrootが調整する。候補用に成功Port/応答/認可/記録権を代用せず、canonical wireを旧形へ書き換えない。

## ステップ

| # | 実行 | 終了条件 |
|---|---|---|
| 1 | 現source/pin照合→既3画面caseの実測→実在障害を修復 | 固定候補で実新規作成/開始/一塁単打・二塁打・一二塁HRの既経路を使う。基線/新規障害を区別し、必要なroot接合差分を最小化 |
| 2 | 未実証の複数走者/三塁打/満塁HR等を実画面driverへ追加 | 操作で走者を作り、各走者の実結果を確認して4安打へ渡す。最低でも複数走者単打、複数走者二塁打、走者あり三塁打、満塁HRを再取得/責任投手/得点/打点/履歴まで照合。DB事前投入で走者を作らない |
| 3 | 同一候補の再送/reload/越境/途中故障・最終固定 | 同D5再送は非二重加算、実再読込はサーバーafter、別tenant拒否、走者ありpayload固有のT4故障でevent/play/runner/checkpoint/ledger全取消。非作者確認・source固定・証拠/残件をrootへ渡す |

実PG/実HTTPS/browserは共有DSN unset、共通owned-pg-browser-network.lockを全寿命保持し、実行WT sourceを固定する。loopback Chromiumを実機/運用信頼TLSと混同しない。失敗を成功へ読み替えず、既提供範囲と今回追加実証を分ける。正式受理/全MVP完了は別。

ステップ1初回実測: d1608585 detached、3003source前後一致、共有DSNunset/共通lock、152.97sで失敗。実画面の新規作成/開始後、既Hostが自然にv3へ遷移するのに旧driverが既に消えた記録入口buttonを待っていた（3case全て同じ）。越境caseも先行result ID未生成で未成立。API/計算/保存成功の証拠にはしない。開始button前から実prefix0 GETを捕捉して自然な記録画面へ従うdriverへ是正し、結果IDファイルをpytest tmp_pathへ分離する。製品source/値期待/認可/artifactは不変更。Node/pnpm/docker/既TLS/venvはpreflight済み。

ステップ1追加診断: 7b5a7fd8の実新規作成/開始/prefix0は成立したが、最初の無走者単打保存が503。1caseだけの透過observerでPlayExportWriterUnavailable→UndefinedFunction/SQLSTATE42883、stats_native_flush:269→play_export_producer:149と確定（83.46s、source不変）。旧b72は0047 tableのみでCSV同TX4関数が未配備の共通依存であり、rootの正規47/provider固定供給を待つ。同基線の全case反復や保存hook迂回は行わない。途中の診断run3はgrep選択ずれでtest未実行、成功証拠にしない。

ステップ2候補: 操作で走者を作る4case（複数走者単打/二塁打、走者あり三塁打、満塁HR）を追加。各走者実結果を入力し、全41列/物理runner/status語彙/ID/責任投手・得点/打点flag・同D5原文再送/reloadを照合する。正の得点caseでは実T5のruns/rbi/runs_allowedがavailableで実数一致することも確認し、未供給を0へ補完しない。既唯一計算/観測型/正式資産/artifactは変更せず再利用。型/lint・構文は成功したが、実測はroot依存解消後で未成立。

ステップ3候補準備: 同じ実appにowned時だけ固定header→既testing_crash_hook(after_t4_projection)を束縛する試験middlewareを追加。正常要求は無変更で、失敗応答も製造しない。走者あり2球目の元本文/Cookie/端末/attemptを保ったままT4へ到達させ、実500・未確認表示・実GETが先行1球と完全一致することを確認する。失敗した実event/play/D5 IDでrunner/ledger/stats/CSVの残存を個別に拒否するDB補助を用意した。BE/FE型・lint・bootstrap構文成功、実測は正規provider固定点供給後で未成立。追加コードはE2E2pathと本planだけ、製品source/唯一artifact/正式契約/根幹SQLは変更なし。

共通依存接合: runner 0f89fa8eへroot固定ae82631b（9c0f101aの標準0047/catalog26宣言＋canonical S0→current startup helper）を通常mergeし、1674459dで衝突0。取り込み40pathはroot原本を採用し、独自正式資産編集・SQL後付注入・artifact再生成は無し。既fixtureが実advance_current_product_from_s0を呼ぶため、本担当の重複fixture修復は不要。BE対象Ruff/Ty成功、既TLSの存在・Node24.16.0/pnpm11.22.0を確認し、同固定候補の正常7＋fault1＋越境1画面caseを実測する。
