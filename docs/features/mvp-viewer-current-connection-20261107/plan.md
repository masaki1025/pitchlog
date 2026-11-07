---
feature: mvp-viewer-current-connection-20261107
status: planning
承認: 未（rootの限定計画レビュー待ち）
重さ分類: コア領域
branch: feature/mvp-viewer-current-connection-20261107
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-viewer-current-connection-20261107
固定基線: 18b31a839558bd6090e77e1a8c53cafcb39509b2
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 閲覧ライブを現在の保存版へ接続する

既採用の `mvp-viewer-live-connection`（40b36545）と実効版修復（f2488c71）を、現行の記録画面用 RR READ ONLY reader と P3 current selector に接続する。3秒の軽量probe、25件page、同一tenant/C2、10秒鮮度境界、0球の初期表示を維持する。閲覧に書込資格を与えず、現行の writer 側行lock・唯一計算・P3原本検証を変更しない。旧候補のP3本文503は完成として扱わず、真正current P3本文と不透明版を同じsnapshotで照合する。

## 編集所有と段階

| # | 単位 | 所有pathと完了条件 |
|---|---|---|
| 1 | 現行readerと版probe | 新規 `backend/src/pitchlog/repositories/{viewer_probe,viewer_read}.py`、`backend/src/pitchlog/authz/viewer_effective_sql.py`、専用 `backend/tests/test_viewer_{probe,read_sql}.py`。旧候補を現行RR token/readerへ再基線化し、点読取だけでCP/P3/LCの実効版を閉検証する。CP・世代・水位のbool/floatを拒否し、同水位P3と終了pointerの変化を検知する。P3本文は既 `read_verified_p3_paged_current` 等の現行selectorを再利用し、旧物理行へfallbackしない。 |
| 2 | 閲覧専用APIと画面 | 新規 `backend/src/pitchlog/api/routers/viewer.py`、専用router pytest、`frontend/src/api/viewerGame.{ts,spec.ts}`、`frontend/src/screens/GameScreenViewerLive{.vue,.spec.ts,Controller.ts,Controller.spec.ts}`、必要な専用E2E source。C2とtenantの既gateを使い、head版とbody/cursorを同RR snapshotで照合する。版変化・断・認証変更では古い表示を最新として残さず、同D1訂正後は新current本文を取得する。 |
| 3 | 共有接合packetと検証 | `docs/features/mvp-viewer-current-connection-20261107/plan.md` とcache packetだけ。共有 `first_ball_product.py`、`transaction.py`、`function_operations.py`、`operation_registry.py`、`api/app.py`、`api/tenant_access.py`、`frontend/src/router.ts`、正式catalog/ACL/manifest/台帳はroot専有とし、必要な最小差分を元byte・対象HEAD付きcache patchで渡す。元の閲覧用2 SQLが現行started readerと同値なら増設せず、必要な場合だけ新実効pointer 1 SQLをowner/ACL付きで提案する。 |

元40b/f248のWTは不変更とし、既レビューと実測の対象版を混同しない。純pytest/Vitest/Ruff/Ty/Vueを先行する。実PG/ブラウザは共通lockをrootと調整してから行い、正式受理・7.7・全MVP成功は別判定とする。新しい野球意味、固定資格、全件読込、成功stubを導入しない。

## 計画レビュー

rootによる固定版レビューの対象HEAD・SHA・判断をここへ追記してから実装する。
