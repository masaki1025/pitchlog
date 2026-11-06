# 終了・追記再開 FE6 進捗（担当: lifecycle UI）

## 受諾と固定点：2026-11-06

- **受諾範囲**: lifecycle-ui-delegation-20261106.md の FE6。編集は新規6pathと本plan/progressだけ。
- **起点**: `e0be2483e29eecba478e5f4fca56d4cf4164711b`（branch `feature/mvp-nonplay-product-connection`、cleanを確認）。後発commitは吸収していない。
- **worktree/branch**: `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-lifecycle-ui` / `feature/mvp-lifecycle-ui`（baseから新規作成）
- **接合仕様**: `~/.cache/pitchlog/mvp-lifecycle-product-author-20261106/MINIMUM-INTERFACE.md`、packet `2f464208ef8ed53e78048ea5370e55204b60584b7397b51272882b1bed91fee8`（SHA256再照合済み）
- **backend候補**: 未正式受理・PG未実。candidate artifact `c461baff82d5b2f2dca44fdef5b07bf0964f7db315981023e724a132f9312aa1` は採用していない。
- **台帳**: 主担当台帳・共有lib・router・正式contracts/DDL・他WTは変更していない。

## 実装HEAD

- ステップ1: `56f63f90`（transport＋plan）
- ステップ2: `df19e51d`（controller＋spec）
- ステップ3: `8e477dc5`（panel＋実画面E2E契約）
- ステップ4: 本progressを含むdocs commit（branch tip。`git log -1` で固定）
- コードHEAD（progressを除く）: `8e477dc5`

## 到達した内容

| 単位 | 実装 |
| --- | --- |
| 読取 | `GET /games/{id}/started?projection=lifecycle-prefix-v1&limit=25[&cursor]`。`read_kind=nonplay-prefix`/`profile`/`status`/`lifecycle{formatVersion,status,lastVersion,active,activeStatsVersionId}` を閉検査。NP prefixの全構造は既存 `isNativeUndoGame` をstatus差替えで再利用し、finishedをin_progressと混同しない。旧DTO/旧projectionは `unsupported` |
| 書込 | `POST /games/{id}/sync/events` の1要求1イベント。既 `buildSyncEventRequestBody` のD1/D4/D5/V12/正本検査を通し、終了=ordinal 5 → `game_end_declaration`、再開=新種別 → `game_reopen` だけを専用写像。V8/V9/V10/V11は送らない |
| 再開の閉拒否 | `EVENT_KIND_RULES` に「試合再開」が無い間は `reopen-kind-unavailable`。id7流用・型cast・固定成功応答をしていない |
| 耐久 | queue受理**前**に V12込み全本文・D5・D1・D2・予約event/receipt・attempt を既 `NativeEnvelopePersistence`（V12込み本文をstrict保持する既存store）へ確定。専用の新storeは送信試行マーカーだけ（`pitchlog-game-lifecycle-dispatch`、資格/本文を保持しない） |
| 排他 | 既 `singleWriterLockName` / `runAsSingleWriter` / 待たないlock manager。鍵なしは追記しない |
| 送信・ACK | 保存本文をそのまま送信。既 `readOrdinaryPitchAck` で同game/D4/D1/D5の受理/重複だけを採用し、既 `applyAckToSlot` で同期済みへ |
| 再送 | 同本文/同D5/同attemptのみ。grantのV12が変わったら書き換えず `grant-changed`。TTL・新D5への置換なし。prepare/append境界停止は `readPreparedSlot` から同一event/本文で再開 |
| 順序 | 先行の未終結slotがあるときは追記を受理しても送信しない（`queued-awaiting-predecessor`）。FR-010の断中宣言を保ち、先行slotを飛ばさない |
| 再取得 | ACK後に必ず実GET。`acked`＋`refresh=pending`（表示はstale）を保存済みと混同しない。reloadは実GETから復元 |
| 画面 | status/確定版/終了確定版/最終更新/未送信/結果不明/他の未終結/保存確認/再取得状態/失敗理由/次の記録位置。Vue自動escapeのみ。終了・再開・再送・再読込・記録を続ける・戻る |
| handoff | `resumeHandoff`（gameId/tenantId/next_position/checkpointRef/recovery/lastSavedAt）と `resume-recording` emit。追加球の計算・保存は実装していない |

