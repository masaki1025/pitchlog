---
feature: mvp-started-read-snapshot-20261107
status: active
承認: 済（PO委任root、2026-11-07、固定af8c6ff9限定計画レビュー）
重さ分類: コア領域
branch: feature/mvp-started-read-snapshot-20261107
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-started-read-snapshot-20261107
固定基線: 7de86358c94dc2c35ea90216a3602f5f0a2607c9
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 記録画面 GET を一貫した readonly snapshot へ分離する

## 根拠と維持条件

実 runner run6 で `/started` GET scope PID1711 は 5.86 秒生存し、NP publisher actor1748 の `public.games` FK 側 `transactionid` 待機の blocker=[1711] と一致した。新 writer binding は2秒で `QueryCanceled`。現 GET は `tenant_transaction_scope` 内 `GameLockToken` / `RecordingGenerationLockToken` を取得し、通常v3・非play・LC の表示計算中も保持する。今回の修復は GET の読取だけを RR/READ ONLY に移す。writer 側 lock、nonce/lease、同TX、RG1、資格、拒否順、保存計算、実P3 current selectorは変更しない。timeout 延長や取得済み資格の cache はしない。別 viewer P1-1 作者 packet は未受理なので、その版 SQL や P3 body 503 分岐を記録画面へ移植しない。

## 方法

`tenant_transaction_scope` と区別する専用 `started_snapshot_read_scope` を、実 TenantContext と同じ接続/tenant証跡のもと最初の tenant SQL より前に `REPEATABLE READ` + `READ ONLY` で開く。原 viewer scope の有限 token whitelist・context/handle失効検査を再利用するが、現在の製品源で使う token だけを閉列挙する。`GameLockToken`、`RecordingGenerationLockToken`、writer/Port/write-admission token はこの scope で常に拒否する。通常 writer 用 scope/token は一切変更しない。read専用関数内に `FOR SHARE/UPDATE` が残る場合は元SQLの固定本文・保存証拠・page境界を共有し、行lock句だけを除いた別 readonly function/token として閉登録する。共有正式関数・catalog/ACL/manifest は cache patch へ分離し root が直列採用する。

`read_started_game` / 0球 `read_initial_started_snapshot`、保存初球の `try_read_recorded_snapshot`、`read_ordinary_prefix`（v1/v2/v3と現P3 current）、`read_undo_prefix` と `lifecycle_display_scope` に限定 readonly mode を通し、同一 RR transaction で実 `GameReadToken`、現 normal generation、CP/水位/履歴page/LC を検証する。可視性・tenant・終了pointer・元CP/cursor/25または既100上限・P3 capsule/current/source/T5 の現行完全検証を保持する。mode の入口は実専用scope検証を必須とし、任意boolで writer reader のlockを省けない。0球/保存初球200/不可視404、記録あり409、原本不整合503の既外形を維持する。複数 GET と writer の snapshot 差は新規GETの結果でだけ解消し、開いた旧snapshotで新保存成功を表示しない。

## 所有・ステップ

| # | 編集範囲 | 到達条件 |
|---|---|---|
| 1 | `backend/src/pitchlog/repositories/transaction.py` の専用RR scope/閉token、`started_read.py`、`started_snapshot.py`、保存初球の `recorded_snapshot.py`、`ordinary_prefix_read.py`、`nonplay_prefix_read.py`、必要最小の `game_lifecycle.py`、専用pytest、cache関数/ACL patch | GETで writer行lock token 0、同handle/RR/tenant/0球・保存初球・通常v3/P3・非play・LC の現有効原本を閉検証。writer scopeのlock試験/拒否を維持。 |
| 2 | `backend/src/pitchlog/api/routers/started_games.py` と専用pytest/plan progress | GET入口だけ専用scopeへ。404/409/503、cursor/tenant/C2、未完了・不正pointer拒否を保持。既API DTO全文/数学は不変更。 |
| 3 | root直列接合・実対向 | source/実関数/正式catalog をrootへpacketで渡した後、共通lock下の owned PG/HTTP で同時GET→NP publish、CP/P3/LC/0球/旧cursor/tenant/故障全取消を確認。rootの正式 asset/7.7 受理と独立レビューは別。 |

このWTでは共有正式asset・router以外のroot共有path・台帳を編集しない。既P3 paged reader の全履歴を一括 RAM 化せず、既有限page検証をそのまま通す。実 PID 原因を否定する後発証拠が出た場合は本計画の採用を取り下げる。

## 計画レビュー記録

2026-11-07、root が固定 `af8c6ff9` / plan SHA `c522c55b660dfb820a2d5a8b683c2919157a1b23b0cda5b2f4941b646a59681e` を全文確認し、P0/P1なしでPO委任採用。真正RR handle限定のread mode、writer lock不変更、現P3 selector/NP/LC/0球保持、固定SQLの行lock句以外全値比較と最小cache接合patchを条件としてstep1→2を進める。DB/browserはroot調整まで未実施。

同日、root は初球 default GET の既200維持に必要な `recorded_snapshot.py` の最小 read-only 分岐を計画追補として承認。旧writer lifetime/lockと保存初球の全値照合・唯一計算を維持し、実RR handleに限って有限Recorded read tokenを許可する。

## 実装記録

2026-11-07 ステップ1: 実RR/READ ONLY scopeの発行印を同handle・top-level TX identity・tenant証跡・失効まで束縛。0球/保存初球/通常・非play・LCのreaderはこの印だけで行lock tokenを省き、旧writer経路を保持。行lockを除く別identity3関数と固定型/registryの共有差分はリポ外候補 `~/.cache/pitchlog/started-read-snapshot-author-20261107/` に分離。元関数の本文・権限は変更しない。実PG/正式登録/非作者確認は未了。

同日 ステップ2: `/games/{game_id}/started` GETだけを専用scopeへ接続。defaultの0球/保存初球200と既C2/DTO対向、非playの別read token、scope内writer lock拒否を純試験で確認。共有関数と正式catalogが未配備なので、公開実PG成功の主張は行わない。
