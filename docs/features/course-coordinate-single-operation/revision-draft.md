# 座標量子化 正式改訂草案（ADR-003 v0.10 / 要件 v2.18 / manifest / 例外）

対象: 実現性確認済み（プロトタイプ第2版 SHA `cfa0814d…33a37`、oracle `9743f330…0cb26`、Node/Chromium/Pythonホスト 22/22、字句0）。
正本は**未変更**。本草案を 7.3 の単一ゲートで確定する。承認者・レビュー実施者・対象版は実態で記録し、PO本人の確認・署名は代記しない。

## 1. ADR-003 v0.10（案）

**変更履歴 row（案）**: 「2026-10-30 | **D-14-m の対象に座標入力形成の量子化1件を追加（起案）**。D11=A（付録A-1 の half-up・量子化後に投手後方視点の左右反転）を、同一JS artifact の単一 operation `course-input-quantization` として実装する。**既存 D-6 の座標変換契約（`coordinate_transform_contract_v1.json` 42ケース）は変更せず**、量子化は別計算として独立に検証する。operation は内部で既存B-7の画面⇄保存変換を消費して保存正準整数を返し、`courseScreenXToStoredX` の float 反転を削除する。NFR-018(c) の逐語移植例外から float 反転を失効させる。**T1/T2 限定文は『追記』ではなく書き換え**、対象計算を T1/T2＋座標入力形成に限定する。射程: 上記 operation とその契約・manifest・pin の整合のみ。V7 formatter の配置は別判断。 | in-review |

**D-14-m 本文の改訂（案）**: 現行の「対象別開始後の T1/T2 に限る」記述を、
「対象別開始後の **T1/T2 および座標入力形成の量子化**に限る」へ**書き換える**（追記ではない）。
対象計算の識別子は `course-input-quantization`。同一JS artifact をブラウザ/Node/Pythonホストで実行し、
独立ベクタ・properties・mutation・directTargets の5判定を維持する。

## 2. 要件 v2.18（案）

**変更履歴 row（案）**: 「座標入力形成の量子化（D11=A）を、付録A-1 の half-up と量子化後の左右反転として明記。
**B-7 は変更しない**（`x_norm=x/263`、`y_norm=(263−y)/263`、画面→保存は丸めなし、保存→画面のみ付録A-1）。
入力形成と B-7 の**二段階境界**を注記し、入力は最短往復表現（指数可、入力長≤400・|指数|≤400）とする。
NFR-018(c) の例外表に当該 operation の検証テストを追加し、float 反転の例外を失効する。 | in-review

**B-7 への注記（案）**: 「本項の変換は**整数の画面座標**を受ける。入力形成（タップ float→整数）は
付録A-1 の half-up と量子化後の左右反転で行い、本項の変換前に一度だけ完了する。本項は丸めを行わない
（画面→保存）。保存→画面の丸めは表示専用。」

**NFR-018(c) 例外表（案）**: 行「`frontend/src/lib/courseInputView.ts` の float 反転
`courseScreenXToStoredX`」を**削除（失効）**し、行「`course-input-quantization`（artifact operation）」を
追加。検証テストは `backend/tests/domain/` の 42ケース不変確認＋量子化の独立ベクタ（境界・指数・範囲・反転）。

## 3. D-11 manifest（案）

`backend/domain/manifest.json` を**新設**する（`pitchlog-domain.json` は artifact SHA 宣言であり代用しない）。
- `calculation`: `course-input-quantization`
- `entrypoints`: `globalThis.PitchlogDomain.quantizeCourse`（JSON文字列 in/out）
- `directTargets`: 同一JS artifact の関数と内容 hash
- `comparison`: ブラウザ/Node の構造化値、Pythonホストの同一実行
- `vectors`: 量子化の独立ベクタ（既存42ケースは `coordinate-transform` 側で不変）

## 4. ゲート対象と確認（7.3）

- 対象正本: ADR-003 v0.10 / 要件 v2.18 / `backend/domain/manifest.json` / NFR-018(c) 例外表 / B-7 注記。
- 変更しない: 既存 `coordinate_transform_contract_v1.json` の42ケース、B-7 の式・丸め、D11=A の意味。
- 確認: P1-1（出力段の文書整合）、P2-1〜3（上限・文法・size ABI）、P2-4（入力長の前倒し）、P2-5（oracle 再現物）。
- レビュー: 既存委任の差分確認。全文周が必要なら PO 判断を記録。未解消を可決扱いにしない。
