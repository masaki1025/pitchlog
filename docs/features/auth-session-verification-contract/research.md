# C1 調査記録: 認証 session 確認

## 2026-10-14 の基線

- `origin/develop`: `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`。
- PR #119: open / behind、HEAD `bf43ef93f8a9a2244b2bd5e06d1906ffbcda11de`。login / logout / password変更、HttpOnly Cookie、`tenant_access.py` を所有する。core-guard / harness は失敗中で、人間逐行確認待ち。
- develop の U-F2 auth store は `teamName` が非nullなら認証済みとし、`signIn` / `signOut` / `expireSession` が QueryClient clear と `authEpoch` 増分を行う。検証待ち状態はない。
- develop の U-F6 client は `credentials: include`、応答前後の `authEpoch` 照合、401時の `expireSession()` を持つ。

## 問題

login 2xx の後に session がnetwork / 5xx / DTO不正で失敗した場合、Cookie は有効な可能性がある。その失敗を401と同一にすると、サーバー認証状態を誤表示する。逆に旧store/cacheを維持すると、Cookieは新tenant、画面は旧tenantという組合せが生じる。

このため、Cookieが変わり得る時点で旧client状態を破棄し、session 2xxだけを認証済み、session 401だけをサーバー未認証、その他を結果未確認として保持する。

## 共有資産

- PR #129 はopenで、`contracts/authz/**`、route registry、HTTP route matrix、`contracts/tenant_boundary/base-allowlist.json` 等を変更中。
- PR #131 はopenで、`.claude/core-areas.json`とtenant boundaryの複数凍結資産を変更中。
- PR #132 はopenで、`.claude/core-areas.json`、core guard、tenant boundary の複数凍結資産を変更中。
- いずれも未統合であり、C1のdevelop基線ではない。C1製品実装時に所有状態を再取得し、未統合の共有資産を変更しない。
