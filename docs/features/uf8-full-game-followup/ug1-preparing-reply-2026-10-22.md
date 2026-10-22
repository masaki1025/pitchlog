# U-G1 preparing接続へのU-F8回答（2026-10-22）

対象は[既存照会6337294852](https://github.com/masaki1025/pitchlog/pull/171#issuecomment-6337294852)、D担当の承認計画98cd9974/DTO・read component実装9c4f8f02と限定設計である。U-F8が回答するのは自担当のパス分担・表示境界であり、他担当の正式受理/実提供・7.7・本人確認を代記しない。

## パス・責任の回答

| 対象 | U-F8回答 | 実編集担当・境界 |
| --- | --- | --- |
| `backend/src/pitchlog/api/schemas/games.py` の `PreparingGameCreate` / `PreparingGameListRequest` | 担当外（D所有を確認） | D。aware scheduled_at、5区分、両team_record UUID、必須tournamentのexisting/new排他、予約field拒否をUI入力へ対応付ける案は受理。保存DTOにtenant/status/applied_rules/D4等を加えない |
| `repositories/games.py`、read API・応答codec/認可登録 | 担当外 | Dがtenant/preparing/可視条件、keyset limit/cursor、詳細1件、保存snapshotの再取得を所有。今回のcomponent実装を正式API提供済みとしない |
| `GameScreenEntry.vue`・`GameScreenEntryRecord.vue`・`GameScreenEntryTypes.ts`・対応spec | 受理（Dへの限定編集分担） | Dがpreparing作成フォーム/一覧/詳細の限定接合を編集可能。U-F8は同じフォームを並行実装しない。既存開始/再開/記録権・前提表示・封鎖の意味と回帰条件はU-F8が保持。所有移管はこの限定差分だけで、U-F8全体ではない |
| 新 `frontend/src/api/games.ts`・必要なら薄い `GameScreenEntryProvider.ts` と固有spec | 受理（D担当） | Dが正式API→表示用EntrySupplyの変換・取得・認証世代/tenant/route/page失効を所有。既存正規client/Pinia/QueryClientを再利用し、HTTP/ACK/queueは新作しない |
| 必須大会の候補取得・既存キー/新名称入力・同scope名称登録 | 受理（preparing限定でD担当） | 最小選択/入力は同じ作成フォーム内。大会管理画面/規則割当編集は担当外。新名称から仮keyを生成せず、語彙の正式keyをサーバーが確定。取消/保存失敗で新大会だけ残さない |
| `router.ts` 等 | 原則変更不要 | 既存 `/games` と `/games/:gameId/record` を再利用。props供給のため実際に必要な薄いroute接合だけ、具体差分をDから提示して調整。別画面/新routeを並行追加しない |
| 共通clientのgames認証経路分類 | 受理（要最小差分・所有照合） | Dの計画内のCookie/authEpoch保護追随だけ。506の通信/wire/ACK/queueには触れない。共通client実編集の時点で現所有/並行差分を照合する。U-F8が今から独自clientを作らない |
| U-G1全体の開始/初期権、resolver/codec、RG1、同期provider | 担当外 | 各正式所有を保持。Dのpreparing分担をこれらの提供/実装許可へ拡張しない |

現在U-F8は上表の製品UI/API clientを編集していない。追跡枝の編集予約は `docs/features/uf8-full-game-followup/` と既存U-F8作業ログだけ。Dの限定UI実編集を未回答待ちへ戻さない。実際の新しいパス競合が出たときだけ、そのパスを調整する。

## 型への要修正点と接合

1. **要修正**：作成入力 `PreparingGameCreate`、read応答候補 `PreparingGameRead`、表示用 `EntrySupply<T>` / `RecordDetail` / `EntryEnvironment` は別物。作成は新preparing保存であり、開始候補の `starts` や開始成功へ写さない。DTOの構造受領を出所/相関検証済みsnapshotへ昇格しない。read応答型・options型・6-key公開codecが未提供なら、候補型/不正入力拒否・変換契約試験までに限定する。
2. **受理**：一覧 `EntrySupply<GameListPage>` は取得要求時の `tenantId/authEpoch/path/requestKey` を固定し、返却直前にも再照合。opaque cursorは解釈せず `nextKey` へ渡す。戻る操作はその認証/tenant内の訪問済みcursor履歴から作るか非表示にし、架空cursorを生成しない。上限・可視条件はサーバーのまま。ページ切替の旧応答を採用しない。
3. **要修正**：preparing詳細だけでは記録権・スタメン・端末前提/永続化許可/キュー件数は分からない。`existingState='draft'` はpreparingの表示対応に限る。`recordingRight='unknown'`、lineup/draftRestorationと環境は未取得として保持し、GET成功でheld/met/queuedCount=0を捏造しない。既存RecordDetailへ不足する値は未取得表示へ倒し、保存snapshotの表示は正式codecで検証された値だけを受ける。
4. **受理**：`GET /games`・`GET /games/{id}` はread認可/正式registry/codec成立後、resolverの実行や通常書込RG1の成功を待たずに接続可能。DTO/read component・providerの純粋変換、欠損/拒否/遅延/tenant切替/route切替/cursorの契約試験は先行できる。未登録APIの公開や合成のread成功は不可。
5. **受理**：作成フォームの5区分・aware日時・両team・大会existing/new・任意ラベルの入力/検証と送信中抑止は、保存成功未接続でも先行可能。実POST・成功表示は正式resolver/codec/登録と安全なRG1成功許可の提供後だけ。日時入力は端末のローカル日時から明示timezone付きへ変換し、naive値を送らない。フォーム内の新大会入力・取消はDが一箇所で実装する。
6. **受理**：createの結果不明は成功にせず、自動再POSTしない。二重submit防止、失効済み遅延POSTの新tenant cache反映拒否、同ID/保存snapshotの正式GET/reload確認、失敗時に試合/新大会が残らない検査はDの合格条件を維持する。preparing保存の成功を開始/1球保存の成功へ扱わない。

## 受取物・共同確認

Dから受け取るのは、公開PR/固定HEAD、API/DTO/正式read応答型・options型・codecのimport先、認可/registryの正式提供、変換関数と上記失効契約試験、resolver/安全RG1の提供SHAと保存成功後の実HTTP/専用DB/reload証跡。公開型の提供・7.7・実保存の未達を未達として保つ。実装後の結合試験をDの独立DTO/read/フォーム着手前の追加条件にはしない。

### 型と共有資産順序の補足

既存EntryDatumはready/pending/denied/failedの閉型であり、未提供のlineup/draftRestorationを架空のpendingリクエストとしてRecordDetailへ詰めない。Dの限定差分でpreparing詳細の表示型を分離するか、既存RecordDetailは未供給のまま維持する接合をU-F8として受理する。いずれも記録/開始のready化はしない。

Dが#173後の正式read登録でも同じ共有資産を変更するため、U-F8は#174→#173→Dのread登録の実統合/引渡しを先行させる。その後だけU-F8正式CI候補を現基線から再導出する。これはU-F8が自分の正式編集を後に置く回答であり、他担当の受諾を代記しない。補足はDへ送付済み。
