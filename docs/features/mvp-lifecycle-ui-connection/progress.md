# 終了・追記再開 FE6 実接続改訂 進捗（レビュー反映）

## 固定点：2026-11-06

- **旧候補（レビュー対象・変更しない）**: `feature/mvp-lifecycle-ui` = `a36c323bdab235e51a480f43ecfc956bc04e1139`
- **新branch/worktree**: `feature/mvp-lifecycle-ui-connection` / `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-lifecycle-ui-connection`（旧候補から作成）
- **入力レビュー**: `~/.cache/pitchlog/lifecycle-ui-intake-independent-20261106/REPORT.md`（否決 P0=1・P1=4）。**本progressは作者の反映であり、再レビュー/採用の代わりではない。**
- **接合仕様**: 主担当の確定ゲート候補 `feature/mvp-lifecycle-product-connection@291451965c3eabf2914aaedca3a01fb685617264`（**in-review**）。旧`MINIMUM-INTERFACE.md`のflat V7は受理しない。
- **編集**: 従来のFE6 6path＋本plan/progressのみ。共有lib/router/正式contracts/DDL/backend sourceは不変更。

## 実装HEAD

- ステップ1: `e0717de2`（閉union V7＋読取transport＋plan）
- ステップ2: `c381219d`（実writer・断中base・依存順controller）
- ステップ3: `b98909f8`（パネル・断中E2E・不可視fixture）
- ステップ4: `28ac0390`（本progress）＋`da72922a`（確定済み終了の再開対象/prefix連続性のfix）
- コードHEAD: `da72922a`（branch tip。`git log -1` で固定）

## レビュー指摘への実装

| # | 指摘 | 実装 | 検査 |
| --- | --- | --- | --- |
| P0-1 | 書込前GET必須で断中の終了宣言を保存できない。未確定終了があると再開を追記前に止める | 最後の実GET baseを`pitchlog-game-lifecycle-base`へstrict保存。断中はbase＋耐久queueのchainから期待status/checkpointRef/targetを導き、実GETなしでend→reopen→再endを追記する。送信は先行slotが解消するまで待つ | 「実GET不能でも未送信プレイ→終了→再開→再終了…」spec |
| P1-2 | 既定writer/mountに実preconditionsが無く常にLOCK_UNAVAILABLE | `GameLifecycleControllerOptions.writer`を**必須**にし、`createGameLifecycleWriter(environment)`で既存記録画面と同じ6前提＋再検証を組み立てる。常時trueの既定を削除 | helperのfalse/true両spec。mount例は下記 |
| P1-3 | 旧flat V7が現gateの閉unionに適合しない | `checkpointRef=confirmed|confirmed_prefix|queued_predecessor`、reopen `target=confirmed|queued_end`へ改訂。flat形は`invalid-checkpoint-ref`/`reopen-target`で拒否 | API spec 15件（flat拒否・queued形・請求記号の非正準） |
| P1-4 | ACK後の古いGETを「再取得済み」とする | ACK後にD1 chainから期待status/確定版/receiptを計算し、GETがACK対象またはそれ以後を示した時だけbaseを更新。後退version/同一版で別receiptも拒否。古いGETは`refresh=pending`/`stale-read` | 「ACK後に古いGETが返ったら再取得完了にしない」spec |
| P1-5 | 不可視試合E2Eが可視の共通fixtureを使う | `PITCHLOG_LIFECYCLE_E2E_INVISIBLE_GAME_ID`を要求し、不可視専用IDで404/状態非表示を検査。2球driver未接続は明示失敗のまま | E2E（実server未供給のため未実行） |

### 断中chainの具体

