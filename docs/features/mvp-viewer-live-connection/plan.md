---
feature: mvp-viewer-live-connection
status: active
承認: 済（PO委任Codex主担当/root、2026-11-06。既MVP内の閲覧技術接合）
重さ分類: コア領域
branch: feature/mvp-viewer-live-connection
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-viewer-live-connection
created: 2026-11-06
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 別端末の保存済み試合を自動更新する

固定基線 `043591c37ddf833553300f36d04940bb40b452e1`。PO委任rootが既MVP内技術接合の進行を承認。本人逐行確認・正式提供・製品受理を代記しない。

## 範囲と既決境界

同一チームの別ブラウザcontextが、記録権・端末登録・書込資格なしに認証済みC2を通して、試合の確定済みスコア、回/表裏/outs/走者、出場選手、有限pageの1球履歴を表示する。最終保存時刻と閲覧確認時刻を分け、通信断・認証/tenant/ゲーム変更・再取得不明では旧値を最新として表示しない。記録端末の未送信はサーバー確定値へ含めない。NFR-006の10秒反映を実HTTPS/owned PGの2 contextで測る。未達数値を残す。

`/games/{id}/started` は既計画 `mvp-started-read-http/plan.md:447-448` がgames/generationロック中のNode起動を理由に定期pollへ流用禁止としている。既登録の非ロック GameRead/RecordingGenerationRead の2 tokenによる小さな版probeだけを定期取得し、版変化時はRR READ ONLYの専用viewer本体GETを取得する。本体も既`started`の行ロックへ入らず、同snapshotの保存済みCP・原本照合・有限履歴を既閉readerから再利用する。0球のみ、同snapshotの開始済みgame/lineup/規則・D3=0・event不在を照合し、既初期配置演算を呼ぶ。probeは表示真実・記録権・保存成功の証拠にしない。旧値が未更新でも毎回probeのC2/可視性を再確認する。版変化/失敗時は古い表示を未更新へ降ろす。本体GETの有限pageは上限25、cursorは既版拘束を使い、v3は最新25球から旧ページへ遡る。全件走査しない。

閲覧端末が記録者端末の通信断・未送信件数をサーバーから直接識別する機構は現MVPに存在しない。画面では「サーバー確定分のみ。記録端末の未送信は含まれない」と常時明示し、viewer自身の通信不能は未更新として示す。動的な記録端末断中検知を確定した成功としては主張しない。この未決意味はrootへ具体例とともに提示する。

## 編集所有と実装ステップ

| # | 単位 | 対象pathと到達条件 |
|---|---|---|
| 1 | 非ロック版probe | `backend/src/pitchlog/repositories/viewer_probe.py`、`backend/src/pitchlog/api/routers/viewer.py` と専用pytest。既token/C2/tenant境界だけを使い、404/503/不正世代を閉拒否。記録権・端末条件を導入しない。共有`api/app.py`のrouter追加はroot向け別patch。 |
| 2 | 非ロック本体と閲覧画面/有限履歴 | `backend/src/pitchlog/repositories/{transaction,started_snapshot,ordinary_prefix_read,viewer_read}.py`、`backend/src/pitchlog/api/routers/viewer.py`、`frontend/src/api/viewerGame.ts`、`frontend/src/screens/GameScreenViewerLive.vue`、専用pytest/Vitest。RR READ ONLYと閉tokenで既保存CP/履歴を同snapshotに束縛し、3秒単一poll、版変更時だけ非ロック本体GET、25件pageと既cursor、対象ID限定GET、認証世代/tenant/ゲーム切替で中断・旧表示破棄。共有`frontend/src/router.ts`・入口、`api/app.py`・`api/tenant_access.py`、Cookie同提示token宣言はroot向け別patch。 |
| 3 | 実2context検査と固定引渡し | rootの所有PG/browser lockが空いた後に共通flockで実HTTPS/ownedPG。新規UI試合→開始→別context閲覧→保存→10秒計測→reload→閲覧側通信断未更新→越境拒否。候補全SHA/パッチ/正式共有path追補を封印し、非作者レビューへ渡す。 |

実DB対向で、既v3履歴page関数と非play active page関数の `FOR SHARE` は PostgreSQL の `READ ONLY` と両立しないことを確認した。writer既関数の行ロック契約を残し、同一SQL生成元からアンカ・行数・原本照合を維持して行ロック句だけを除く閲覧専用の有限2関数を追加する。専用tokenと閉登録を使い、RR READ ONLY以外からは呼ばない。新関数の正式宣言・EXECUTE ACL・catalog照合・manifest/bodyはroot向け別patchとし、独立確認まで製品受理としない。

正式router/registry/DDL/認可/manifest/pin、他WT、共有DBはこのWTのwriter対象外。既routeのロックreadを閲覧から呼ぶ実装は禁止。FR-020全イニング/H/E/K/BやFR-021〜023成績の完成へ拡張して主張しない。全件/正式CI/人間確認/本番性能はroot統合後の別判定。
