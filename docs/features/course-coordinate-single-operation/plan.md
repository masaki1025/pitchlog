---
feature: course-coordinate-single-operation
status: active
承認: PO委任によるCodex主担当判断（2026-10-30、bee806b1＋本確定記録、非作者coordinate_gate_reviewの最終差分P0/P1=0）
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
- **事実の是正（非作者レビュー P0-2）**: Python の `k/263`（`sync/first_ball_course.py`）は製品経路に**残っている**
  （`sync/first_ball_execution.py` の投影と `repositories/recorded_snapshot.py` の照合）。「除去済み」ではない。
  これは**別の候補**であり、本計画の受入で「既存の単一写像」として無条件に正解扱いしない。k→Double の符号化を
  正式採用するかは、D18 の単一実装の範囲（入力形成のみ／変換契約全体）と合わせて本ゲートで裁定する。
- **ゲート前は「契約ベクタ・独立導出・Python 試験・計画起案」まで**（D18=A の採用記録）。**artifact の改変・再生成・
  pin 更新はゲート後**に行う（初版のステップ順は非作者レビュー P0-1 で否決）。画面の暫定実装は出さない。

## 2. 設計

### 2.0 契約との関係（非作者レビュー P0-3/P0-4）

**既存の座標変換契約を再利用する。** `contracts/display-geometry/coordinate_transform_contract_v1.json`
（`calculation:"coordinate-transform"`、42ケース、D-6 の「1契約=1対象計算=1ファイル」）が B-7 の
**画面⇄保存**（`x_norm=x_screen/263`、`y_norm=(263−y_screen)/263`、保存→画面は付録A-1の丸め、往復・内外角・
クランプ点）を既に定義している。**同じ計算（`coordinate-transform`）の2本目のベクタは作らない。** 入力形成の量子化は**別の計算**（`course-input-quantization`）として別契約に宣言し、既存42ケースは変更しない。

**二段階の境界を明示する（B-7 の改訂ではない）**
1. **入力形成（D11=A）**: タップの float を付録A-1 の half-up で**整数の画面座標**へ量子化し、
   量子化後に投手後方視点の左右反転を行う。B-7 はこの**整数だけ**を受ける（B-7 `:1321`「画面→保存では
   丸めを行わない」は変換自体の規定であり、入力形成の量子化を禁止しない）。
2. **画面⇄保存（B-7/D-6）**: 量子化済み整数に既存契約の変換を適用する。**丸めは保存→画面だけ**。
**したがって B-7 の意味変更は無い**（D11=A は入力形成の規定）。計画が (a)/(b) で迷う余地を残さず、
本計画の operation は 1（入力形成）を計算し、**内部で 2（既存B-7契約の変換）を消費**して保存正準整数を返す。B-7 の別実装・2本目のベクタは作らず、`courseScreenXToStoredX` は削除する。

**受入の比較面**: 保存 PlayRow の `course_x/course_y` は、**既存契約の画面→保存変換**（整数→`k/263`）で
照合する。`sync/first_ball_course.py` の Python `k/263` は**候補**であり、受入の正解として無条件に使わない。
正式採用の可否は本ゲートで裁定する（採用しない場合は既存契約の単一実装へ置き換える）。

### 2.1 単一 operation の ABI（案）

実ホストはJSON文字列in/outとし、成功は `{ok:true,value:{unit,x,y}}`、失敗は `{ok:false,error:{code}}`（revision-draft参照）。下記は封筒内の値型。

```
quantizeCourse({
  x: "<十進文字列>",        # 表示座標（入力形成時の実数）
  y: "<十進文字列>",
  view: "catcher" | "pitcher", # 捕手視点 / 投手後方視点
  size: "<十進文字列>"          # contracts/display_geometry_263_v1.json の size（263 を焼き込まない）
}) -> { unit: "1/<size>", x: "<k>", y: "<k>" }
```

- **規則**: 付録A-1 の四捨五入（half-up）で整数化し、**量子化後に**投手後方視点の左右反転を行う（D11=A）。
- **y 軸（非作者レビュー P1）**: B-2/B-7 は上向き座標（保存は `263 − y`）。現行 `StrikeZone.vue` は素通しで、
  受入だけでは検出できない。ABI に y の向きと `263 − y` の適用点を明記し、ベクタで固定する。
