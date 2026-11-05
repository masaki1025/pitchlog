# 実装計画書: 取消の接続spike

- 起点: 正式 develop `112f771e549d6a92d724f62d9b0b45dcc89973c1`
- 作業枝 / worktree: `feature/mvp-undo-connection-spike` / `~/projects/pitchlog-worktrees/feature-mvp-undo-connection-spike`
- 状態: spike（製品統合前の候補。PR・マージは主担当が行う）
- 関連: `docs/features/ux1-undo-ts/plan.md`・`findings.md`、`docs/features/ux1-roundtrip/plan.md`・`findings.md`

## 1. 目的

実画面で「新規作成→開始→通常の1球保存→取消→サーバー再取得→reload」を通し、
実認証・実記録権・正式計算・同期核・実DBの接続を実測する。純粋計算や事前投入
データの成功だけでは完了としない。契約・正本・共有台帳は変更しない。

## 2. 再利用する成果

| 起点 | 再利用するもの | 本枝での扱い |
| --- | --- | --- |
| `feature/ux1-undo-ts@b2ed1905` | `undo.ts` の取消計算、契約 `undoRows` 10 件の照合、artifact 経由の照合 | 現行 `stateTypes.ts` と v3 `battingOrderBySide` へ追随して移植。契約期待値は変更しない |
| `feature/ux1-roundtrip@41d7175d` | 前進計算が返す `historyEntry`・差分をそのまま取消へ渡す往復の考え方 | 現行製品の `newHistoryEntry` をそのまま使い、試験側で差分を組み立てない |
| 現行製品 | 通常投球 `deriveOrdinaryPitchWithContinuation`、第一球 `deriveFirstPitchWithContinuation`、同期核 P1/P2、記録権 Port、実 DB | 接続先として使用。別のドメイン計算を追加しない |

## 3. スコープ

### やること

- 正式 artifact に `applyUndo` を追加し、取消の純粋計算・JSON 境界・契約 10 件の照合を現行型で通す。
- 取消を同期核の P1 イベントとして、実認証・実端末提示・実記録権・同一トランザクションで保存する。
- 保存済みイベントを正式 artifact で畳み込み、取消後の状態・履歴・対象を返す再取得入口を作る。
- 同じ実画面に通常投球入力と取消 panel を接続し、E2E spec を用意する。
- 再送・拒否・越境・記録権不成立・途中故障・監査行保持を実 DB で検証する。

### やらないこと

- `contracts/`・`docs/requirements`・`docs/design`・`docs/adr` の変更。
- 製品 `create_app()` の既定ルートへの取消接続（spike は `PITCHLOG_UNDO_SPIKE=1` の試験合成だけ）。
- 製品の `/started` prefix 読み取り経路への取消投影の接続（§5-1 の未決事項）。
- 原ブランチ `spike/ux1-mvp`・`feature/ux1-undo-ts`・`feature/ux1-roundtrip` の変更。
- 正式統合・PR 作成・マージ。

## 4. 実装

### 4-1. フロントエンド（正式 artifact）

- `frontend/src/domain/undo.ts`: 履歴差分の逆適用。`delta`/`set` のローカル規約は
  `feature/ux1-undo-ts` の findings §3-1 を維持する。v3 の両打順 cursor は
  状態だけ戻し、契約の比較面には足さない。
- `frontend/src/domain/publicApi.ts`: `applyUndo` の JSON 境界を追加。
  整数は十進文字列のみ。空スタックは `nothing-to-undo`。
- `frontend/public/domain/pitchlog-domain.js` / `.json`: `pnpm build:domain` の再生成物。

### 4-2. バックエンド（spike 入口）

- `backend/src/pitchlog/sync/spike_undo_http.py`: 実認証・実端末提示・実記録権を使う
  `POST /spike/games/{game_id}/undo` と `GET /spike/games/{game_id}/state`。
- `backend/src/pitchlog/sync/spike_undo_ports.py`: 取消の内容検証 Port / 投影 Port。
  投影は監査行を消さず、挿入済み取消行と対象行の存在だけを確認する。
- `backend/src/pitchlog/sync/spike_undo_validation.py`: 同一取引で対象行・水位を読み、
  正式 artifact の `applyUndo` と保存予定結果を照合する。
- `backend/src/pitchlog/sync/spike_undo_artifact.py`: artifact 呼出の合成部品。
- 同期核への最小追加: `_apply_e1_f1` の `spike_p1` 引数、`_replay_e1_without_binding`
  の `path` 引数、Port 登録表への spike Port 追加、content phase の読取許可
  （水位・操作イベント）、`create_app` の `PITCHLOG_UNDO_SPIKE=1` 時だけの install。

### 4-3. 画面

- `frontend/src/screens/GameScreenUndoSpike.vue`: サーバー由来状態、取消対象、
  取消・再取得 button。`GameStartPersistence` から実端末提示と V12 を取得する。
- `frontend/src/screens/GameScreenRecordedRestore.vue`: 同じ記録画面に
  「通常投球の状態を取得」と取消 panel を埋め込む（spike 専用）。
- `frontend/src/router.ts`: `/games/:gameId/undo-spike` を追加（直接確認用）。
- `frontend/src/api/undoSpike.ts`: 再取得・取消 POST の閉じた DTO。

## 5. 未決事項（主担当の判断対象）

1. **製品 read 経路の取消投影**: 現行 `/started?projection=...` は history page の
   D1 連続性と `last_source` を play 行に前提しており、cancel 後の tail を表現できない。
   spike は「保存済みイベントを都度畳み込む専用 GET」で観測した。製品接続には
   history version / retired / checkpoint の設計判断が要る。
2. **undo の V7 payload schema**: 契約に取消 payload の形がない。spike は
   `undo-connection-spike-v1`（target + result）を暫定使用した。
3. **取消対象の範囲**: spike は「水位末尾が確定プレイ」の 1 件取消だけを受理する。
   FR-006 の「直前の取消可能な操作」を非 play イベント越し・連続取消まで広げるには
   履歴スタック全体の解決規則が要る。
4. **artifact SHA と凍結 vector**: `applyUndo` 追加で artifact SHA が
   `cda0b594…` から `74409235…` へ変わり、旧 SHA を固定した frontend の
   凍結 vector 照合が 59 件失敗する。契約 vector を更新するか、取消を別 artifact に
   分離するかの判断が要る（本枝では `contracts/` を変更していない）。
5. 既知の取消契約の仕様不足・期待値矛盾は `docs/features/ux1-undo-ts/findings.md`
   §3・§4 をそのまま保持する（delta/set 分類、現在状態、liveness-only の
   履歴文脈、D+1 スタックの不整合など）。
