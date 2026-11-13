# FR-013 通常引き継ぎの製品接続（bounded first increment）

## 実装した操作

通常の記録権引き継ぎを、既存の初期権 broker・外部耐久台帳・V12Box・
`recording_generations` を使って製品 API と画面へ接続した。新しい権利判定器は
作らず、既存の `check_current_right` が読む保持端末・D4・V12 digest・復旧世代の
述語をそのまま使う。

| 手順 | 実装 |
| --- | --- |
| 旧保持端末の明示解放 | `POST /games/{game_id}/recording-right/handover/release`。旧端末の資格、旧 V12、最終 D1、新端末 ID、引き継ぎ要求 ID、明示確認を送る |
| 同期完了（確定水位）の照合 | 旧世代の `confirmed_watermark` と `applied_prefix` が最終 D1 以上であることを同一 SQL 取引で確認する。追いついていなければ解放しない |
| D4 の更新 | 旧世代を `revoked_at` で失効し、外部台帳の新しい世代を `issuance_order = max + 1`、D3 = 0 で同一取引に挿入する |
| 新保持端末の取得 | `POST /games/{game_id}/recording-right/handover/acquire`。新端末の資格で同じ引き継ぎ要求の配達だけを再交付する |
| 旧保持端末の拒否 | 旧世代は失効するため、既存の B4 述語（現世代・保持端末・V12 digest・復旧世代）に一致しない |
| 画面 | `/games/:gameId/handover`。旧端末は新端末の ID と要求 ID を入力して解放し、新端末は同じ要求 ID で取得して記録画面へ戻る |

解放要求の再送は同じ引き継ぎ要求 ID で冪等に成功し、新しい世代を二重発行しない。
取得要求の再送は `recording_right_deliveries` の同じ配達を V12Box で再交付する。

## 緊急引き継ぎを実装していない理由

緊急引き継ぎは、元端末が断中・故障・応答不能であることを前提に、最終同期の
完了確認を省略し、未送信記録が自動では取り込まれない旨の明示的な警告と確認を
要求する。さらに同時要求の後発を失敗させる契約を持つ。これは通常引き継ぎの
単なる「確認なし版」ではなく、次の意味判断を伴う。

- 元端末の最終 D1 を確認できない状態で、どの世代を新端末へ渡すか
- 旧端末の未送信記録を退避へ回す境界と、退避の閲覧・書き出しの製品導線
- 同時要求の後発拒否を、既存の部分一意とどう結び付けるか

今回の増分ではこれらを既存契約から一意に導けないため、緊急経路を偽装せず
未実装のまま残す。通常経路の API・SQL・画面・旧端末拒否・新端末再開を先に固定
する。

## 残余（今回の増分で閉じていないもの）

- **結果不明の引き継ぎ専用照会**: 解放が外部台帳の claim 後・業務 commit 前に
  失敗した場合、既存台帳の未解決予約として残る。通常の sync 試行照会に相当する
  引き継ぎ専用の照会・終結 UI は未実装。
- **退避イベントの管理コンソール閲覧・書き出し**: 旧世代イベントの B4 退避は
  既存の sync 経路が担うが、引き継ぎ画面から退避資料を開く導線は未接続。
- **実ブラウザ E2E**: 今回は backend の実 DB テストと frontend の Vitest で
  旧端末拒否・新端末再開を確認した。実ブラウザの 2 端末操作は未実施。
- **緊急引き継ぎ**: 上記のとおり未実装。

## 検証

- `backend/tests/db/test_recording_right_handover.py`: 実台帳・実 actor・実 SQL で
  旧世代失効、新世代 D3 = 0、旧保持端末の B4 述語不成立、新保持端末の述語成立、
  未同期水位での解放拒否を確認（2 passed）。
- `backend/tests/test_recording_right_handover.py`: 閉 wire、明示確認、V12 の
  非露出、SQL 契約、製品 API 接続を確認（7 passed）。
- `frontend`:
  - `gameStartPersistence.spec.ts`: 引き継ぎ grant の保存・復元と解放状態。
  - `GameScreenOrdinaryPitchController.spec.ts`: 解放済み旧端末の入力・HTTP 停止、
    新 D4/端末/proof での通常記録再開。
  - `recordingRightHandover.spec.ts`: 解放・取得の要求/応答と V12 の取出し。
