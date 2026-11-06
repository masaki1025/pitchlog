---
feature: mvp-offline-recording-reentry
status: active
branch: feature/mvp-offline-recording-reentry
承認: PO委任によるCodex/root判断（2026-11-06、FR-012の端末内記録復帰を既開始資格へ接合）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 通信断再起動後の端末内記録復帰

FR-012と既開始済み1端末/耐久queueの保証を満たす技術接合。静的shellだけではrouterのsession GETに失敗しloginへ戻る。既authStoreのsessionVerified/isAuthenticated、APIの認証/C2/401/tenant拒否は変更しない。新たな利用者権限/記録結果/記録権成功応答は作らず、最後に実認証/C2で確認した同端末の開始資格・現artifactの保存source・入力語彙を使って端末内の未送信記録だけを継続する。サーバー保存/現時点の権利を確認済みとは表示しない。共有DB/秘密発行/運用公開は対象外。

1. 真正C2 v3 GETで確認したsourceと、実認証下で受信した有限ページの球種語彙をstrict IndexedDBへ保存する。開始received grant/端末、tenant/game/D4/recovery、auth-intent expectedの実nonce/tenant、現在artifactを束縛。保存/読取で閉検査・世代/nonce/同水位別source拒否。同TX get/比較/writeで多タブ後勝ち上書きを防ぐ。既queueやgrantを消さない。キャッシュはサーバー認証の証拠として使わない。
2. game-recordだけで、保存資格が有効かつ通信を確認できない時に専用local入力hostへ復帰する。session呼出前にCookieを使わないpublic health到達確認（同origin/credentials omit/有限deadline）をし、ネットワーク不達/503だけを断中として扱う。401/C2不一致/不正応答をfallback成功にせず、到達できる場合は既session検証を行う。正常認証を偽装せず、local専用scopeは同auth-intent/不確実通知/端末資格を毎操作照合し、logout/切替/未知状態で失効。画面の6前提/Web Locksは維持する。
3. 既唯一artifact/OrdinaryController/耐久queueを再利用し、local scopeでは保存要求を送信しない（常時成功応答を返さず未送信として保持）。語彙は保存した閉ページだけを表示し、足りない選択肢を作らない。オンライン復帰は既認証を再検証した通常画面へ戻して同本文/D5/attemptを順序再送。公開APIは依然実認証/C2/実記録権/同TXを通す。
4. 対向unitと実HTTPS/ownedPGで開始→真正source/語彙確定→断中複数球→reload→端末暫定表示→オンライン再認証/同要求順序同期→GETを実測。APIだけ断と完全断中cold起動を分離。世代/端末/intent変更・logout・未準備・不正source・新D5勝手生成を拒否。非作者確認後に接合する。初ACK直後GET前断、NP/交代/LCのqueued後続は別の未充足であり、普通投球だけの成立を全Must操作/MVP完成にしない。

範囲: frontendの新local録入scope/persistence/hostとtest、router.tsの同record route表示host接合、既recorded restore/PitchTypeの真正保存、OrdinaryPitchの明示local scope対応、対応docs。auth.ts/authStoreの検証済みを作る変更、server認可/計算複製/正式assetsは対象外。rootのみwriter。

## 非作者P1反映（2026-11-06、PO委任Codex/root）

plan b75adacfの非作者REPORT fcc707cb…の3 P1を採用し、実装条件を具体化する（旧計画を可決済みとは扱わない）。

- local追記は送信無しの別結果として実装する。既普通投球を唯一kernelで生成し、同ゲームWeb Lock内で本文全体（V12含む）/D1/D2/D5/予約ID/attemptをstrict envelopeへ先に確定、同attemptを既attempt storeへ束縛、その後だけqueueへE0追記する。queueが無い準備済orphanは、保存本文と予約IDをそのまま用いる修復だけを許し、別D5/attemptを生成しない。queue存在なら既attempt必須。HTTPは呼ばず、成功ACKを合成しない。V12/資格変更で本文を置換せず閉拒否する。
- 複数IDBを一つの原子TXとは呼ばない。ゲーム排他を先に取り、同じauth-intent lock名の**read-only非同期lease**を取る別helperを用いる。既withAuthIntentの同期callbackへPromiseを返す実装は禁止。authの書込み資格intentLockHeldは立てない。auth lease内ではlocal IDBだけをawaitし、通信/別lock待機なし、取得不能は未受理。開始/端末/nonce/phase/tenant/uncertainty、source D3/D4/ref、queue次D1/未終結suffixを操作前後に照合し、変化/失敗で成功表示や送信をしない（既追記は消さず隔離/復旧対象として保持）。
- cap更新は、同nonce/世代では水位後退と同水位別refを拒否。未終結slotがある間は旧capを保持し新headへ置換しない。完全ACK済みprefixだけなら新しい真正C2 headをstrict確定してから基点を進める。新nonceは古capで許可せず、実認証/C2で改めてsourceと語彙を確認した場合だけ新capを確定する。旧queue/本文/attemptを消さず、同一内容の未終結列を先に同期する。
- オンライン復帰は実session/C2成功後だけ、最古slotを同本文/D5/attemptで再送し、ACK適用→真正GET→次の最古を自動反復する。非成功ACK/HTTP不明/再取得不明/資格変更で止まり、手動押下無しで全suffixが空になる正例と件数通知を確認する。health成功直後session通信断は安全に閉じる未充足として残す。5秒最適化はPO指示で後段だが安全/自動順序条件は維持。

