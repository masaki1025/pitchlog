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