- **十進文法と丸め**: 浮動小数の `number` は使わない（D-14-e 3）。入力を十進文字列として `BigInt` の
  スケール付き整数へ変換し、`q=|n|/|d|`・`r=|n|%|d|`・`2r ≥ |d|` で切り上げる。`131.5→132`、`-0.5→-1`、
  `263.4` は量子化前に拒否。`Math.round(-0.5)=-0` の罠を避ける。
- **範囲方針**: 表示側で既存B-7に従い `[0,size]` にクランプした画面座標を渡す。operation は量子化前の厳密値が同範囲内かを判定し、範囲外は拒否する。クランプと拒否は別の境界である。
- **263 の出所**: `contracts/display_geometry_263_v1.json` の `size` を単一の出所とし、`unit:"1/<size>"` を契約から導出し、263 を
  焼き込まない（I-17 の二重管理を再生産しない）。
- **反転と既存実装**: 既存の float 反転 `courseScreenXToStoredX` の扱い（置換か温存か）と、NFR-018 の逐語移植例外
  との関係を明記する。
- **単一実装**: operation の本体は artifact の TS 正本に置き、生成 JS を**ブラウザとサーバーの両方**が実行する。
  Python 側はホスト経由で同一 artifact を呼び、同じ規則を再実装しない（NFR-018）。
- **V7 接続**: `observations.course` にこの出力をそのまま使う。V8 は artifact の
  `historyContext[0].difference` を使い、Python で再計算しない。**V7 組立（`first-ball-play-v1`）の置き場は未決**で、
  本計画の受入に含める前にゲートで確定する（backend formatter と同一閉値の単一の場所）。
- **確定操作の前提**: `PITCH_COMMIT_BLOCKED` の解除は、排他の保持単位（D02）・U-X1 凍結・D5/D2/queue/ACK の
  境界が満たされた後にだけ行う（本計画は座標の供給だけを扱う）。

### 2.2 ベクタと独立導出（ゲート前実施可）

- 全264点 × 視点2 × 打席2 の期待値（k）を、**契約ベクタ**として固定する。
- 境界: 131.5（half-up で 132）、0、263、263.4（拒否）、-0.5（拒否）、非十進、NaN/Inf。
- **独立導出**: 正本実装から期待値を自動生成しない。有理数（1/263）との差が正しい丸めの 1/2 ulp 以内であること、
  端点の厳密一致、量子化後の反転（左右・視点）を別実装の oracle で照合する。
- 既存の初球 payload ベクタ（`tests/fixtures/first_ball_payload_vectors_v1.json`）の course と一致させる。
- **3層**: direct vectors に加え、properties（単調・範囲・反転の不変条件）と mutation（丸め・反転・範囲の変異）を
  descriptor 付きで用意する。J2 は ADR-003 で既に必須（未回答の裁定は「必須か」ではなく運用条件）。
- **manifest/directTargets**: `backend/domain/manifest.json` の不在を前提にせず、現行の manifest 配置と
  両 runner・独立収集器・5判定の具体を計画に書く。

### 2.3 pin / manifest

- artifact 再生成に伴い `frontend/public/domain/pitchlog-domain.json` の SHA、`first_ball_payload_vectors_v1.json` の
  `artifactSha256`（102箇所）、計画・ADR の SHA 記述を同一段で更新する。
- manifest に operation を登録し、directTargets / 入口（ブラウザ・サーバー）の検査対象に含める。

## 3. ステップ