- base: `{tenantId,gameId,d4,status,lastVersion,active,checkpointRef,d3,nextD2,appendPolicy,recoveryGeneration,lastSavedAt}`。実GET成功時だけ更新。
- 期待status: baseのstatusへ、baseの`d3`より後の耐久lifecycle slot（未送信/同期済み）をD1順で適用。
- checkpointRef: 直前D1がbase内→`confirmed`、base以降で受理済み→連続受理を確認して`confirmed_prefix`、未送信→`queued_predecessor`。
- reopen target: 直前終了がbase内/一致→`confirmed`、端末chainの未確定/未追従終了→`queued_end`（予約eventId/receiptId/D5/D1を固定）。終了slotが無いサーバー確定済み終了→`confirmed`。
- D2: 直前slotのV6→既存`nextOrdinaryD2`、無ければbaseの`nextD2`。断中3操作で`+1000`ずつ進むことをspecで確認。
- 再送: 先頭がlifecycleのときだけ同本文/同D5/同attemptで順に送る。通常操作の先行は既入力の再送に譲る（`pending-predecessor`）。本文・D5・attemptを書き換えないことをspecで確認。

## 実行した検査

| 検査 | 結果 |
| --- | --- |
| `pnpm exec vue-tsc --noEmit` | 成功（0診断） |
| `pnpm exec eslint <6path>` | 成功（0） |
| 対象spec | **35 passed**（`gameLifecycle.spec.ts` 15＋`gameLifecycleController.spec.ts` 20） |
| `pnpm test`（全件） | **154 files / 3490 tests passed**（新規2 file/35 testsを含む。約157〜159秒） |

mock ACK/IndexedDBの成功は実認可・実PG・実HTTP・実画面の成功ではない。実画面E2Eは未実行。

## 全path SHA256

```
e37f2b566b22c287986a570e5b704ebe686cba4e5077f45f8c6fd3c2f76bf2bd  frontend/src/api/gameLifecycle.ts
ff5565963ffae47fd54a4d8ecae0c8dfae34304cc697c0fedb39be4b1445770b  frontend/src/api/gameLifecycle.spec.ts
5f6e8f42adbd8e6f405a95dd1fa2d064b870e09aa4110b18db78d12ecd71bde2  frontend/src/screens/gameLifecycleController.ts
bbac9a18a2decf804e4d670ac93bad7aabe762f1cd01518f47170b39ab4fdb77  frontend/src/screens/gameLifecycleController.spec.ts
5909afbdffc0298371b9724c48f5d901cde1c6ebc71c91cd02c1696e180245ba  frontend/src/screens/GameScreenLifecyclePanel.vue
d2041b5c7ced458f3ce696c8ae1cf887f88c8dcc319fbba2a972f7999e8cfa6c  frontend/src/screens/GameScreenLifecycle.e2e.ts
8a2943de1b756ea3bde35f9b6e3a0bb38c8527ae4b2d9ad06fb19034e7bdf3e3  docs/features/mvp-lifecycle-ui-connection/plan.md
```

## 非作者確認

- **未実施**。本担当が作者であり、`REPORT.md`は入力であって採用ではない。独立再レビューで (1) 断中chainのstatus/CP/target導出、(2) 同本文/同D5/同attemptの再送、(3) ACK後stale GETの拒否、(4) 実writer preconditions、(5) 閉unionのflat拒否 を確認する必要がある。
- **実PG/実画面/実HTTPは未実行**。rootが隔離PGで実測するまで合格にしない。

## 接合差分（rootが直列反映）

### 1. `frontend/src/lib/sync/eventKinds.ts`（正式裁定が前提の候補）

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

名前は `GAME_LIFECYCLE_EVENT_KIND_NAME.reopen = '試合再開'` と一致させる。id `13` はクライアント内部のordinalで、backend V5は`game_reopen` literal。参加区分/C12はroot裁定に従う（候補であり確定ではない）。

### 2. `frontend/src/lib/sync/eventFieldRules.ts`

上記がLOGICAL_POSITION・非取消・非墓標/改訂なら**変更不要**（V6必須・V8..V11禁止が既写像で成立）。別区分なら再評価。

### 3. backend候補（`feature/mvp-lifecycle-product-connection`）

現候補は**旧flat V7**を読むため、閉unionへ追随しないと通常endもkind欠落で内容拒否になる。

