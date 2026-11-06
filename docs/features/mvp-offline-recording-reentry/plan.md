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

所有分割: rootはpermission store/readonly intent lease/health gate/router/local host/OrdinaryPitch.vueと文書。別作者game_operations_final_independentはOrdinaryPitchController・PitchCommit/PitchAcceptance・必要なprepared envelope補助と対応specのみ。共有同一fileへ並行書込みせず、coreの最終候補は別レビュアーへ渡す。