| # | 内容 | 受入 |
|---|---|---|
| 1 | 既存 `coordinate_transform_contract_v1.json` の42ケースは**不変**。入力形成の量子化は**別計算 `course-input-quantization`** として別契約にケース（最短往復表現・指数・境界・範囲外・量子化後の反転）を宣言し、独立 oracle と properties/mutation の descriptor を追加（ゲート前）。**同じ計算の重複ファイルは作らない** | 既存42ケース不変・別計算の宣言・負例拒否・製品コード/artifact を変更していない |
| 2 | **7.3 確定ゲート**: ADR-003 v0.10（D-14-m の対象追加は「追記」でなく T1/T2 限定文の書き換えを含む）＋要件 v2.18（D11/B-7/NFR-018 の例外表）＋B-3（丸めを伴わない線形写像）への影響を単一ゲートで敵対レビューし、PO 承認 | P0/P1 全件処理・PO 承認・対象版記録 |
| 3 | **ゲート後**: artifact に量子化 primitive と `quantizeCourse` を追加し、再生成・pin 更新・manifest/directTargets 登録 | 同一 JS をブラウザ/サーバーで実行し全点一致。SHA 宣言一致 |
| 4 | 画面接続（U3）: wrapper 経由で tap→k を呼び、V7/V8 と D5/D2・queue/ACK を接続。封鎖解除は前提成立後 | 実ブラウザでボール1球→ACK受理→実PG1行 |
| 5 | 再読込（U4 完成）: recorded の `after` を自動復元（端末が開始した記録がある場合） | reload 後に 1ボール・0ストライク・履歴1・得点/アウト/走者不変 |

## 4. 受入条件

- 全264点で artifact の出力が独立 oracle と一致し、ブラウザ/サーバーの実行結果が同一である。
- 画面のタップから `course {unit:"1/263", x, y}` が作られ、保存 PlayRow の `course_x/course_y` が
  **既存の座標変換契約（画面→保存）**と一致する。Python `k/263` は候補であり、正解として固定しない。
- 負例（範囲外・非十進・未知 view）が成功経路へ漏れない。
- ゲート前のコードに画面側の暫定変換が存在しない。

## 5. ゲート対象正本（列挙）

- ADR-003 v0.10: D-14-m の対象追加（T1/T2 限定文の**書き換え**を含む）と、入力形成の量子化を D-2 の対象計算に含めるか。
- 要件 v2.18: D11=A の入力形成（付録A-1 の half-up・量子化後の反転）と、B-7 との二段階境界の注記。
- **既存の座標変換契約 `coordinate_transform_contract_v1.json` と D-6/D-8/D-11**: 量子化ケースの追加が
  「1契約=1対象計算=1ファイル」を保つこと。NFR-019(a) の比較面（一部だけ採らない）。
- **NFR-018 (c) の逐語移植例外**: 既存 float 反転 `courseScreenXToStoredX` の扱い（削除）を削除する。例外表の既存行は `COURSE_COORDINATE_SIZE` のみであり本ゲートでは不変。
- **B-3**（丸めを伴わない線形写像）への影響の有無。
- J2（3層検査のマージ前必須）の運用条件（ADR で既に必須であることの確認）。

## 6. 未決・リスク

- **J2**: 既存ADRが3層検査をマージ前必須としており、本単位も維持する。追加のPO意味判断を要しない（PO委任による実装判断）。
- ADR-003 v0.10 の改訂範囲は **D-14-m の対象追加と座標変換1件に限定**する（他対象の方式切替を含めない）。
- 既存の `COURSE_COORDINATE_SIZE` 契約テスト（`course-coordinate-contract`）とは別単位。本計画は量子化の単一実装を扱う。
- ゲート通過までは U3 の画面コードを書かない（fail-closed）。U1/U2/U4/U5 は本ゲートと独立に進められる。

## 7. 限定ゲートの確定記録（2026-10-30）

PO委任によるCodex主担当判断。REPORT〜REPORT7の既履歴を維持し、今回の差分確認・再確認は射程不変の限定追加レビューとして採用。対象は32dccc90とbee806b1までのADR v0.10/要件v2.18改訂・本計画・対応表・草案・量子化候補契約。非作者coordinate_gate_reviewがP0/P1=0と対象別着手前基盤の存在を確認。PO本人の逐行確認・署名ではない。

既存schema・runner・収集器・host基盤と契約1093件/descriptorの供給を着手条件として確認し、step3製品実装を許可する。実manifest entry・operation source/artifact/pin・両runner実行・properties/mutation/収集器登録/必須CIは同一変更のマージ前条件として残す。Python k/263の正式採用、正式7.7受理、画面初球・MVP完成をこの承認に含めない。

### Step3の編集パス具体化（PO委任Codex判断、2026-10-30）

