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
