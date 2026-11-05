# 主担当への提案: 試合ライフサイクル契約（未受理）

- 状態: 提案（`contracts/`・正本・共有台帳へは未反映）
- 起点: `660d58554f3e0b74da2623ffd7e9a452188d7772`
- 関連: `plan.md` / `findings.md`

本spikeで観測した不足を、主担当が契約として採否するための候補として分離する。
以下のどれも本枝では実装済み・正式受理済みと主張しない。

## 1. 終了宣言の V7 payload

現行 `game_end_declaration` は V5 と D1/D2 だけを持ち、V7 の閉じた形が
`contracts/` に無い。spike は次を使った。

```json
{
  "formatVersion": "game-lifecycle-spike-v1",
  "action": "end",
  "finalization": {
    "version": 1,
    "previous": null,
    "state": {
      "stateFields": {},
      "scoreboard": {},
      "battingOrderBySide": {}
    }
  }
}
```

提案する意味:

- `version` は試合内で単調増加する終了確定版（1 始まり）。
- `previous` は再終了の直前の終了确定版 `{version, d1}`。初回は `null`。
- `state` は既存 T1/T2 の保存済み最終状態。画面で再計算しない。
- サーバーは `state` を直前の確定プレイ `after` または直前の再開時状態と
  byte/値で照合し、一致しなければ拒否する。
- `games.status='finished'` への投影は本spikeの範囲外。製品では
  `operation_events` の受理と同一 TX で `games.status` を更新する必要がある。

## 2. 再開イベント

再開は Must 6 種の操作イベントに含まれず、`operation_events.event_kind` にも
専用値が無い。spike は同じ `game_end_declaration` の V7 で
`action: "reopen"` を送った。

```json
{
  "formatVersion": "game-lifecycle-spike-v1",
  "action": "reopen",
  "finalization": {
    "version": 1,
    "target": { "version": 1, "d1": 2 },
    "state": {}
  }
}
```

提案する契約:

- `game_reopen`（仮）を新しい操作イベント種別として追加する。D1/D2 を持ち、
  D3 を前進させる。`game_end_declaration` の流用は監査上誤解を招くため、
  正式契約では分離する。
- `target` は失効させる終了確定版 `{version, d1}`。`state` は終了時の状態と一致。
- 再開は直前の終了確定版だけを失効させる。古い版・別試合・別世代を名指せない。
- 再開後に終了条件が成立していても、再終了宣言までは入力を受け付ける
  （FR-005 の終了条件ロック解除）。本spikeはこの入力経路を未接続。

## 3. 終了確定版と成績側への引き渡し

成績側（`feature/mvp-stats-*`）は `games.status='finished'` だけを確定根拠に
しない方針を採っている。本spikeは次を提案する。

```json
{
  "gameId": "…",
  "status": "finished",
  "activeFinalization": {
    "version": 2,
    "d1": 6,
    "d5": "…",
    "stateDigest": "sha256:…",
    "finalizationDigest": "sha256:…"
  },
  "finalizations": [
    { "version": 1, "d1": 2, "invalidatedBy": { "d1": 4 } },
    { "version": 2, "d1": 6, "invalidatedBy": null }
  ]
}
```

- 成績側は `activeFinalization.finalizationDigest` を公開版の同一性キーにし、
  `version` を単調増加の世代として扱う。
- 再開は旧版を `invalidatedBy` で失効させ、旧版を最新として返さない。
- 再終了は新しい `version` と新しい `finalizationDigest` を発行し、旧版の
  in-place 上書きをしない。
- `games.status` を併用する場合も、`status='finished'` 単独では確定にしない。
  終了イベントの受理と同一 TX で更新されたことを別の receipt/pointer で照合する。

## 4. 非 play イベントを含む prefix の bridge

本spikeの最大の残件。現行 v3 play prefix projection は、同一 PA の
`pa_start_source` 以降に `event_kind <> 'play_input'` のイベントがあると
`prepare_play_prefix_projection` で拒否する。終了・再開は D1 を消費するため、
再開後に通常投球を追記すると次のどちらかが必要になる。

1. 非 play イベントを prefix の checkpoint に橋渡しし、次の play の
   `prefixRef`/history へ反映する（bridge checkpoint）。
2. 終了・再開を D1 列の外へ移し、別のライフサイクル列／表で管理する。

本spikeは 1 も 2 も実装しない。再開後の追記は「製品 prefix 境界の未接続」と
して残す。契約案としては、bridge checkpoint の `version`、`prefixRef`、
`history` への非 play 行の表現、再計算対象を主担当が決める必要がある。

## 5. 製品の終了後ロック

本spikeは `games.status` を更新しないため、終了後も `/sync/events` へ
play を送れる余地が残る。製品接続では次を同一 TX で行う必要がある。

- 終了宣言の受理と `games.status='finished'` の更新
- 終了後の play/substitution/tiebreak の P2/P1 入口での fail-closed
- 再開の受理と `games.status='in_progress'` の更新
- 終了後修正（P3）は `finished` のまま許可する既存仕様との整合

この投影は本spikeの `spike_end_reopen_ports` に置き場所だけ用意できるが、
`games.status` の更新 operation と認可 catalog の正式登録が必要なため、
本枝では提案に留める。
