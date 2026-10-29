---
feature: mvp-first-ball-screen-commit
status: in-review
承認: 一部（2026-10-29 主担当判断: D02=A 技術方針・J2=A 進行・B-1〜B-3 委任手続。計画レビューは未実施）
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

## 8. 決定の区分（2026-10-29 改訂）

本計画の判断は二層に分ける。**回答待ちを初球作業全体の停止条件にしない。**

- **既存PO委任で主担当が決める**: D02=A（技術方針。下記8-1の確認対象を条件）／J2=A（単一artifact
  operationの追加と正本整合を主担当判断で進める。対象版・レビュー・根拠を記録し、PO本人の
  個別確認としては記録しない）／B-1〜B-3（対象版を固定した非作者レビューと値照合。B-3は隔離枝の
  値をそのまま正式受理せず、実PRの基線・最終候補から前後値と履歴を照合して受理）／C-1〜C-6。
- **新たな意味判断（PO）**: 初球では **D01 のみ**（9回裏でサヨナラとコールドが同時成立した場合の
  終了理由。B=サヨナラを推奨案として保持）。初球の実装・検証は D01 を待たずに進める。

## 8-1. D02=A の確認対象（ブラウザ排他とサーバーwriter bindingは別）

サーバーwriter bindingは `(tenant, attempt_id, phase_id)` の**1要求1束**の資格であり、
1球ごとに開閉できた実測（`tests/db/test_first_ball_vertical_http.py`）は**ブラウザの排他**を
証明しない。A を採用する条件として、次を必須の対向検査とする（非作者レビュー
`9549c30730343fd833f1c98509d46124f7d895b6760a2498a758d8911d640cd7` の指摘）。

| 区分 | 検査 | 合格条件 |
| --- | --- | --- |
| 画面 | 待球中フリーズで待機タブの確定が非受理（追記0・D1不消費・Q2-b） | **A+lease** か **A+限定受容** の選択が先。未選択なら解除しない |
| 画面 | 確定中フリーズでロック保持継続／非所有タブ拒否／終了→再選出→再検証→再開 | 既定経路で green |
| 画面 | `revalidateSingleWriter` の**本番実装**（現状スタブのみ・未指定は全不受理） | 実装＋注入忘れ検出 |
| 資産 | `leader-freeze-reelection_v3`（`freeze-between-balls` / `freeze-during-commit`）、`waiting-input-not-accepted_v3`（再入力は新要求として測定）、v2/v3共存 | 契約検査 green |
| 実ブラウザ | 同一context 2ページ同時確定／CDP凍結→待機ページ／強制終了→再開 | green まで「ブラウザ排他成立」と書かない |
| サーバー | 同一D5・**別attempt**の再送で二重適用しない／2タブ同時再送でQ5二重発火なし／旧D4蘇生タブはB4で退避 | green |
| 保持 | 未送信・要操作は24hで破棄しない／未解決要求がある間は清掃を先行させない／清掃でD1が巻き戻らない | green |

**別判断（Aの採用と切り離す）**: (1) 正本 7-4 Q2-c/10-2 の期間の読み替え（正本改訂）、
(2) 7-3 手順1の再送主体の追加（U-F7 所有）、(3) 資産 v2→v3 の移行。安全保証・再送規則の
差分が必要になった時点で、この計画ではなく当該正本/所有単位の判断へ戻す。

## 8-2. 座標（J2=A）の扱い

- 現行の Python `k/263` は**候補**であり、正式採用済みではない（独立レビュー
  `3bfddb0d6eb722dea268c24112b2e09e860aa5bf177e83fcd6a879720d957a06`、P0=2）。
  コードの docstring も候補へ是正済み。
- 目標は**単一artifact操作**（tap→k と k→保存値の供給）。実現案は DSL に正規化 primitive
  （BigInt長除法→十進文字列18桁以上・半偶数丸め）を追加し、Python は `float()` のみとする案を
  第一候補とする（264点全一致を実測済み。17桁は13/264が1ulpずれる）。
- 正式採用の条件: artifact再生成とpin更新（`frontend/public/domain/pitchlog-domain.json`、
  `first_ball_payload_vectors_v1.json` の `artifactSha256` 102箇所）、264点全数ベクタと
  非等価変異、manifest/directTargets 登録、非作者レビュー、ADR v0.10/要件 v2.18 の確定ゲート。
  対象版・レビュー・根拠を記録し、PO本人の個別確認としては記録しない。

## 8-3. C条件（維持）

- C-3: 24時間で未解決要求・未送信記録を消さない。結果不明時の保持・照会・後着遮断を満たすか確認する。
- C-4: fixture専用環境でも実認証・実記録権・実API・実DBを通す。成功を固定する模擬認可にしない。
- C-5: 初球1件の先行提供は可。2球目以降の記録・閲覧・訂正はMVP完成までの必須作業として残す。
- C-6: ACK到達だけで成功表示しない。受理・保存された結果（A5と保存行）を確認してから成功表示し、
  未処理・拒否・結果不明は成功表示しない。