## 実行した検査（このworktree・このHEAD）

| 検査 | 結果 |
| --- | --- |
| `pnpm exec vue-tsc --noEmit` | 成功（0診断） |
| `pnpm exec eslint <6path>` | 成功（0） |
| `pnpm exec prettier --write <6path>` | 適用済み（`--check` は未実行。差分はcommit済み） |
| `pnpm test`（全件） | **154 files / 3483 tests passed**（160.96秒〜173.70秒。新規2 file/28 testsを含む） |
| 対象spec | `src/api/gameLifecycle.spec.ts` + `src/screens/gameLifecycleController.spec.ts` = **28 passed** |

`scripts/feature_status.py` は、base が未統合の feature 枝（`feature/mvp-nonplay-product-connection`）のため、base 側の `(ステップ k/3)` を本planの総数4と比較して「不整合」と表示する。本枝の3コミットは単独解析で `[1]/[2]/[3]` の正当な完全トークンである（base 由来の表示であり、本枝の記法不正ではない）。

検査の境界: 上記はjsdom/fake-indexeddbとmock transportの成功であり、**実認可・実PG・実HTTP・実画面の成功ではない**。

## 全path SHA256

```
c24778e7b2822895cca0fc0958195852c5fad05b47634ed47138511d2b45786f  frontend/src/api/gameLifecycle.ts
7515baea9bab85040e7e106e3c4b998e6db27f4f50963c1d081063cd7f54f607  frontend/src/api/gameLifecycle.spec.ts
10c28269880685fad6cd67c2418444c2b71bfecb1a777138881e1bd735f9e0c4  frontend/src/screens/gameLifecycleController.ts
2eb0859e21cb57743d532b0adc5d2317aed3c1c76d8f3a0a859a035c34c062db  frontend/src/screens/gameLifecycleController.spec.ts
41d641e90493432a1256540c794bec298b96e0051a8ab9fd6c6f2b626e4b5150  frontend/src/screens/GameScreenLifecyclePanel.vue
a92d5c6328ac52badfc50de490e5eb8e1cccc3a626cc6accd017e33f39ed4711  frontend/src/screens/GameScreenLifecycle.e2e.ts
1a25a95be646e99519bfc3461d18b3022634c8a89868bdd4cf7e31c4b682852a  docs/features/mvp-lifecycle-ui/plan.md
```

## 非作者確認

- **未実施**。本担当が作者であり、独立確認ではない。rootが別担当（例: undo UI/backend非作者）へ依頼するまで、採用・正式受理・完了扱いにしない。
- 確認してほしい点: (1) 保存ACKとGET未了の区別、(2) 同本文/同attempt再送で新D5を作らないこと、(3) 先行slot飛ばしの拒否、(4) 再開種別が未裁定の間の閉拒否、(5) パネルの資格原値非表示。

## 必要な接合差分（rootが直列反映）

### 1. `frontend/src/lib/sync/eventKinds.ts`（正式裁定が前提。候補）

`EVENT_KIND_RULES` の id `12` の後ろへ追加する。

```ts
  {
    id: '13',
    name: '試合再開',
    participation: EVENT_PARTICIPATION.LOGICAL_POSITION,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
```

- 名前は `GAME_LIFECYCLE_EVENT_KIND_NAME.reopen`（`'試合再開'`）と一致させる。
- id `13` はクライアント内部のordinal。backend V5は `game_reopen` literalであり、ordinalを送らない。
- 参加区分/C12はroot追補の裁定に従う。`LOGICAL_POSITION` は「D2を消費しV6必須・V8..V11禁止」を既条件写像で成立させる候補であり、確定ではない。

### 2. `frontend/src/lib/sync/eventFieldRules.ts`

**変更不要（候補種別がLOGICAL_POSITION・非取消・非墓標/改訂の場合）**。既存の条件写像が V6必須 / V8・V9・V10・V11禁止 を導く。裁定が別区分になった場合は、この節を再評価する。

### 3. `frontend/src/router.ts` / `frontend/src/screens/GameScreen.vue`（mount）

`GameScreenUndoProduct.vue` と同じ配線で、game screenのコンテナに追加する（最小形）。