所有分割: rootはpermission store/readonly intent lease/health gate/router/local host/RecordedRestoreと文書。別作者game_operations_final_independentはOrdinaryPitchController・PitchCommit/PitchAcceptance・必要なprepared envelope補助・OrdinaryPitch.vueと対応spec（22:54 JST追加移管）。共有同一fileへ並行書込みせず、coreの最終候補は別レビュアーへ渡す。

## source非作者初回4指摘の反映（2026-11-06、PO委任Codex/root）

固定5d46ec3aのsource REPORT SHA77e523089c8eeed408be7f3e1b7bac5e416bb40e344eec3ad03a1855ac420209はP1=2で未受理、固定7796e3b3のUI REPORT SHAe8f49cdb246b2703229ca2b71c6440710d35d882247925b40cef7b03f6672ea5はP1=2で未受理。これらを可決とせず同じ反映周で是正する。

- 同D1/refの別headはprefix_refのみでなく閉head全値一致を要求する。独立反例と同じstate/afterの両balls変更（構造valid）を拒否し、旧保存原本が全値不変、同head再供給は可の対向を追加。
- navigator.onLine=falseはhintとしても不達成立に使わず、必ずCookie無しの有限publichealthを試す。hint=false/実health200の対向で通信を実行し既session検証へ戻す。
- 最古ACK後の真正GET+新context解析中は、ACK起点の同game/D4/tenant/authEpochだけ旧子instanceを保持する。suspendedで操作・HTTP・語彙採用を閉じ、fresh原本解析完了後だけ解除。別scope/取得失敗/手動別DTO更新は従来通り破棄。作者UIはsuspended同値で未送信観測と四確認を保持し、解除時再inspectする。
- 再接続は許可済みrecording queryだけを使い、router.replace force:trueで同じURLでも毎回guardを再実行する。reconnect=1を認証戻り先へ追加しない。実VueRouterで2回押下のguard2増分・query有限を固定。

root対象4suite68件・型成功、元作者UI/親66件・型成功。これらはmock/IDB単体で実認証/PG/完全断中ブラウザの証明ではない。67264062にはproduction build/preview/SWを使うowned E2E source準備があり、実行・最終非作者再確認・正式受理は未了。ソース固定後に実測し、NP/LCqueued/開始ACK直後GET前断の未充足は維持する。

## 全体表示ゲートの接合追補（2026-11-06、PO委任Codex/root）

r2は実create/start/C2 cap/語彙とSW制御まで進み、cold画面非表示で停止。source確認でApp.vueがauth=falseの全protected routeを描画せずloginへ戻すため、routerだけのlocal資格接合では成立しないと判明。App.vueを編集範囲へ最小追加する。router内private WeakMap/shallowRefで保持する真正brand付き・同fullPath/game-record/current scopeだけをAppへread-only公開する。protectedReady/authStore/server sessionは変更せず、local専用branchの表示だけ許可し他protected画面へ流用しない。同localから再接続中は内容を隠してguardの真正認証結果を待つ。失効/別scope/取得失敗は既loginへ。3 App/実Router境界を追加し既routerと58件通過、型成功。r3の別停止はlogin POST未発行であり、このApp修復の成功証拠とはしない。後発source再レビューと実画面は未了。

## App失効表示P1の反映（2026-11-07、PO委任Codex/root）

9b2の非作者REPORT SHA2dc712db975f839e0c3669fc5feee8e3e27e5aae8a21c2406984deb9f73f1cc3はP1=1で未受理。LocalRecordingSessionのactive/epochをshallowRefとして実computed依存にし、disposeだけでcurrent/表示/identityが失効する。App対向から人為authEpoch加算を除き、実scopeのcomputedもdispose直後falseを検査。cold再生成writerは旧scopeを使い回さず、同じ6条件のまま新scopeへ束縛する。localから公開ガイド等へのnavigation中も旧保護内容を隠してguard決定を待ち、中間状態がloginへ割り込まない対向を追加。関連23/型/lint成功。66d50b24のcold実画面1passed73.504秒はこの後発修復の再実測/受理ではなく、旧固定版の正経路の証拠として保持する。
