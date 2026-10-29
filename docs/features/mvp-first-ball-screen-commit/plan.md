---
feature: mvp-first-ball-screen-commit
status: in-review
承認: 未（計画レビュー未実施。PO委任の承認記録はレビュー後に追記）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-first-ball-vertical
created: 2026-10-29
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画: 実画面からの初球commit（隔離E2E）

## 1. 背景・目的

初球の縦断は**API経路**で実証済み（`tests/db/test_first_ball_vertical_http.py`、`b048aba3`:
実HTTP開始→1球→ACK→実PG1行→再送再掲→記録後409）。ただし製品画面には記録経路が無い:
`/games/:gameId/record` のhostが `mode="preparing-read"` 固定で `GameScreen.vue` をmountせず、
`PITCH_COMMIT_BLOCKED=true`・確定ボタンに `@click` が無く、enroll/start client・device/attempt
ヘッダ・V8/座標/語彙の供給も無い。本計画は**隔離環境で実画面から1球を確定し、再読込で同じ状態を
確認する**ところまでを、既存API縦断の証拠と分離して達成する。

## 2. スコープ

含む: (a) 記録画面hostの明示mode（`preparing-read` 以外）とcommit配線、(b) 端末enroll/試合開始の
clientと資格の端末保存、(c) 同期POSTの device/attempt ヘッダと**送信前の耐久attemptバリア**、
(d) 単一artifactからのV7/V8（観測・参加者・計算）整形とコース正準kの供給、(e) 球種/結果の
tenant語彙取得、(f) 記録後再読込の表示（`GET /started` の 200/recorded は本計画では**消費しない**:
U14 DTOが未提供の間は409を「再読込は未提供」として明示）、(g) broker/RG1制御を露出するE2Eモード。

含まない: 全操作・訂正・終了/再開・成績/CSV、P3、記録後GET DTO（U14）、実機/HTTPS、正式7.7。
`PITCH_COMMIT_BLOCKED` の解除は **MVP-D02**（排他の保持単位）の回答後に限る。

## 3. 影響する正本

- `docs/design/sync-protocol.md`: **反映なし**（DI1〜DI5・7-3・6-3-A は既に再送/試行を規定。
  本計画は実装接続のみ。版は 0.12 のまま）。
- `docs/requirements/requirements-pitchlog-2026-07-22.md`: **反映なし**（FR-012/013 の範囲）。
- 記録後read DTOは別単位（`mvp-started-read-http` §8 の拡張点／`tsk544` 単位5）。
- 座標: 画面tap→正準kは単一artifact operation（J2は継続提示中）。k→保存Doubleは
  `sync/first_ball_course.py` の単一実装を再利用し、TS側に写像を複製しない（NFR-018）。

## 4. 実装方針

隔離E2Eは既存 `GameScreenPreparingRead` の loopback http 方式を再利用し、backendを
「binding client設定＋RG1 client設定＋実broker」付きで起動する専用modeを追加する
（実brokerは現行の縦断fixtureと同型。新規秘密の発行なし）。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 記録画面hostのmodeとcommit配線（`MVP-D02=A` 前提の設計メモを同梱） | hostが記録modeで `GameScreen` をmountし、確定ボタンが `commitPitchEvent` を呼ぶ。封鎖理由/解除条件をコードとテストに固定 |
| 2 | enroll/start clientと端末資格の保存（SecretStrをログ/表示へ出さない） | Vitestで成功/拒否/形式不正。資格がDOM/ログへ出ない |
| 3 | 同期POSTの device/attempt ヘッダと**送信前耐久attemptバリア**（IndexedDB） | 送信前保存失敗で送信しない。再起動時に未照合を自動送信しない。attemptは同一不明試行で再利用・新試行で新規 |
| 4 | V7/V8整形（単一artifact評価→`first-ball-play-v1`）とコースk供給 | Vitestでartifact評価と一致。Pythonの`read_first_ball_payload`と同じ閉形式。座標の写像複製0 |
| 5 | 球種/結果のtenant語彙取得（既存APIまたは閉じた限定read） | 語彙0件/別tenantで送信不可。値は表示のみで計算に使わない |
| 6 | 記録後表示（409=「再読込未提供」を明示、成功扱いしない） | 409で保存成功と表示しない。再送は同一要求のみ |
| 7 | E2Eモード（broker/RG1露出）と Playwright `recording` project | 実Chromium→実HTTP→専用PGで1球保存・再読込一致・ACK消失再送（重複）・異内容拒否を確認 |
| 8 | 独立レビューと固定点記録 | 非作者レビューP0/P1=0、台帳へ利用者ができる操作を追記 |

## 5. DoD

- [ ] 実画面→実HTTP→専用PGで1球が保存され、再読込で同じ状態（または未提供の明示）になる。
- [ ] 通信断・再送・異内容・attempt再利用の各拒否が実画面経路で確認される。
- [ ] 資格/秘密がDOM・ログ・IndexedDBの非意図領域へ出ない（NFR-014/NFR-023）。
- [ ] 共有DB・実機・運用HTTPSを使わない。`PITCHLOG_TEST_*DSN` は unset。
- [ ] 非作者レビューと計画のステップ対応が記録される。

## 6. テスト計画

- `frontend`: Vitest（host/commit/queue barrier/整形/語彙/409表示）、`prettier`・`eslint`・`vue-tsc`。
- `frontend/src/screens/*.playwright.config.ts` に `recording` projectを追加。既存 `sealed-ui`・
  `preparing-read` は変更しない。未提供経路をskip合格にしない。
- `backend`: 既存縦断（`tests/db/test_first_ball_vertical_http.py`）を回帰として維持。
  新規server modeは実broker/RG1を必須にし、設定欠落時は503で閉じる。

## 7. 未決・依存

- **MVP-D02**（排他の保持単位）: 回答まで `PITCH_COMMIT_BLOCKED` を解除しない。A（1球ごと）を推奨。
- **J2**（座標単一artifact operation）: 画面tap→kの供給が未確定。回答までkは試験入力で代替し、
  製品正解値とは扱わない。
- 記録後GET DTO（U14）: 本計画では409の明示表示まで。DTOは別単位で非作者レビュー必須。

## 計画レビューと承認

**未実施**（周回0）。本計画は起案のみで、実装・承認・PO委任記録はレビュー後に追記する。
