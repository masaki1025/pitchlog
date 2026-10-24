# U-X1 MVP spike（状態計算 T1・終了判定 T2・1 球保存への接続）

**状態: spike（凍結）— マージしない・push しない。本設計へ持ち込む材料として残す。**

- 枝: `spike/ux1-mvp`（起点 `83e147cc` = 1 球保存 spike の先端）
- worktree: `~/dev/pitchlog-mvp`
- 正本（`docs/requirements`・`design`・`adr`）と `contracts/` は**変更していない**

## 0. 追補（2026-10-24）: 成果物（TS 正本）で T1 を実装した

§5 の三択は **案 1（許可構文の最小拡張）** で解消した。実測すると、変換器は esbuild で
あり、`scripts/domain-checks/policy.ts` の許可表は「変換できない」制約ではなく
**宣言された安全側の文法**だった。T1 に不足していたのは `ElementAccessExpression` だけで、
規則表の参照（`STATE_RULES[resultId]`）に必要なので 1 種だけ理由付きで追加した。

- 追加: `[ts.SyntaxKind.ElementAccessExpression, '規則表・表引きのキー参照']`
- 追加しなかったもの: `number`（D-14-e の機械拒否を維持）、`ConditionalExpression`・
  数値リテラル・`Array#push`・`.length`（戻り値・型が number になり `NUMBER_TYPE` に触れる）。
  このため T1 は bigint・`if` 文・`.map`・固定フィールドで書いている。
- 実装: `frontend/src/domain/stateTypes.ts`（型）/ `stateRules.ts`（42 結果IDの表）/
  `state.ts`（`derive`）/ `publicApi.ts`（`deriveState`: JSON 文字列 in/out、整数は十進文字列）
- 検証:
  - Vitest `state.spec.ts`: matrixRows **89/89**（5 面＋23 フラグ）、遷移後状態の差分 **34 行**（P-6 と一致）
  - `publicApi.spec.ts`: 単打の境界計算、未知 ID・数値入力の拒否
  - **ビルド済み artifact を Node で実行して契約 89/89**（`frontend/public/domain/pitchlog-domain.js`、
    sha256 `b45b123b…`、18,097 bytes）
  - `eslint` / `vue-tsc --noEmit` / `pnpm test`（1187 件）green

**残る NFR-018 の論点**: T1 が artifact と Python（`backend/src/pitchlog/sync/spike_domain.py`）の
2 実装になっている。spike では照合用に意図して残したが、製品では artifact を単一実装とし、
バックエンドは `domainrt/host.py` 経由で artifact を呼び、Python 側の T1 は削除する。
T2 も同じ形で artifact へ移すのが次の段階。

## 1. 何を作ったか

| 対象 | 実装 | 検証 |
| --- | --- | --- |
| T1 状態計算（1 球の遷移） | `backend/src/pitchlog/sync/spike_domain.py` の `RULES`・`derive` | 契約 `matrixRows` 89/89（5 面＋23 フラグ）、遷移後状態は既知の 34 行差分のみ |
| T2 規則設定の検証 | 同 `validate_rule` | `validationErrors` 12/12 を拒否、境界 39/39（受理 27・拒否 12）、F-2 既定 2/2 受理 |
| T2 試合終了の判定 | 同 `decide`（6 分岐） | `cases` 248/248 |
| 1 球保存への接続 | `spike_http.py` の `POST` ACK と `GET` に `game_state` を追加 | 実 DB で「保存→状態が返る→再読込で同じ状態」 |

`game_state` の形は `{stateFields, scoreboard, appliedEvents}`。状態は**保存しない**。
毎回、現行世代のイベント payload（`resultId` と `pitchEventKind`）を先頭から畳み込んで再現する
（保存後応答と再読込が同じ計算を通る）。

初期状態は 1 回表・アウト 0・走者なし・カウント 0-0・打順 1・0-0。

## 2. T2 の 6 分岐

| outcome | 契機 | xMark |
| --- | --- | --- |
| `cold-end` | コールド成立ティアあり・裏・リード | x-mark |
| `walk-off` | 最終回以降の裏・リード・per-pitch の打撃結果で得点 | recorded-score |
| `normal-end` | 最終回裏のリード（延長なし）／延長上限の翌回表でリード | x-mark / recorded-score |
| `limit-draw` | 延長上限の翌回表で同点 | recorded-score |
| `extra-continue` | R+1 回表で同点・タイブレーク無効 | recorded-score |
| `tiebreak-continue` | R+1 回表で同点・タイブレーク有効 | recorded-score |

`walk-off` と XMARK-02（記録済みスコア）の区別は「per-pitch かつ kind=batting-result かつ得点結果」で行う。
条文外・裁定依存の 2 件（`secondary-result.pitch-clock-violation`・`batting-result.sacrifice-bunt-error`）は
PO 裁定（2026-10-01 案C・2026-09-30 案A）に従う。

## 3. 実行手順（再現）

