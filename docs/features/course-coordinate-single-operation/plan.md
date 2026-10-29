---
feature: course-coordinate-single-operation
status: in-review         # ゲート前の起案。承認は 7.3 の確定ゲート + PO 承認で行う
承認: 未                  # PO 承認前。D11=A / D18=A の方針採用は済みだが、本計画の承認ではない
重さ分類: コア領域
worktree: ../../..
notion: なし
branch: feature/mvp-first-ball-vertical
created: 2026-10-30
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: タップ座標の量子化を単一 artifact operation として実装する（D11=A / D18=A）

## 1. 目的と現在地

初球 V7 の `observations.course` は正準整数 `k`（`unit:"1/263"`, 0..263）で保存する。
画面のタップは表示座標（float）を出すため、**入力形成時の量子化**（D11=A: 付録A-1 の四捨五入）と、
**クライアント・サーバーで同一の単一実装**（D18=A: 同一 JS artifact を両実行環境で実行）が必要である。

**現在地（実測）**
- artifact DSL に除算が無く、`k/263` は有限小数にならないため、artifact 内で保存用 binary64 は作れない。
- 画面に tap→k の変換関数は無い。backend は正準整数 k のみ受理し、float からの変換をしない
  （`backend/src/pitchlog/sync/first_ball_payload.py`）。
- Python の `k/263` は**候補**（正式採用ではない）。製品経路からは除去済みで、`tests/first_ball_course_oracle.py` は検査専用。
- **ゲート前は「契約ベクタ・独立導出・Python 試験・計画起案」まで**（D18=A の採用記録）。画面の暫定実装は出さない。

## 2. 設計

### 2.1 単一 operation の ABI（案）

```
quantizeCourse({
  tapX: "<十進文字列>",        # 表示座標（入力形成時の実数）
  tapY: "<十進文字列>",
  view: "catcher" | "pitcher", # 捕手視点 / 投手後方視点
  batterSide: "right" | "left"
}) -> { unit: "1/263", x: "<k>", y: "<k>" }
```

- **規則**: 付録A-1 の四捨五入（half-up）で整数化し、**量子化後に**投手後方視点の左右反転を行う（D11=A）。
- **閉じた拒否**: 非十進・非有限・範囲外（0..263 を外れる）・未知の view/batterSide は fail-closed。
- **単一実装**: operation の本体は artifact の TS 正本に置き、生成 JS を**ブラウザとサーバーの両方**が実行する。
  Python 側はホスト経由で同一 artifact を呼び、同じ規則を再実装しない（NFR-018）。
- **V7 接続**: `observations.course` にこの出力をそのまま使う。V8 は artifact の
  `historyContext[0].difference` を使い、Python で再計算しない。V7 の組立（`first-ball-play-v1`）は
  backend の formatter と同一の閉値を生成できる単一の場所（artifact 拡張を第一候補）に置く。

### 2.2 ベクタと独立導出（ゲート前実施可）

- 全264点 × 視点2 × 打席2 の期待値（k）を、**契約ベクタ**として固定する。
- 境界: 131.5（half-up で 132）、0、263、263.4（拒否）、-0.5（拒否）、非十進、NaN/Inf。
- **独立導出**: 正本実装から期待値を自動生成しない。有理数（1/263）との差が正しい丸めの 1/2 ulp 以内であること、
  端点の厳密一致、量子化後の反転（左右・視点）を別実装の oracle で照合する。
- 既存の初球 payload ベクタ（`tests/fixtures/first_ball_payload_vectors_v1.json`）の course と一致させる。

### 2.3 pin / manifest

- artifact 再生成に伴い `frontend/public/domain/pitchlog-domain.json` の SHA、`first_ball_payload_vectors_v1.json` の
  `artifactSha256`（102箇所）、計画・ADR の SHA 記述を同一段で更新する。
- manifest に operation を登録し、directTargets / 入口（ブラウザ・サーバー）の検査対象に含める。

## 3. ステップ

| # | 内容 | 受入 |
|---|---|---|
| 1 | 契約ベクタ（264×2×2）と独立 oracle の作成。Python 試験で境界・負例を固定 | 全点一致・負例拒否・製品コードに変換を追加していない |
| 2 | artifact に量子化 primitive と `quantizeCourse` を追加し、再生成・pin 更新・manifest 登録 | artifact の同一 JS をブラウザ/サーバーで実行し全点一致。SHA 宣言一致 |
| 3 | **7.3 確定ゲート**: ADR-003 v0.10（D-14-m の対象に座標変換1件を追加）＋要件 v2.18（D11/B-7 追記）を単一ゲートで敵対レビューし、PO 承認 | P0/P1 全件処理・PO 承認・対象版記録 |
| 4 | 画面接続（U3）: wrapper 経由で tap→k を呼び、V7/V8 と D5/D2・queue/ACK を接続。`PITCH_COMMIT_BLOCKED` 解除 | 実ブラウザでボール1球→ACK受理→実PG1行 |
| 5 | 再読込（U4 完成）: recorded の `after` を自動復元（端末が開始した記録がある場合） | reload 後に 1ボール・0ストライク・履歴1・得点/アウト/走者不変 |

## 4. 受入条件

- 全264点で artifact の出力が独立 oracle と一致し、ブラウザ/サーバーの実行結果が同一である。
- 画面のタップから `course {unit:"1/263", x, y}` が作られ、保存 PlayRow の `course_x/course_y` が
  既存の単一写像（k→Double）と一致する。
- 負例（範囲外・非十進・未知 view）が成功経路へ漏れない。
- ゲート前のコードに画面側の暫定変換が存在しない。

## 5. 未決・リスク

- **J2**（3層検査をマージ前必須にするか）は未回答。必須なら本単位は L になり、ゲートで裁定を受ける。
- ADR-003 v0.10 の改訂範囲は **D-14-m の対象追加と座標変換1件に限定**する（他対象の方式切替を含めない）。
- 既存の `COURSE_COORDINATE_SIZE` 契約テスト（`course-coordinate-contract`）とは別単位。本計画は量子化の単一実装を扱う。
- ゲート通過までは U3 の画面コードを書かない（fail-closed）。U1/U2/U4/U5 は本ゲートと独立に進められる。