- `backend/src/pitchlog/sync/lifecycle_payload.py::_read`
  - `checkpointRef`を`kind`で分岐し、`confirmed={kind,id,revision,digest}`、`confirmed_prefix={kind,id,revision,digest,d4,d1,d5}`、`queued_predecessor={kind,d4,d1,d5}`の完全一致を検査する。
  - reopen `target`を`confirmed={kind,version,eventId,receiptId}` / `queued_end={kind,d4,d1,d5,eventId,receiptId}`に分岐する。endは`target is None`。
  - d4は既V3 wire正規形、revision/d1/versionは正準正整数、digestは64hex。
- `backend/src/pitchlog/sync/lifecycle_execution.py`
  - 現在の`_canonical_json(payload["checkpointRef"]) == _canonical_json(cp["ref"])`は`confirmed`専用。`confirmed_prefix`/`queued_predecessor`は保存済みイベント原本・受理結果からD1 prefixを解決し、終端一致だけを受理する。未成立/gap/結果不明は当該イベント以降を未処理にし、D5を消費しない。
  - ホストへ渡す`target`は、`queued_end`を先行終了の実受理結果（version/eventId/receiptId）へ解決してから渡す。予約値を確定値として扱わない。
- `game_reopen`のV5/参加区分/C12/`operation_events` CHECK、0043・ACL・registry・artifact/pins・finished GETの正式化。
- `backend/tests/db/test_game_lifecycle_http.py`等で上記の実PG実行。

### 4. mount（`GameScreenOrdinaryPitch.vue` 等と同じ画面）

```ts
import { createGameLifecycleWriter, GameLifecycleController } from './gameLifecycleController'

const lifecycleWriter = createGameLifecycleWriter({
  topLevelHttps: httpsTopLevel,
  sameBrowserProfile: () => sameProfile.value,
  sameBrowsingMode: () => sameMode.value,
  sameStorageBucket: () => sameBucket.value,
  siteStorageAvailable: () => typeof indexedDB !== 'undefined',
  lockdownModeNotApplied: () => noLockdown.value,
  identityVerified: () => identity().verified,
})
const lifecycle = ref<GameLifecycleView | null>(null)
let lifecycleController: GameLifecycleController | null = null

async function loadLifecycle() {
  lifecycleController?.dispose()
  lifecycleController = new GameLifecycleController(props.gameId, identity, {
    writer: lifecycleWriter,
  })
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

`resumeRecording(handoff)`は既通常/NP入力controllerの再読込へ、`backToRecording`は既記録画面へ接続する。**パネルは計算も保存もしない。**

### 5. E2E実行条件

```
PITCHLOG_LIFECYCLE_E2E_BASE_URL=https://<isolated-app>
PITCHLOG_LIFECYCLE_E2E_GAME_ID=<created-and-started-game-uuid>
PITCHLOG_LIFECYCLE_E2E_INVISIBLE_GAME_ID=<invisible-or-absent-game-uuid>
```

2球追記ステップはrootの既通常/NP入力driver接続まで意図的に失敗する（固定stubで成功にしない）。

## 再現手順

```sh
cd /home/ymdms/projects/pitchlog-worktrees/feature-mvp-lifecycle-ui-connection/frontend
pnpm install --frozen-lockfile
pnpm exec vue-tsc --noEmit
pnpm exec eslint src/api/gameLifecycle.ts src/api/gameLifecycle.spec.ts \
  src/screens/gameLifecycleController.ts src/screens/gameLifecycleController.spec.ts \
  src/screens/GameScreenLifecyclePanel.vue src/screens/GameScreenLifecycle.e2e.ts
pnpm exec vitest run src/api/gameLifecycle.spec.ts src/screens/gameLifecycleController.spec.ts
pnpm test
```

## 未成立（成功にしない）

1. 実PG/実HTTP/実画面での end→reopen→2球→re-end→reload。backend未供給。
2. `game_reopen`種別・C12・閉V7のbackend実装。本候補はFE側だけ閉unionへ追随済み。
3. router/画面mount、既通常/NP入力driver。
4. 非作者再レビュー・正式受理・PR/merge。