```ts
import { onScopeDispose, ref } from 'vue'
import { useAuthStore } from '../stores/authStore'
import { GameLifecycleController, type GameLifecycleView } from './gameLifecycleController'
import GameScreenLifecyclePanel from './GameScreenLifecyclePanel.vue'

const auth = useAuthStore()
const identity = () => ({
  tenantId: auth.teamId,
  epoch: auth.authEpoch,
  verified: auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null,
})
const lifecycle = ref<GameLifecycleView | null>(null)
let lifecycleController: GameLifecycleController | null = null

async function loadLifecycle() {
  lifecycleController?.dispose()
  lifecycleController = new GameLifecycleController(props.gameId, identity)
  lifecycle.value = await lifecycleController.refresh()
}
async function endGame() {
  if (!lifecycleController) return
  await lifecycleController.end()
  lifecycle.value = lifecycleController.view
}
async function reopenGame() {
  if (!lifecycleController) return
  await lifecycleController.reopen()
  lifecycle.value = lifecycleController.view
}
async function retryLifecycle() {
  if (!lifecycleController) return
  await lifecycleController.retry()
  lifecycle.value = lifecycleController.view
}
onScopeDispose(() => lifecycleController?.dispose())
```

```vue
<GameScreenLifecyclePanel
  :view="lifecycle"
  @refresh="loadLifecycle"
  @end="endGame"
  @reopen="reopenGame"
  @retry="retryLifecycle"
  @resume-recording="resumeRecording"
  @back="backToRecording"
/>
```

`resumeRecording(handoff)` は既通常/NP入力controllerの再読込（handoffのgameId/next_positionを使う）へ、`backToRecording` は既記録画面へ接続する。**パネルは計算も保存もしない。**

### 4. backend・正式資産

- packet `2f464208` のbackend受理（`lifecycle_payload.py` / `lifecycle_execution.py` / `lifecycle_ports.py` / `game_lifecycle.py` / SQL / 0043 / ACL / registry / operation dispatch / started_games read）
- `game_reopen` の V5 literal・参加区分/C12・operation_events CHECK の正式裁定
- 新artifact/pins/D11/owner/body/最小ACLの正式導出
- `frontend/src/api/startedGame.ts` の `lifecycle-prefix-v1` 閉shape（packetのshared source。root反映）
- `frontend/src/domain/gameLifecycle.ts`（packetの新domain。root反映。FE6はこれを呼ばない）
- `backend/tests/db/test_game_lifecycle_http.py` と `test_game_lifecycle_screen_e2e.py` の実PG実行

## 未成立・残る接合（成功にしない）

1. 実PG/実HTTP/実画面での 終了v1→再開→2球→再終了v2→reload は**未実行**。`GameScreenLifecycle.e2e.ts` は実server/実PG/mountが無い場合に明示失敗し、2球追記ステップもrootの既通常/NP入力driver接続まで意図的に失敗する。
2. 再開種別は未裁定。裁定までは実装が `reopen-kind-unavailable` で止まる（**固定成功で埋めていない**）。
3. router mount・既通常/NP入力controllerへのhandoff接続はroot。
4. 非作者確認・正式受理・PR・mergeはroot。
5. 二重タブ/通信断/再起動/ACK喪失/越境の**実画面**試験は未実行。unit specは呼出順と分岐だけを検査する。

## 再現手順

```sh
cd /home/ymdms/projects/pitchlog-worktrees/feature-mvp-lifecycle-ui/frontend
pnpm install --frozen-lockfile
pnpm exec vue-tsc --noEmit
pnpm exec eslint src/api/gameLifecycle.ts src/api/gameLifecycle.spec.ts \
  src/screens/gameLifecycleController.ts src/screens/gameLifecycleController.spec.ts \
  src/screens/GameScreenLifecyclePanel.vue src/screens/GameScreenLifecycle.e2e.ts
pnpm exec vitest run src/api/gameLifecycle.spec.ts src/screens/gameLifecycleController.spec.ts
pnpm test
```

実画面E2E（rootが隔離PG・専用tenant・mount・入力driverを用意した後）:

```sh
PITCHLOG_LIFECYCLE_E2E_BASE_URL=https://<isolated-app> \
PITCHLOG_LIFECYCLE_E2E_GAME_ID=<created-and-started-game-uuid> \
pnpm exec playwright test --config <rootが本fileを追加したconfig> --project <lifecycle>
```
