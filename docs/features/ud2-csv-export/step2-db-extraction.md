# ステップ2 同一snapshotのDB抽出

実装日: 2026-11-06。基線 `14b96546`。追加readは `backend/src/pitchlog/repositories/play_export.py` に閉じ、既存のtenant bound `_TenantTransaction` だけを使う。生Session・任意SQL・テナント条件のないSELECTは公開しない。

## 実装した境界

- `tenant_export_read_scope(context)` を `repositories/transaction.py` へ最小追加した。tenant binding の最初のSELECTより前に `REPEATABLE READ` と `postgresql_readonly=True` を固定する。既存 `tenant_transaction_scope` の書込経路・RG1・commit処理は変更していない。
- 5つの閉じたread operationを追加し、`PRODUCT_OPERATIONS` と生成済み `repository-contract.json` へ反映した。
  - `PlayExportPlayRowsToken`: 有効PlayRowを `(play_number,id)` キーセットで最大500行。
  - `PlayExportEventsToken`: 受理済OperationEventを `(d2,id)` と NULL d2 の `id` キーセットで最大500行。置換・退役前も保持。
  - `PlayExportRunnersToken`: ページ内の `play_id` 集合を1文のOR等値で一括読取（N+1なし、最大500行）。
  - `PlayExportParticipationsToken`: 出場区間を `id` キーセットで最大500行。
  - `PlayExportTenantVocabularyToken`: `pitch_type` / `strategy` / `tournament` / `roster_label` の有効語彙を最大501行。
- gameは既存 `GameReadToken`、lineupは既存 `StartedLineupsReadToken`、選手・チームは既存 `PlayerReadToken` / `TeamRecordReadToken` を再利用した。新しいCAPは走者と出場区間のreadだけである。
- 可視性は `tenant_id` / `game_id` / `trashed_at IS NULL` / `hidden_at IS NULL` / status で判定し、不存在・別tenant・隠蔽・退避は同じ `PlayExportNotVisible` に閉じる。
- snapshot digestは同じRR内のgame・lineup・出場区間・選手・チーム・語彙・最新play/event/participationから作る。出力時刻はexport実行時刻であり、記録時刻の代替にしない。
- 88列写像は保存値参照だけを行う。T1のbefore/after、観測、走者、出場区間、保存背番号を使い、状態・スコア・球数・座標を再計算しない。欠測は `PlayExportSourceUnavailable` に列名・列index・供給群・必要producerを入れて返し、0・NULL・現在名簿で埋めない。

## 現時点の供給不足（実装対象）

以下は本ステップで意図的に非成功のまま残した。値の捏造はしていない。

| 列 | 供給群 | 不足している提供元 / 必要差分 |
|---|---|---|
| 34 球数 | G04-A | `ReadPlayExportPrimitives` と、現行D-1の有限reducerから生成する投手別累計球数のSQL。Python/JSの全event累積は不可 |
| 42 コースX / 43 コースY | G03 | 保存正準k（1/263）から旧画面座標へのD-1生成target。既存 `courseQuantization` は入力形成のみで逆変換ではない |
| 50 打球位置X / 51 打球位置Y | G10 | 保存正規化 `hit_x/hit_y` から旧画面座標へのB-6 field geometry生成target。コースk263の推測転用はしない |
| 61 打席結果 / 62 Result_col | G04-R | 旧表示規則のD-1生成formatter。保存T1と語彙は揃っているが、表示合成を手書きしていない |
| 73 先攻打順 / 74 後攻打順 | G04-R | 両チームの現在打順ポインタの保存値。`state.battingOrder` は攻撃側のみで、守備側を推測しない |
| 86 top_score / 87 bottom_score | G04-A | 回別得点配列を同RR・DB側で作るprimitive。保存T1の `inningScores` は累計 `{home,away}` のみで旧16要素配列ではない |
| 40 プレイの種類（non_pitch行） | G02 | `event_kind='non_pitch'` の旧区分（牽制/ボーク等）の保存値または表示binding。pitch行は「投球」を供給する |

G07（72 入力項目）とG08（75 経過時間 / 77 現在時刻）は、新規nativeに旧移行原字面がなく旧TagがWon'tであるため、明示NULL（元からの不在）として扱う。現在時刻や経過時間を新しく生成しない。

## 検証

- `uv run pytest tests/test_authz_repository_contract.py tests/test_authz_capability_catalog.py tests/test_authz_capability_registration.py tests/test_play_export_repository.py tests/test_play_csv_rows.py tests/test_play_export_archive.py tests/test_csv_export.py -q`: 336成功。
- 追加readの登録は単一表・tenant等値・LIMIT bindの既存検証を通る。`EXPANDING` bindは既存認可検査が許可しないため、走者はページ内play_id数ぶんのOR等値へ展開した。
- 実DB/HTTPはステップ3以降で接続する。本ステップのpure試験成功を実試合の供給成功とは扱わない。
