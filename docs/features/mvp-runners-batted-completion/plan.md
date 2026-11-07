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

標準47 run5: 3ce62069で457.20s、3032source前後一致/clean/共有DSNunset/cleanup。実画面の正常7case＋越境404は成功し、複数走者単打/二塁打/三塁打/満塁HRの明示結果・同本文再送・reloadを実証。T4故障caseは実500と未確認表示まで進んだが、その後の実GETをAPIRequestContextで行う際にHTTP/2 pseudo-header :authorityを転記したdriver TypeErrorで失敗。DB全照合は未到達なので全case成功にしない。HTTP header輸送で認められないpseudo-headerだけを除去し、Cookie/端末/その他原値を維持する最小是正を行う。元run5/log/正常7結果はcacheへ保存済み。

## 実測からのT5供給追補（PO委任root・2026-11-07）

run6 d4444710は3032source不変/clean/DSNunset/cleanup、Playwright9case成功。DBのruns/rbi/runs_allowed実数照合は、native_projectionがruns_rbiを一律unavailableにしてrunner_scoresを生成核へ渡さず失敗した（496.52s）。UI成功を成績完成へ読み替えない。

専有pathへ`backend/src/pitchlog/stats/facts.py`、同adapter専用`backend/tests/stats/test_native_runner_scores.py`、既adapter期待の専用testを追加する。生成facts.py/model/SQL/math/正式assetは非編集。真正V7中の唯一artifactが確定したrunnerDefaultAdvance/batterDestination、明示source走者ID/責任投手、既打点判定だけを生成T5のrunner_scoresへ写す。得点差で人数・選手を推測しない。まず既通常球の確定ゼロと、RBI-06/08で閉じる失策/妨害/第3アウトなしの4安打を閉対象にする。第3アウト/不足観測/未対応causeはunavailableを維持し、D07は拡張しない。得点差はコピーした結果の整合拒否にしか使わない。

正負pureでID/責任投手/打点・scoreless・不足観測・第3アウト拒否・原値非変更を固定し、rootの非作者source確認後に実game全7のDB集計を同候補で確認する。T4故障は全T5版/source/factの送信前実DB集合と故障後集合を読取専用で比較するfault単独試験を追加し、既UI9成功と混同しない。rootは正式pin/manifest/資産の所有を維持し、adapter実byte追随が必要ならcache packetで受け渡す。

T5追補採用: rootはff207de5/plan SHA b04e47b3a193661c6b6d85c329e3824c841c39a40983a368e0149bc1bc1d6ce3全文とRBI-06/08を照合し、PO委任Codex/root・2026-11-07として着手可。adapterはT1到達/打点真偽と原本走者/責任IDを有限コピーし、生成核は不変更。正準19安打＋明示4配置＋欠測/因果/重複ID/override対向＋初球通常0の専用39件を含め、関連5群408件成功36.58s、BE Ruff/Ty成功。NP通常球の旧unavailable期待だけを真正complete空集合へ追随。新sourceの実DBは未実証、root限定非作者確認へ渡す。

T4全版対向追補: 画面が真正先行1球を保存した直後、unique pytest tmp内のgame ID通知をatomic renameで渡す。ownedホストの読取専用connectionが当該tenant/gameのstats_fact_versions（旧非current含む）/sources/facts全行を封印してから2球目送信を許可する。T4後は同3集合を全値比較し、新旧版の残存を拒否する。owner資格はapp/browserへ渡さず、通知に資格・本文を含めない。専用fault pytestは実画面で同前提1球を作って1caseのみ選択、通常受入pytestは正常7＋fault＋404の全9を維持する。範囲envはall/faultの閉2値で未知拒否。BE/FE型lint成功、実測は次。

root非作者確認の是正: 25ceの冒頭outEffect0限定は、正準Kの非生還/3flag false/不変scoreで証明済み0も未供給にしていた。先にこの確定0を確認し、正得点供給だけoutEffect0へ限定する順に是正。正準hold/nullも値域内として扱う。K27行で走者保持・第3out・攻守交代・次回への実出力0と、score改変時のunavailableを固定し、専用67件/関連436件36.91s、BE/FE型lint成功。第3outの未観測正得点を補完しない。fault選択run7は^開始grepの誤りでNo tests found（53.17s/source不変/cleanup、故障証拠なし）。^だけを除去し、--listでexactly1を確認してから再実行する。

実到達点79fe5cca: root限定非作者REPORT SHA b53de3e4f794beb439a32713273acdc363da7376c3ce98d944f4b6934a69b398（独立228pass、新P0/P1なし、4sourcepath限定）をPO委任root採用。run8は故障単独1pass84.87s、run9は同79fe/同owned環境でPlaywright9＋pytest1pass495.88s。3033source不変/clean/共有DSNunset/cleanup。正常7全41列・物理runner・責任投手・T5 runs/rbi/runs_allowed実数、同原文再送/reload、別tenant404、runner T4実500/全取消と全T5旧現版/source/factのbefore/after一致を完了。証拠はcache t5-fault-only-run8/t5-all-nine-run9。正式受理/実機/運用TLS/断中打球/全MVPは別。
