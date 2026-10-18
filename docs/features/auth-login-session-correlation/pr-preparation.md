# C1相関：レビュー候補・本人逐行確認の準備

## 検査の帰属

単独製品108c7562、fixture追随912585d1でfrontend69ファイル1,278成功（69.99秒）。型・ESLint・Prettier成功。buildは同一製品の108c7562で成功、fixtureは閉域検査で製品に含まれない。backend製品/試験は7e18a91a以降不変で全2,581成功4skip。root scripts/tests/contractsは不変で全29,670成功2skipを保持。

専用結合は製品cdaf49fd、fixture追随d1f467f5で71ファイル1,382成功（73.25秒）。結合の実画面/API/DB正常・故障結果は作業ログへ帰属させる。単独HEADのCIへ転用しない。

## レビュー採否

review-round2.mdが正。両経路2/2使用済み。P0なし、全P1を採用し局所修正/試験を行った。自チーム受入は別契約ゲートで未了。最終反映は未再レビューで、人間の確認を代行しない。全DoD・TSK-528/520完了とは記録しない。保留P2案はPO受理済みとしない。

## 本人確認（未実施）

- [ ] コア領域/検査経路の変更: 人間による逐行確認を実施した
- 実施記録: 対象= 範囲= 方法=

対象は以下の全差分。特に拒否通知/ack/lock/旧Cookie、quota fallback、DTO照合、旧signIn廃止、caller exact-setの1組追加、後発の結果不明/password通知、単体fixtureの非製品境界を確認する。方法を推定しない。

- backend/src/pitchlog/api/routers/auth.py
- backend/src/pitchlog/api/schemas/auth.py
- backend/tests/db/test_api_login_entry.py
- backend/tests/test_api_login.py
- backend/tests/test_authz_app_layer_surface.py
- backend/tests/test_roster_boundary.py
- docs/features/auth-login-session-correlation/lock-contention-decision.md
- docs/features/auth-login-session-correlation/metadata-cookie-decision.md
- docs/features/auth-login-session-correlation/plan.md
- docs/features/auth-login-session-correlation/pr-dependency-map.md
- docs/features/auth-login-session-correlation/pr-preparation.md
- docs/features/auth-login-session-correlation/review-round2.md
- docs/features/auth-login-session-correlation/self-team-read-gap.md
- docs/features/auth-login-session-correlation/worklog.md
- frontend/src/api/auth.spec.ts
- frontend/src/api/auth.test-support.ts
- frontend/src/api/auth.ts
- frontend/src/api/authIntent.spec.ts
- frontend/src/api/authIntent.ts
- frontend/src/api/client.boundary.spec.ts
- frontend/src/api/client.spec.ts
- frontend/src/api/client.ts
- frontend/src/api/roster.spec.ts
- frontend/src/components/settings/TeamMembersContent.spec.ts
- frontend/src/screens/TeamScreen.spec.ts
- frontend/src/stores/authStore.boundary.spec.ts
- frontend/src/stores/authStore.spec.ts
- frontend/src/stores/authStore.ts
