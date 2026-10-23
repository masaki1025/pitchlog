# TSK-506 同期 HTTP 入口: 調査記録（2026-10-16）

## 起点と重複

- 基線は `origin/develop` の `966d7a38aa8dab2113c1d8ec6d30e5d32088ede5`（#132/TSK-391 統合後）。専用 branch は `feature/tsk506-sync-http-entry`、worktree は `/home/ymdms/projects/pitchlog-worktrees/feature-tsk506-sync-http-entry`。
- [正式カード TSK-506](https://app.notion.com/p/3f493b75e68781629ed8eec9c8338dcd) は High、担当欄は山田正輝。E-1/E-2 と EP-1〜EP-11 を DoD とする。カードの担当欄は人間の割当であり、稼働中の実装セッションの証拠とはしない。
- 2026-10-16 の `git worktree list`、local/remote branch、`gh pr list --state all --limit 300`、この会話の稼働中セッション一覧に TSK-506 の先行実装は無い。カードへの後発の担当変更・外部セッションは見えないため、実装開始直前に再照合する。U-R1、共有実行器 A、C1 の作業領域は編集しない。

## 既存の実体と不足

| 境界 | 現在確認できる実体 | 接続時に確認する点 |
| --- | --- | --- |
| wire | [TSK-331 設計](../sync-wire-schema/design.md) 3〜6 節。E-1=`POST /games/{game_id}/sync/events`、E-2=`POST /games/{game_id}/sync/changes`。E-1 は P1/P2/P4/P5、E-2 は P3。S-1 だけ試合参照より前に 422 | E-1 の経路はクライアントが選ばない（同設計 3-1）。U-S1 の `SyncRequest.path` に何を渡すかを U-S1 担当から受理する |
| 適用核 | `backend/src/pitchlog/sync/apply.py:292` の `apply_sync_request(context, request, rights, projection, validator, *, registrations, targets)`。`SyncRequest.from_payload` は `sync/model.py:231`。内部で 1 イベント 1 transaction、試合行→記録権世代行の順に lock。S-1 外形と ACK/P3 結果型がある | 正本 8-1 の種別表では毎球入力は P2。`SyncRequest` の公開 path は要求全体に P1/P2/P3/P4 の単一値で P5 は内部拒否経路。E-1 の P1/P2 混在バッチを単一 ACK・D1 順で扱う公開境界が現状の型からは導けない。U-S1 側受理まで HTTP で勝手に分割しない |
| 認証・テナント | `api/tenant_access.py:12` の `require_tenant_access` が正規の `TenantContext` を発行。適用核は存在しない試合/他テナント試合を B6、P3 は B12 にする。`api/errors.py` に共通封筒 | 認証失効 B5/B11 は HTTP 入口側。B6/B12 と自テナント不存在の 404 のヘッダー・本文まで一致させ、S-1 は試合存在から独立させる |
| 記録権・RG1 | `sync/ports.py:65` の `RecordingRightsPort` は ③-a、⑧、復旧世代、V12 を要求。`PORT_IMPLEMENTATIONS` は現基線で空。U-R1(TSK-392) が物理方式と本物のポートを所有 | V12/D4/復旧世代の発行・保存・失効、初回試合開始時の記録権、RG1 拒否、同一ロック順、登録済みポートの導入を受理。未登録ポートを仮で通さない |
| 状態計算・検証 | `sync/ports.py:89,97` の `ProjectionPort` / `ContentValidationPort`。U-S1 設計 2 節は前者を U-X1、後者を U-X1/U-G2 所有とする。現基線に製品実装・登録はない | 1球 `play_input` の T4 投影と内容検証、DB トリガによる原子性保護（U-S1 設計 R-12）の所有者と受理先を決める。現時点で実保存の DoD は未達 |
| 永続化・再送 | `db/sync_protocol/models.py:117` の `operation_events` は `(tenant_id,d5)` 一意、台帳 FK と `(tenant_id,game_id,generation,d1)` の slot FK を持つ。U-S1 は D5 再掲と prefix を持つ | HTTP 入口は D5 を生成・書換えず、ACK 不明時に同じ D5/内容を再送。重複・異内容・D1 欠落・ACK 消失を実 DB で確認 |
| フロント通信 | `frontend/src/api/client.ts` の `apiRequest` と `ApiStaleAuthError` を利用。`frontend/src/lib/sync/` に transport-neutral なキュー/ACK/P3 DTO。TSK-331 設計 5-3 の X-1〜X-6 が未接続 | codec/通信層は TSK-506、画面は U-F8。`ApiStaleAuthError`・401 でキューと D5 を保持。V12 をログ出力しない |
| 記録画面・再読込 | `docs/features/uf8-record-screen/plan.md` は入力下書きと非保存表示だけ。`backend/src/pitchlog/api/app.py` に games/sync/read-back router は無い | 画面からの確定イベント生成・記録権受領・再読込表示は U-F8 の後続。TSK-506 の HTTP 直叩きで実 DB の原本を再照合できるが、利用者画面の再読込を満たす読取 API は別途所有確認が必要 |

## 入口固有の必須条件

- [TSK-331 設計 4-1・4-4・6-2](../sync-wire-schema/design.md): ACK/P3 の HTTP 写像、E-1/E-2 の越境直叩き、B6/B12 の同一 404、S-1 の同一 422、wire 往復、X-1〜X-6、B5/B11 のキュー保持、V12 非ログ化、DTO 置場・TB002・コア paths、N-1/N-2/N-4/N-15/N-18、実スキーマ越境ゲートを**同一の入口 PR**に含める。
- `backend/tests/test_api_conventions.py` は `api/` 内の同期語彙を拒否する。検査を一律緩和せず、薄い router と `api/` 外の DTO/codec を候補にして同試験の維持を検証する。`contracts/tenant_boundary/base-allowlist.json` の TB002 と `.claude/core-areas.json` の変更要否は、実差分が決まった時点で担当/7.7/コアゲートへ回す。
- [data-model 12-4](../../design/data-model.md) は新しい HTTP 入口ごとに route_id・外部からの API 直叩き・RLS 適用済みの実スキーマの越境ゲートと PR 記録を要する。`route_id` の付与と共有認可資産は TSK-424 側と編集順序を合わせる。
- 同節の「実スキーマ」は試験ごとに捨てるクラスタを除外する。機能・故障系の隔離試験 DB と、ゲート判定用の**実行間で存続する検証専用クラスタ**を分け、後者に製品 migration head と RLS/ロール DDL を製品経路で適用する。既存 DB や共有クラスタへは適用しない。
- N-1（件数/本文サイズ）、N-2（再送間隔/Retry-After）、N-4（流量制限）は NFR-002 の測定後に判断する。根拠の無い定数を計画で置かない。
