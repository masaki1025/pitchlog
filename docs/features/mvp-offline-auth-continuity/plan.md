---
feature: mvp-offline-auth-continuity
status: active
branch: feature/mvp-offline-auth-continuity
承認: PO委任によるCodex主担当/root判断（2026-11-06、FR-012断中継続の認証接合修復）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 通信断後の記録継続と同提示token更新の境界

既要件FR-012の開始済み試合の断中全記録操作、NFR-011の利用中スライディングを両立する技術接合。固定d335反例はcache lifecycle-cookie-offline-gap-20261106/REPORT.md（SHA3bcc848ff5d80f7ac9396852a8718f77e58be1074e2baee1d2cecd7db701f392）。最初の同期POST通信断/started GET AbortでCookie不確実通知がverified/tenantを破棄し、次のローカル記録を閉じる。P0相当の未接続として是正する。認証/C2/401/明示logout/tenant切替/実権利/単一書き手/耐久性を弱めない。POの11/7 0時再評価指示に基づき、候補を接続後に独立レビュー・必須検査をまとめる。rootが本WTの唯一writer。

1. 同提示token更新だけを許す保護業務routeのmethod/path/operation IDを閉宣言へ固定し、server middlewareがそのrouteで発行するSet-Cookieを真正require_tenant_accessのcanonical renewalだけに限定する。401では更新しない。認証変更経路は除外し、NFR-011の期限延長は維持。明示Set-Cookieによる別token/削除/別属性を防止する正負対向を付ける。対象は新contracts/authenticationの閉policy、backend api/tenant_access.py・app.pyと対応tests。正本の既認証意味は再裁定しない。
2. clientは上記policyに一致するC2要求で、同tenant/同authEpoch/検証済み状態が維持されるnetwork/Abortに限り同token更新をidentity不確実性と混同しない。古い応答によるCookie巻戻しは同tokenでもあり得るため、authEpoch変化・跨tenant・stale・共有notice・401・C2不一致・login/logout/password/session/未知経路の失効拒否を維持。対象はfrontend api/client.ts・閉policy matcher・対応spec、backend policyとの整合検査。常時verified=trueや資格値の推測は禁止。
3. 既ordinary/NP/lifecycleの耐久queue/baseと接続し、実画面の開始→断中複数記録→reload→順序同期→再取得をowned環境で検証する。auth不整合修復だけで全操作の断中継続を完成扱いしない。最後の真正tenant/grant/baseを用い、未知履歴/世代/未確定結果を推測しない。必要なcontroller接合は固定候補の具体不足を根拠に本planへ最小追補し、T1の別実装を作らない。

候補の対象HEAD・diff SHA・独立レビュー・対向・全件検査を揃えて通常統合する。共有DB/運用公開/秘密発行は対象外、実機とownedブラウザを区別する。独立確認前に正式受理/人間確認とは記録しない。