```bash
# 契約全件（DB 不要）
cd ~/dev/pitchlog-mvp/backend && uv run pytest tests/test_spike_domain.py -q

# 実 DB（保存→状態→再読込）。DSN は環境変数で渡す
export PITCHLOG_TEST_ADMIN_DSN="host=127.0.0.1 port=5432 user=pitchlog password=... dbname=pitchlog"
export PITCHLOG_TEST_ROLE_DSN="host=127.0.0.1 port=5432 user=pitchlog_spike_probe password=... dbname=pitchlog"
uv run pytest tests/db/test_spike_one_ball_slice.py -q
```

## 4. 実測結果（2026-10-20）

- 契約照合（unit）: 9 passed
  - T1 `matrixRows` 89/89（5 面＋23 フラグ）
  - T1 遷移後状態: `historyInput.after` との差分 **34 行**（P-6 の実測と一致）
  - T2 判定 248/248、不正 12/12、境界 39/39（受理 27・拒否 12）、F-2 2/2、DRAW-01/03 の理由
- 実 DB: 4 passed（既存 3＋新規 1）。payload `{"resultId": ..., "pitchEventKind": ...}` で
  - 単打 → 走者一塁・打順 2・カウント 0-0
  - 本塁打 → 走者なし・0-2（一塁走者と打者の 2 人が生還）・打順 3
  - 各応答の `game_state` と `GET` の `game_state` が一致
- 別実装一致（P-6 の `derive.py` / `t2_validate.py` を再実行して直接突き合わせ）
  - T1 89/89、T2 不正 12/12、T2 境界 39/39
- 壊し試験 3/3 検出（規則表のアウト数・DRAW-01 の拒否・walk-off 条件）、復元後 green

## 5. 設計上の判断と限界

**ドメイン成果物（`frontend/public/domain/pitchlog-domain.js`）での実装は断念した。**
（→ 追補 0 で案 1 を採用し、許可構文を 1 種だけ拡張して解消した。以下は当時の判断の記録。）
変換可能な構文は `frontend/scripts/domain-checks/policy.ts` の `ALLOWED_SYNTAX` で限定され、
T1/T2 が必要とする `interface`・配列型・分割代入・要素アクセス（`arr[i]`）・複合代入（`+=`）・
`number` を拒否する（実測: `NUMBER_TYPE` / `UNKNOWN_SYNTAX` / `UNSUPPORTED_OPERATOR`）。
`for...of`・プロパティ参照・オブジェクト/配列リテラル・bigint だけで書き直すことは可能だが、
塁を配列添字で扱えないため、状態を `r1/r2/r3` の個別フィールドへ展開する大規模な書き換えになる。

したがってこの spike の Python 実装は**製品の単一実装ではない**。NFR-018（単一実装）を満たすには、
本設計で次のいずれかを決める必要がある。

1. 変換器の許可構文を広げる（要素アクセス・分割代入・複合代入・interface・number）＝ 生成系の変更
2. T1/T2 をサーバー側の単一実装にする（成果物は投球入力の検証など限定用途に縮小）
3. 成果物用に「配列を使わない」内部表現を先に設計する（`r1/r2/r3`・`outs` 等の平坦な状態）

## 6. 残件（申し送り）

- 追補 0 の帰結: 許可構文へ `ElementAccessExpression` を足した差分は**宣言の変更**なので、
  本設計では当該表の所有者の承認が要る（spike では提案として置く）。
- T2（検証・6 分岐判定）を artifact へ移す。T1 と同じ形（bigint・十進文字列）で書ける見込み。
- バックエンドを `domainrt/host.py` 経由の artifact 呼び出しへ切り替え、Python の T1 を削除する
  （NFR-018 の単一実装）。
- `stateRules.ts` は Python の規則表から一度だけ機械生成し、以降は TS を正本とする
  （生成スクリプトは spike の作業用で、リポジトリには置いていない）。
- 上記 5 の三択（**本設計の最初に決める**）。
- `historyInput.after` の 34 行差分（P-6 が検出済み）。契約側の語彙違反・走者/得点の矛盾で、
  計算側は契約の `expected`（5 面）と一致している。契約所有者の裁定待ち。
- T2 の `sourceClauseIds` 過剰表示（P-6 指摘）と、判定結果の記録先（署名のみ or `provenance` 新設）。
- `state.battingOrder` は 9 人固定の巡回で実装。実際の打順（スタメン・交代）との接続は未実装。
- 得点・打点の付与は結果 ID 単位の近似（`error` は打点 -1、`double-play` は 0）。付録E-2 の
  個別条文との突合は T1 の 5 面の範囲外。
- イベント payload の形（`resultId`・`pitchEventKind`）は spike の独自形。製品の V7 スキーマ合意が必要。
- 保存直後の応答は、適用トランザクションが未確定の場合に備えて「読めた行＋今回受理された
  イベント」で畳み込む。確定後に読む `GET` と結果が一致することを実 DB で確認済み。
