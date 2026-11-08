---
feature: mvp-viewer-current-connection-20261107
status: active
承認: 済（PO委任root、2026-11-07 JST、固定80f652d9の限定計画レビュー）
重さ分類: コア領域
branch: feature/mvp-viewer-current-connection-20261107
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-viewer-current-connection-20261107
固定基線: 18b31a839558bd6090e77e1a8c53cafcb39509b2
計画レビュー周回: 1
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

2026-11-07 JST、root が HEAD `80f652d98dbe886b89c948a5920b2475654f4a95` の plan SHA `36d1304b735f82fc73d0ce3aabb23d9a47a5104f53be08e0abaa32c0acaadb76` を全文確認し、P0/P1なしとしてPO委任で限定採用。真正RR scopeの有限登録とC2 gateは共有patchへ残す。終了版の未対応を成功で隠さず、P3のCP/capsule/slotの既結合、版・本文・cursorの同snapshot照合を維持する。実PGはrootとの時刻調整後に限定する。

現行 `read_started_play_prefix_history_page` は昇順であり、元viewer計画の最新25件から旧頁へ遡る契約と同値ではない。2026-11-07 JST、root はこの具体差分を確認し、正常v3に必要な降順keyset/索引点範囲の有限reader 1本だけを共有patchへ追加する技術追補をPO委任で承認。NPは現行降順readerを再利用する。P3 paged currentも同じ最新頁・cursorを、既CP/capsule/slot/全頁seal検証を残したまま有界選択へ接ぐ。所有に新規 `backend/src/pitchlog/authz/{viewer_page_sql,viewer_product}.py` と専用pytestを加え、現行単一readerからの固定byte派生・2関数の宣言を供給する。共有 `ordinary_prefix_read.py`、`started_snapshot_read_operations.py` と関数登録はcache patchでrootへ渡し、このWTで直接編集しない。旧2関数の無条件追加、全履歴RAM取得、履歴欠落の成功化はしない。

## rootのステップ3直列接合（2026-11-07 JST）

元計画80f652d9/SHA36d1304b735f82fc73d0ce3aabb23d9a47a5104f53be08e0abaa32c0acaadb76のPO委任採用に基づき、root専用 `feature/mvp-viewer-product-integration-20261107`（730536eb起点）へ作者4b3339bcを接合する。共有13path patch SHA53991f6fcfc8ef279b2c725be8c80f6662ae42aa4af90caaca9ab3644f3d56aaを親18bの実byteと照合して適用し、生成器の2関数宣言/全SQLを正式product DDL・body manifestへ生成、Cookie対象と実有限期待集合を追随する。旧recover応答型除外・guard緩和は行わない。必要なrepository/runtime/7.7の派生受理は正規helperを使用し、実catalog/CI前に成立とはしない。編集をrootへ一本化し、作者と別WTで独立確認を継続する。

ここでの接合は候補環境であり通常mergeや提供完成ではない。実PG/実画面は共通owned lockで走者主経路と分離し、終了v3の未提供を503のまま完成扱いにしない。
