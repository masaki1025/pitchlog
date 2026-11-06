---
feature: fr012-offline-app-shell
status: active
branch: feature/fr012-offline-app-shell
承認: PO 委任による root の実装範囲指定（2026-11-06、親セッションからの依頼文）
計画レビュー周回: 0
確定ゲート周回: 0
---

# FR-012 静的 app shell の断中 cold 起動

## 判断と既成果

2026-10-10 の PO 決定で `registerServiceWorker.ts` と `public/sw.js` は U-F1 から TSK-533 へ切り出された（`docs/features/uf1-common-ui/plan.md` 64 行、`docs/worklog/2026-10-09-uf1-common-ui.md` 29 行）。現製品に SW 登録・実体はない。既 `vite.config.ts` の CSP/build 閉域検査と domain artifact byte/SHA 検査を再利用する。

root の今回の委任範囲は「frontend serviceworker/build-time 静的資産 manifest 生成/登録/対応テストと専用 docs」。同 origin 固定 build 資産と app shell だけを CacheStorage に置く。API、Cookie、tenant データを置かず、未知・改竄・未完成 bundle は拒否する。quota/更新失敗で既 cache を壊さず、試合中の強制 worker 切替や `skipWaiting` をしない。認証 guard/API 認可は変更しない。

## 実装単位

1. build 出力の閉域検査後、`index.html`、実 JS/CSS、domain artifact 等の配布静的ファイルだけを列挙し、各 SHA-256 を持つ版固定 manifest と SW を生成する。ビルドの未知形式、外部 URL、欠損、manifest と SW の不一致を閉拒否する。生成物は dist のみで source を手編集しない。
2. production で SW を登録する。SW は同 origin の列挙資産と既 router route の navigation app shell だけを返す。全資産の byte 検証に成功した版だけを cache 完成とし、失敗時は既版を保全。fetch 時も改竄を拒否する。API や不明 path は SW cache を使わない。waiting worker を強制起動しない。
3. Vitest/型/ESLint/build と可能なら Chromium offline cold 起動を確認する。静的画面起動の証拠とローカル記録資格の証拠を分ける。変更後は別担当の独立レビューへ渡す。

## 対象と境界

対象は `frontend/vite.config.ts`、`frontend/offline-build.ts`、`frontend/public/sw.js`、`frontend/src/lib/registerServiceWorker.ts`、`frontend/src/main.ts`、frontend の専用テスト、当 docs。既 auth/router/API、DB、domain 計算、共有 ledger、正本は変更しない。静的起動が成功しても FR-012 の local 記録資格・全 Must 操作・実機の成立は主張しない。

## 非作者確認・候補受領（2026-11-06、PO委任Codex/root判断）

対象patch a2482a15…bb7、baseb3899d59の7pathをrootが非作者として確認。cache fr012-app-shell-root-review-20261106/REPORT.md、Vitest14と別VM6対向が成功しP0/P1なし。候補範囲で採用しLCへ接合する。作者Chromium coldは静的help200/API非cache/保護record→loginの限定証拠。人間確認/P-6 blind/記録資格の成立ではない。静的install前断、local権限と全操作、正式派生/全CI/実機は残る。