既承認のoperation/manifest/両runner/実host接続を次へ具体化（射程追加なし）: `frontend/src/domain/courseQuantization.ts` と同spec、`publicApi.ts`、配布JS/宣言と既pin、`backend/domain/manifest.json`、`backend/domain/course-quantization-property-catalog.json` と同schema、`backend/src/pitchlog/domainrt/course_quantization.py`、`backend/tests/domain/test_course_quantization_manifest.py`・`test_course_quantization_host.py`。既synthetic schema・T1/T2 handoff・拒否検査は変更しない。manifest識別値は最終artifact生成後に直列更新する。

画面接続の具体対象は `frontend/src/components/zone/StrikeZone.vue` と同spec、`frontend/src/lib/courseInputView.ts`。float入力反転を削除しscreen座標をemit、量子化後の反転はartifactに一本化する。既保存→画面の表示変換は削除しない。

画面座標の意味追随として `frontend/src/screens/GameScreen.spec.ts` の投手視点タップ期待値を保存反転値183から実画面値80へ追随する。計算結果ではなくemit/下書き境界の期待値であり、保存整数の左右反転はartifact契約で独立検証する。

step3の公開操作集合追随: `frontend/src/domain/publicApi.spec.ts`・`firstPitchContinuationArtifact.spec.ts` のexact集合に承認済quantizeCourseのみ追加し、既5操作を保持する。部分一致に緩めない。

### Step3のBOOT対象binding具体化候補（2026-10-30、委任承認前）

実CIの`boot.report`はmanifestの計算識別値を正本対象のstable IDと同一視し、既承認`course-input-quantization`を未知対象として拒否した。operation/契約/descriptorの識別値を維持し、`nfr018-alpha-02`（入力と表示のための座標変換）への**部分供給**を1件だけ閉登録する。D18=A/ADR-003 v0.10の実装具体化であり、新たな野球意味・対象集合・全体完成条件を追加しない。本追補は非作者確認・主担当のPO委任承認後にsource着手する。

候補資産は`backend/domain/boot-operation-bindings.json`と同`.schema.json`、対向ケースは`backend/tests/domain/fixtures/boot_coordinate_binding_cases_v1.json`。schemaは1件のoperation/target/source/coverage=partial/根拠をconstで閉じ、未知operationへ任意targetを付けても拒否する。既manifest schema・既13対象・boot封印・契約1093件/既42件・artifact/pinは変更しない。

承認後のsource最小編集集合は新規`backend/src/pitchlog/domaincheck/boot/operation_bindings.py`、既`snapshot.py`・`report.py`、新規`tests/domain/boot/test_operation_bindings.py`および既`test_snapshot.py`・`test_report.py`の必要回帰のみ。専用loaderで閉schemaと対応の規範対象実在を検証し、既`InputAssetCollector`でbinding/schemaのdigestを証跡化。before/afterとも同じ固定対応を用い、過去manifest blobを変更しない。旧stable IDの登録は従来通り、未知operation/target拒否は保持する。

部分operationについても既source/生成物/入口/direct adapter/3層登録先の全実在検査を通す。六集合への写像ではoperationの3層成功をtarget全体の3層成功へ昇格させず、verified_checks供給時も当該targetを全体成功集合へ加えない。未供給なら既Noneを維持する。他対象の実測結果は変えない。部分登録があるtargetについてstable IDの別行を追加して完全化したと偽る混在も閉拒否し、全体完成への移行は別変更とする。

合否: 実manifestのreport生成/再検査と既snapshot/phase2回帰を通す。全layer成功でも当該targetのresolutionは空、既封印要素は未解消のまま。binding欠落・重複・target差替え・partial→complete偽装・実在欠落・不正schemaを拒否する。CI greenは従来通り移行要件のみで、NFR-018/019全体成立を主張しない。

PO委任によるCodex主担当判断（2026-10-30）: 上記binding候補4pathを全SHA照合し、非作者REPORTdd87b3423ed48ba0affd35bcd74cd650a0acc3a77b83f5f9a52007f1d883808d（P0/P1/P2=0、10変異拒否）を採用してstep3の有限登録是正へ進む。15対向の実source実行・report成功は未実施であり、本受理だけで成立としない。
