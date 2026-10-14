---
feature: field-region-vectors
type: design
date: 2026-10-11
---

# 詳細設計: 領域シードと座標系ベクタ — 座標系・多角形・ケースの選び方・独立確認

[実装計画書](./plan.md) 4 節のステップ 1 の成果物。典拠の詳細は [research.md](./research.md)。

**本書が決めるのは「どう作るか」であって「正解は何か」ではない。** 内外角の境界は[計画書 前提 B](./plan.md) のとおり**要件書 付録B-3 の改訂(ステップ 2)で条文として定める**。本書はその条文を受け取る形だけを用意する。

## 1. 座標系の対応表

**3 つの系が登場する。混同すると正解が静かに壊れる。**

| 系 | 定義 | 原点 | 向き | 値域 | 典拠 |
| --- | --- | --- | --- | --- | --- |
| **保存座標** | 0〜1 に正規化した実数ペア `(x, y)`。**捕手視点の物理座標** | **左下** | x = 捕手から見て右 / y = 上 | `[0, 1]` | 要件書 `:1286`・`:1287` |
| **画面座標** | 263 スケール | **左上** | x = 右 / y = **下** | `[0, 263]` | `contracts/display_geometry_263_v1.json`(`origin: top_left`)/ `courseInputView.ts:4` |
| **旧 263 系**(移行元) | 画面座標と同じ 263・左上原点 | 左上 | 同上 | `[0, 263]` | 付録B-5 `:1290` |

**(α) の射程は「画面座標 ⇄ 保存座標の相互変換」**(要件書 `:932`)。

**移行の変換式**(付録B-5 `:1290` — **旧 263 系 → 保存座標**。算術は画面座標にも共通):

```
x_norm = x_old / 263
y_norm = (263 - y_old) / 263      # 旧 Y 軸は下向きのため反転
```

### 1-1. 呼称のずれ(本タスクでは直さない)

**`frontend/src/lib/courseInputView.ts` は 263・左上原点を「保存座標」と呼んでいる。** DB の表現(`course_x`/`course_y` が `Double` で CHECK `BETWEEN 0 AND 1`)とは別物である。**B-3/B-4 の変換は未実装**([research.md 7 節](./research.md))。

**本書とベクタは要件書 `:1286`・`:1287` の定義に従う。** 実装の呼称は本タスクで変更しない(要件書 `:965` の現状維持)。**申し送り事項**([計画書 5 節](./plan.md))。

### 1-2. 数値表現と丸め — **ADR-003 が既に定めている**

**当初この節は「量子化と丸めをステップ 2 の条文で定める」としていたが、誤りだった。** `ADR-003`(approved)の **D-14-e**(`:628-640`)が既に両方を定めている。**本タスクが新しく定めるものではない。**

**型領域**(`:630-634` 逐語):

> 本書の型領域(`NumericValue` = **整数・decimal・有理数〔分子/分母〕**とそれらの nullable)
> `NumericValue` は **BigInt** で表す(**decimal = スケール付き整数 / 有理数 = 分子・分母の整数対**)

**`1/263` は 10 の冪では表せないので、座標には有理数(分子・分母)を使う。** `263` は 10 の冪ではないため decimal では厳密にならない。

**丸め**(`:637-640` 逐語):

> **要件書 付録A-1 が定める「四捨五入・負の中間値は絶対値で丸めて符号を戻す」**を、被除数と除数の整数対に対する剰余の比較として書く。**浮動小数の乗除を経由しない。**
> `q = |n| / |d|`(切り捨て)・`r = |n| % |d|` とし、**`2r ≥ |d|` のとき `q + 1`**、そうでなければ `q`。
> **「除数の半分」と比較してはならない**(確定ゲート 2 周目 P1 — **奇数の除数で誤る**)

**付録B-7 は丸めを定義してはならない。** 要件書 付録A-1 と ADR-003 D-14-e を**参照するだけ**にする(定義を書くと二重管理になり、しかも A-1 は四捨五入、当初の草案は偶数丸めで**別物だった**)。

**往復の定義**: 画面座標(整数 `0..263`)→ 保存座標(有理数 `k/263`)→ 画面座標(整数)。**有理数のまま保持すれば往復は恒等**であり、丸めが要るのは保存 → 画面の 1 方向だけ。

### 1-3. schema の是正(ステップ 1 の是正・2026-10-14)

ステップ 1 で作った schema は座標を `{value, scale}`(decimal のみ)としており、**ADR-003 の型領域より狭く、`k/263` を書けなかった**。**`numericValue` を 3 形の `oneOf`(整数 / decimal / 有理数)へ広げた。** 分母 0 は reject する。

**丸め規則は schema に書かない**(参照のみ)。採用する形は各契約の条文が決める。

## 2. 多角形の定義方針(付録B-6 領域シード)

### 2-1. 旧システムは多角形を持っていない

固定コミット `dd03160:frontend/src/lib/fielder.ts` の実測(全 37 行):

**矩形ルール 4 本を上から順に評価する**(1 つでも当たればそこで決まる):

| 順 | 条件 | 守備位置 |
| --- | --- | --- |
| 1 | `y >= 205` | 2(捕手) |
| 2 | `x >= 155 && y >= 165` | 3(一塁手) |
| 3 | `x <= 75 && y >= 165` | 5(三塁手) |
| 4 | `x >= 105 && x < 145 && y >= 140 && y <= 190` | 1(投手) |

**残りは 9 アンカーへの最近傍**(ユークリッド距離の二乗で比較):

| 守備位置 | x | y |
| --- | --- | --- |
| 8 | 116.0 | 66.0 |
| 7 | 56.0 | 101.0 |
| 9 | 174.0 | 101.0 |
| 6 | 88.0 | 144.0 |
| 4 | 152.0 | 144.0 |
| 5 | 66.0 | 174.0 |
| 3 | 166.0 | 174.0 |
| 1 | 123.0 | 164.0 |
| 2 | 123.0 | 232.0 |

**タイブレーク**: 比較が厳密 `<` なので、距離が同じなら**上表の先頭側が勝つ**。
**センチネル**: `x <= 0 || y <= 0` と非有限値は `null` を返す。

**座標は旧 263 系(左上原点)である。**

### 2-2'. 当初「新規設計」としたのは誤り — **旧の規則を多角形として厳密に表す**(2026-10-14 の是正)

本節は当初「旧の規則(矩形 + 最近傍)とは形が違うので新規設計になる」としていたが、**2 つの理由で誤りだった**。

**理由 1: 逐語移植の裁定が効く。** PO 裁定(2026-08-16)は旧 SPA を「**完全に同じもの**」として移植すると定め、改善台帳 `I-28` はその限定を「**要件書・改善台帳が改善を既決にした箇所、および実体のない機能を除く**」(`:240`)とする。**捕球選手推定の領域はどちらの限定にも当たらない** — 要件書は領域の形を定めておらず(`:1291` は「座標多角形のシードデータとして収載する」という**形式**の要求)、実体のない機能でもない。**したがって旧の挙動を再現するのが既定である。**

**理由 2: B-6 のタイブレーク規則が、旧の評価順をそのまま表現できる。** `:1291` は「境界線上の点の帰属は**先に定義された領域が優先**」と定める。旧は**矩形ルール 4 本を上から順に評価し、当たらなければ最近傍**という**順序つきの規則**である。**順序つきの領域列として書けば、意味が一致する。**

#### 採る形 — 順序つき 13 領域

| 順 | 領域 | 守備位置 | 由来 |
| --- | --- | --- | --- |
| 1 | 捕手の矩形 | 2 | 旧 `y >= 205` |
| 2 | 一塁手の矩形 | 3 | 旧 `x >= 155 && y >= 165` |
| 3 | 三塁手の矩形 | 5 | 旧 `x <= 75 && y >= 165` |
| 4 | 投手の矩形 | 1 | 旧 `105 <= x < 145 && 140 <= y <= 190` |
| 5〜13 | 9 アンカーの**ボロノイ領域** | 8 / 7 / 9 / 6 / 4 / 5 / 3 / 1 / 2 | 旧のアンカー列の順(**距離が同じとき先頭側が勝つ**という旧の厳密 `<` と一致する) |

**1 つの守備位置が複数の領域を持つ**(例: 守備位置 2 は矩形とボロノイ領域の両方)。B-6 は「1 領域 = 1 守備位置」を要求しておらず、**領域 → 守備位置の写像**であればよい。

**ボロノイ領域は厳密に計算する。** 2 アンカー間の垂直二等分線は整数座標から**有理係数**で定まり、交点も有理数になる。**1-2 の型領域(有理数 = 分子・分母の整数対)で厳密に書ける**ので、浮動小数を経由しない。

**フィールドの外周でクリップする。** 外周は `contracts/display_geometry_263_v1.json` の `field`(home・first・second・third・`fence_radius 180`)から取る。**円弧は多角形で表せない**ので、**フェンスは十分細かい折れ線で近似し、その分割数を schema に記録する**(近似であることを明示する)。

#### この形が満たすもの

- **旧との一致が構成上保証される**(近似ではなく、同じ規則を別の表現で書いたもの)
- **2-3 の照合が「大きく外れていないことの確認」ではなく、厳密な一致検査になる** — ずれるのはフェンス近似の外周だけ
- **タイブレークが旧の評価順と一致する**(矩形が先・アンカー列の順)

#### PO 判断と実装結果(2026-10-14・山田正輝)

**裁定: 旧と厳密に一致させる(案 A)。**

| 論点 | 裁定 | 実装 |
| --- | --- | --- |
| 旧の `x < 145`(投手の矩形の右辺だけが開いている) | **辺ごとの開閉を schema に持たせて厳密に表す** | `openEdges`(開いた辺の 0 始まりの番号・列挙しない辺は閉じる)。投手の矩形は `openEdges: [2]` |
| フェンスでのクリップ | **やめる**(①の帰結 — 旧に外周の境界が無く、フェンス外は最近傍へ吸われる) | **単位正方形 `[0,1] × [0,1]` でクリップ**。**円弧の折れ線近似が丸ごと不要になり、近似誤差が消えた** |

**裁定の根拠**: `I-28:241` が「移植時に該当するか**判断が割れる場合は実装計画書ゲートで PO へ判断を上げる**——**挙動優先の例外を現場判断で作らない**」と定める。閉じた多角形にして差分を記録する案は**現場判断の例外**にあたる。

#### 検証結果 — 旧 263 格子の全点で一致

**照合した点 69,169 / 不一致 0。** 委任先の報告とは独立に、委任元が旧ルールを書き直して突合した(`openEdges` を解釈する内外判定を自前で実装)。

- 投手の矩形の開いた辺が効いていること(旧 `(145,150)` → 守備位置 **4**)を含めて一致
- **フェンス近似の頂点は 1 つも残っていない**
- 頂点数: `4 / 4 / 4 / 4 / 5 / 5 / 5 / 5 / 5 / 6 / 6 / 5 / 4`

#### 残る未定(申し送り)

- **センチネル**(旧の `x<=0 || y<=0` → `null`)は**そのまま移せない** —— 旧 263 系では `0` が「未入力」の印だったが、**保存座標では `0` が有効な座標**(原点・左端・下端)になる。上記の全点照合でもセンチネルの点は照合対象から外している。**未入力をどう表すかは要件に記載が無く、PO 判断**
- **旧 263 系の外側**(例 `(264, 205)`)は**保存座標 `[0,1]` の外**なので、そもそも表現できない。旧では最近傍へ吸われていたが、**定義域の外であり差分ではない**

### 2-2. ~~したがって多角形は新規設計になる~~(2-2' で是正)

付録B-6(`:1291`)は「**座標多角形**のシードデータ」を要求する。**旧の規則(矩形 + 最近傍)とは形が違う**ので、旧から多角形を機械的に導出することはできない。

**方針**:

1. **多角形は保存座標系(0〜1・左下原点)で定義する** — シードは製品の正本であり、旧 263 系を引きずらない
2. **各守備位置に 1 つの多角形**。頂点は固定小数点整数(1-2 と同じ様式)
3. **タイブレーク規則は付録B-6 の条文どおり「先に定義された領域が優先」** — したがって**シードの配列順そのものが規則の一部**であり、順序を変えると帰属が変わる。schema に順序依存であることを明記する
4. **共有境界は「重なり」として扱わない。禁じるのは内部の重複**(`:1291` が境界線上の帰属を定めているため)
5. **どの領域にも属さない点(ファウル域・フェンス外)の扱いは要件にも ADR にも無い** — [計画書 5 節](./plan.md)の申し送り。**シードでは「属さない」を表現できる形にしておく**(全域を覆う多角形を無理に作らない)

### 2-3. 旧実装との照合(ステップ 4 で行う)

**多角形から導かれる帰属が、旧の規則と同じ入力で同じ守備位置になるか**を全ケースで照合し、**一致・不一致の双方を本書へ記録する**。

- **一致を要求しない** — 旧は多角形を持たず、pitchlog は要件書が多角形を要求している。**形が違う以上、ずれる点が出て当然**
- **不一致が出たら理由を書く**(例: 矩形ルールの角が多角形では別領域に入る)
- **照合は oracle ではない** — 旧の規則を期待値の出所にはしない(2-1 の座標系も違う)。**「大きく外れていないこと」の確認**である

### 2-4. 打球方向の区分角 —— **レイで持つ**(PO 判断 2026-10-14・山田正輝)

付録A-3(`:1212`)は「左翼線〜右翼線を**等角 5 分割**(レフト / 左中間 / センター / 右中間 / ライト)」とし、「**区分角はB-6の領域シードで定義**」とする。

#### 等角 5 分割は有理数で厳密に書けない

本塁 `(123, 39)`・一塁 `(170, 92)`・三塁 `(76, 92)`(いずれも保存座標の単位 `1/263` の整数)から、**右翼線 = `(47, 53)`・左翼線 = `(−47, 53)`**。挟角は `2·atan(53/47)` ≒ **83.132739 度**で、**5 等分した角の正接は無理数になる**。

角度で持つと分類に `atan2` が要り、**浮動小数が入って ADR-003 の「暗黙の丸めを置かない」に反する**。

#### 採った方式 —— 境界を整数の方向ベクトル(レイ)で持つ

**要件書 `:1212` が「区分角は B-6 の領域シードで定義」と委ねているので、シードの値が定義になる。****等角 5 分割は導出の由来**として `source` に記録し、**実角との誤差は検査で上限を押さえる**。

| 区分 | `startRay` | `endRay` |
| --- | --- | --- |
| `batted-ball-direction.left` | (-47, 53) | (-93, 200) |
| `batted-ball-direction.left-center` | (-93, 200) | (-32, 219) |
| `batted-ball-direction.center` | (-32, 219) | (32, 219) |
| `batted-ball-direction.right-center` | (32, 219) | (93, 200) |
| `batted-ball-direction.right` | (93, 200) | (47, 53) |

**分類は外積の符号だけで行う** —— 点 `P` の本塁からの向き `v = P − home` について、`cross(startRay, v)` と `cross(endRay, v)` の符号で決める。**整数演算で厳密。**

**境界レイ上の点は「先に定義された側」が取る**(シードの `tieBreak` と同じ規律)。すなわち各区分は**自分の `endRay` を含み、`startRay` を含まない**。**左翼線そのものだけは最初の区分が含む。**

**等角との誤差(実測)**:

| 境界 | レイ | 実角(度) | 理想(度) | 誤差(度) |
| --- | --- | ---: | ---: | ---: |
| 1 | (−93, 200) | 114.938428 | 114.939822 | **0.00139413** |
| 2 | (−32, 219) | 98.313155 | 98.313274 | **0.00011859** |
| 3 | (32, 219) | 81.686845 | 81.686726 | **0.00011859** |
| 4 | (93, 200) | 65.061572 | 65.060178 | **0.00139413** |

**上限 `0.01` 度を `backend/tests/` の検査が押さえる。** **この検査でだけ浮動小数を使う** —— 契約の値ではなく、契約の値の妥当性を測る検査だからである。

**探索の制約**: 理想角に最も近い整数レイを `|p|, |q| <= 20000` で探すと、**約分後のレイが保存座標の格子内へ届かず、境界上のケースを置けない**。**本塁から進んで格子内に点が取れる範囲**で最小誤差のレイを選んだ。

#### ファウル域の扱い(本タスクで定めた)

**左翼線より外・右翼線より外の点**は、物理方向・打者相対とも **`foul-territory`**(表示名 **`ファウル地域`**)とする。**打者相対への畳み込みの対象外。**

**要件書に記載が無い。** 要件書 `:1212` は「**インプレー打球の**付録B座標から」と限っており、ファウル域の座標は入力として想定されていない。一方 `ADR-003:231` は入力範囲に**範囲外**を要求するので、**値を置かないとベクタが作れない**。**本契約の決定**として該当ケースの `provenance` に記録した。

**旧には等角 5 分割が存在しない**(旧は x だけの 3 分割)。**新規設計**である。

## 3. ケースの選び方(入力範囲)

`ADR-003:228-231` が入力範囲を定める。本書はそれを**どう具体化するか**を決める。

### 3-1. 捕球選手推定(`ADR-003:229`)

> 各守備位置の**内点** + **領域境界線上の点**(タイブレーク規則の検証)

- **内点**: 各多角形の内部から 1 点以上。**重心ではなく、角に寄った点も入れる**(重心だけだと矩形ルールの角のずれを検出できない)
- **境界線上の点**: **隣接する 2 領域の共有境界上**から取る。タイブレーク規則で**先に定義された側**へ帰属することを固定する
- **センチネル**: 旧は `x <= 0 || y <= 0` を `null` にする。**保存座標では 0 が有効な値になり得る**(左下原点の原点そのもの)。**センチネルの扱いは要件に記載が無い** — 申し送り(計画書 5 節)。本ベクタでは**センチネルのケースを置かない**(扱いが未定のものを固定しない)

### 3-2. 座標変換(`ADR-003:228`)

> **境界値**(ゾーン枠の端点・0・最大値)+ **等価分割**(内角/外角の各領域)+ **範囲外のクランプ点** × **打席左右の全値を必ず両方**

- **境界値**: `contracts/display_geometry_263_v1.json` の `strike_zone`(left 80 / right 183 / top 68 / bottom 180)の 4 辺の端点、画面座標の `0` と `263`
- **等価分割**: ステップ 2 の条文が定める内外角の各区間から 1 点ずつ
- **範囲外のクランプ点**: 画面座標の負値と `> 263`。**クランプ規則も条文が定める**(付録B-5 は移行側で `[0,1]` へクランプすると定めるが、(α) には規定が無い — 申し送り)
- **打席左右**: **全ケースを左右の両方で持つ**。片側だけだと**反転を未検査のまま「全件消費」と判定できる**(確定ゲート 23 周目)
- **往復**: 1-2 の定義で各ケースに往復の期待値を持たせる

### 3-3. 打球方向導出(`ADR-003:231`)

> **座標の境界値と等価分割**(付録B-6 の領域境界・領域内点・**範囲外**)× **打球種別の全列挙** × **打席左右の両方**

- **領域境界**: 等角 5 分割の区分角の境界線上
- **領域内点**: 5 区分それぞれの内部
- **範囲外**: 左翼線より外・右翼線より外(ファウル域)
- **打球種別**: `contracts/vocabulary/input_vocabulary_v1.json` の `batted-ball-type` 軸(ground / line / fly)の**全列挙**。**語彙 ID で参照し、参照整合を CI が検査する**(`ADR-003:351`)
- **打者相対の区分**: [計画書 前提 A](./plan.md) により **3 値**(引っ張り / センター返し / 流し)。物理 5 区分から打席左右で畳む(2:1:2)
- **表示名**: 各区分に**写像①を適用した表示名**も `expected` に持つ(`ADR-003:325`・v0.2)

## 4. `provenance` の様式(独立確認の記録)

`ADR-003:324` は「**期待値はシードから自動生成せず独立に確認する**」と定める。[計画レビュー 2 回目の P0](./plan.md) のとおり、**`provenance` は自己申告なのでそれだけでは証明にならない**。**3 点の連言**で担保する。

### 4-1. ケースごとの `provenance`(TSK-236 の先例に倣う)

`contracts/state-transition/state_transition_contract_v1.json:10-35` と同 schema `:611-623` の `provenance{subjectKind, sources[]}` を踏襲する。

| フィールド | 内容 |
| --- | --- |
| `subjectKind` | 期待値が何に由来するか(`clause` = 条文 / `legacy-pinned` = 旧の固定コミット / `geometry-contract` = `display_geometry_263_v1.json`) |
| `sources[]` | 出所の列挙。**各要素に `path` と、可能なら `line` または `blobSha`** |

**機械検査**: `sources[]` に**領域シードのパスが含まれないこと**。含まれていれば fail。

### 4-2. 契約の `independentVerifierId`

`ADR-003:334`(D-6 の CI 規則 3)の対象。`contracts/state-transition/state_transition_contract_v1.json:215` は現在 `"not-performed"`。

**本タスクの契約は `"not-performed"` 以外の値を持つ。** 値は**確認を実施した主体の識別子**。

### 4-3. 確認の記録(本書に書く)

**ケース ID と全件対応する表を本書の末尾に置く。** 各行に:

| 列 | 内容 |
| --- | --- |
| `caseId` | 契約の `cases[].caseId` と一致 |
| 確認者 | 期待値を書いた主体とは**別**の主体 |
| 方法 | どう確かめたか(条文からの手計算 / 幾何の別経路 / 旧規則との照合) |
| 結果 | 一致 / 不一致(不一致なら理由) |

**機械検査**: 本表の `caseId` 集合と、各契約の `cases[].caseId` 集合が**完全一致**すること。

> **この表はステップ 4〜6 で埋める。** ステップ 1 の時点では空の枠だけを置く。

## 4-4. schema の置き場(ステップ 1 の決定)

| schema | 置き場 | 従う契約 |
| --- | --- | --- |
| `field_geometry_vector_contract_schema_v1.json`(対象計算ベクタ契約) | `contracts/display-geometry/` | **3 契約が共有する** — 捕球選手推定(`contracts/field-regions/`)・座標変換(`contracts/display-geometry/`)・打球方向導出(`backend/` 配下) |
| `field_region_seed_schema_v1.json`(参照データ契約) | `contracts/field-regions/` | 付録B-6 領域シード 1 件 |

**対象計算ベクタ契約 schema は 1 本だけ置き、複製しない。** 3 契約が異なるディレクトリにあるため、どこに置いても 1 つはディレクトリをまたぐ参照になる。**複製すれば NFR-018 の「単一実装」の精神に反し、schema どうしの乖離が静かに起きる**ので、1 本にして参照させる。

D-12(`ADR-003:343`)が定めるのは**契約の実体**の置き場であって schema の置き場ではない(`contracts/state-transition/` では schema と契約が同居しているが、あちらは 1 対 1 である)。

### 数値リテラルの字句検査(schema では閉じられない)

**JSON Schema は数値リテラルの字面を保持しない** — parse 後は `-0` と `0`、`1.0` と `1` を区別できない。したがって「座標は固定小数点整数」を schema だけでは強制できない。

**`tests/test_field_geometry_numeric_lexemes.py` が生のテキストとして検査する** — 小数点・指数・`-0`・`NaN`・`Infinity` を reject する。負例は `tmp_path` の合成 JSON で判定し、実リポジトリの状態に依存しない。

**この検査は契約を守る検査なので、ステップ 8 の `AREA_PATH_ADDITIONS` の宣言対象に含める**(設計書 `:404-①` が「契約(ベクタ・スキーマ・**テスト**)を変え得るファイル」を求める)。

## 5. 確認の記録表(ステップ 4〜6 で埋める)

### 5-1. 捕球選手推定ベクタ

**契約**: `contracts/field-regions/fielder_estimation_contract_v1.json`(**31 ケース** — 内点 13 / 矩形境界 8 / 等距離 6 / 範囲の端 4)。

**確認者は期待値を書いた主体とは別である** —— 期待値は委任先(Codex)が旧ルールの記述から導出し、**委任元(Claude)が旧ルールを自前で書き直して全件を突合した**。**領域シードは期待値の導出にも確認にも使っていない**(シードは独立の第 3 経路として突合に加えた。6 節)。

| caseId | 確認者 | 方法 | 結果 |
| --- | --- | --- | --- |
| `interior-catcher-rectangle` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 2 = 旧規則 2 = 領域シード 2) |
| `interior-first-base-rectangle` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 3 = 旧規則 3 = 領域シード 3) |
| `interior-third-base-rectangle` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 5 = 旧規則 5 = 領域シード 5) |
| `interior-pitcher-rectangle` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 1 = 旧規則 1 = 領域シード 1) |
| `interior-anchor-8` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 8 = 旧規則 8 = 領域シード 8) |
| `interior-anchor-7` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 7 = 旧規則 7 = 領域シード 7) |
| `interior-anchor-9` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 9 = 旧規則 9 = 領域シード 9) |
| `interior-anchor-6` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 6 = 旧規則 6 = 領域シード 6) |
| `interior-anchor-4` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 4 = 旧規則 4 = 領域シード 4) |
| `interior-anchor-5` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 5 = 旧規則 5 = 領域シード 5) |
| `interior-anchor-3` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 3 = 旧規則 3 = 領域シード 3) |
| `interior-anchor-1` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 1 = 旧規則 1 = 領域シード 1) |
| `interior-anchor-2` | 委任元(Claude) | 旧規則の独立再実装で導出し、**8 近傍の格子点がすべて同じ守備位置になること**まで確認 | **一致**(ベクタ 2 = 旧規則 2 = 領域シード 2) |
| `rect-boundary-catcher-closed-y205` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 2 = 旧規則 2 = 領域シード 2) |
| `rect-boundary-first-closed-corner-155-165` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 3 = 旧規則 3 = 領域シード 3) |
| `rect-boundary-third-closed-corner-75-165` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 5 = 旧規則 5 = 領域シード 5) |
| `rect-boundary-pitcher-closed-left-x105` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 1 = 旧規則 1 = 領域シード 1) |
| `rect-boundary-pitcher-closed-top-y140` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 1 = 旧規則 1 = 領域シード 1) |
| `rect-boundary-pitcher-closed-bottom-y190` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 1 = 旧規則 1 = 領域シード 1) |
| `rect-boundary-pitcher-inside-right-x144` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 1 = 旧規則 1 = 領域シード 1) |
| `rect-boundary-pitcher-open-right-x145` | 委任元(Claude) | 旧規則の独立再実装で導出(矩形条件の境界に当たる点) | **一致**(ベクタ 4 = 旧規則 4 = 領域シード 4) |
| `equal-distance-anchor-8-vs-6-first-8` | 委任元(Claude) | 旧規則の独立再実装で導出し、**二乗距離が厳密に並び、アンカー順の先頭側が勝つこと**まで確認 | **一致**(ベクタ 8 = 旧規則 8 = 領域シード 8) |
| `equal-distance-anchor-8-vs-4-first-8` | 委任元(Claude) | 旧規則の独立再実装で導出し、**二乗距離が厳密に並び、アンカー順の先頭側が勝つこと**まで確認 | **一致**(ベクタ 8 = 旧規則 8 = 領域シード 8) |
| `equal-distance-anchor-6-vs-4-first-6` | 委任元(Claude) | 旧規則の独立再実装で導出し、**二乗距離が厳密に並び、アンカー順の先頭側が勝つこと**まで確認 | **一致**(ベクタ 6 = 旧規則 6 = 領域シード 6) |
| `equal-distance-anchor-6-vs-5-first-6` | 委任元(Claude) | 旧規則の独立再実装で導出し、**二乗距離が厳密に並び、アンカー順の先頭側が勝つこと**まで確認 | **一致**(ベクタ 6 = 旧規則 6 = 領域シード 6) |
| `equal-distance-anchor-4-vs-3-first-4` | 委任元(Claude) | 旧規則の独立再実装で導出し、**二乗距離が厳密に並び、アンカー順の先頭側が勝つこと**まで確認 | **一致**(ベクタ 4 = 旧規則 4 = 領域シード 4) |
| `equal-distance-anchor-1-vs-2-first-1` | 委任元(Claude) | 旧規則の独立再実装で導出し、**二乗距離が厳密に並び、アンカー順の先頭側が勝つこと**まで確認 | **一致**(ベクタ 1 = 旧規則 1 = 領域シード 1) |
| `range-edge-left-x0-valid` | 委任元(Claude) | 旧規則の独立再実装で導出(保存座標の値域の端) | **一致**(ベクタ 7 = 旧規則 7 = 領域シード 7) |
| `range-edge-top-y0-valid` | 委任元(Claude) | 旧規則の独立再実装で導出(保存座標の値域の端) | **一致**(ベクタ 8 = 旧規則 8 = 領域シード 8) |
| `range-edge-right-x263-valid` | 委任元(Claude) | 旧規則の独立再実装で導出(保存座標の値域の端) | **一致**(ベクタ 9 = 旧規則 9 = 領域シード 9) |
| `range-edge-bottom-y263-valid` | 委任元(Claude) | 旧規則の独立再実装で導出(保存座標の値域の端) | **一致**(ベクタ 2 = 旧規則 2 = 領域シード 2) |

**31 件すべて一致・不一致 0。**

### 5-2. 座標変換ベクタ

**契約**: `contracts/display-geometry/coordinate_transform_contract_v1.json`(**27 ケース** — 画面往復 8 / 正準往復 4 / 量子化 3 / クランプ 2 / 内外角 10)。

**確認者は期待値を書いた主体とは別である** —— 期待値は委任先(Codex)が条文から導出し、**委任元(Claude)が付録B-7 と付録B-3 だけを根拠に変換・丸め・クランプ・往復・決定表を自前で書き直して**全件を突合した。**どちらも浮動小数を経由していない**(丸めは剰余で `2r >= |d|`、内外角は `2k` と `263` の整数比較、`c` ちょうどは `Fraction` で厳密比較)。

| caseId | 確認者 | 方法 | 結果 |
| --- | --- | --- | --- |
| `screen-roundtrip-origin` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (0, 0)・— → (0, 263) / 戻り (0, 0)) |
| `screen-roundtrip-max-corner` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (263, 263)・— → (263, 0) / 戻り (263, 263)) |
| `screen-roundtrip-zone-top-left` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (80, 68)・— → (80, 195) / 戻り (80, 68)) |
| `screen-roundtrip-zone-top-right` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (183, 68)・— → (183, 195) / 戻り (183, 68)) |
| `screen-roundtrip-zone-bottom-left` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (80, 180)・— → (80, 83) / 戻り (80, 180)) |
| `screen-roundtrip-zone-bottom-right` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (183, 180)・— → (183, 83) / 戻り (183, 180)) |
| `screen-roundtrip-interior-upper` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (123, 100)・— → (123, 163) / 戻り (123, 100)) |
| `screen-roundtrip-interior-lower` | 委任元(Claude) | 条文(付録B-7)から変換と往復を書き直し、**画面 → 保存 → 画面が恒等**であることまで確認 | **一致**(画面 (130, 140)・— → (130, 123) / 戻り (130, 140)) |
| `canonical-roundtrip-origin` | 委任元(Claude) | 条文から書き直し、**正準表現の入力について保存 → 画面 → 保存が恒等**であることまで確認 | **一致**(保存(正準) (0, 0)・— → (0, 263) / 戻り (0, 0)) |
| `canonical-roundtrip-max-corner` | 委任元(Claude) | 条文から書き直し、**正準表現の入力について保存 → 画面 → 保存が恒等**であることまで確認 | **一致**(保存(正準) (263, 263)・— → (263, 0) / 戻り (263, 263)) |
| `canonical-roundtrip-quantized-half` | 委任元(Claude) | 条文から書き直し、**正準表現の入力について保存 → 画面 → 保存が恒等**であることまで確認 | **一致**(保存(正準) (132, 132)・— → (132, 131) / 戻り (132, 132)) |
| `canonical-roundtrip-zone-bottom-left` | 委任元(Claude) | 条文から書き直し、**正準表現の入力について保存 → 画面 → 保存が恒等**であることまで確認 | **一致**(保存(正準) (80, 83)・— → (80, 180) / 戻り (80, 83)) |
| `quantization-half-to-132-units` | 委任元(Claude) | 条文から書き直し、**最近傍の正準表現へ量子化されること**と**冪等であること**まで確認 | **一致**(保存(非正準) (1/2, 1/2)・— → (132, 132)) |
| `quantization-thirds-one-two` | 委任元(Claude) | 条文から書き直し、**最近傍の正準表現へ量子化されること**と**冪等であること**まで確認 | **一致**(保存(非正準) (1/3, 2/3)・— → (88, 175)) |
| `quantization-thirds-two-one` | 委任元(Claude) | 条文から書き直し、**最近傍の正準表現へ量子化されること**と**冪等であること**まで確認 | **一致**(保存(非正準) (2/3, 1/3)・— → (175, 88)) |
| `clamp-negative-x-above-max-y` | 委任元(Claude) | 条文から書き直し、**クランプを変換より先に行う**ことまで確認 | **一致**(画面 (-1, 264)・— → (0, 0)) |
| `clamp-above-max-x-negative-y` | 委任元(Claude) | 条文から書き直し、**クランプを変換より先に行う**ことまで確認 | **一致**(画面 (264, -1)・— → (263, 263)) |
| `inside-outside-grid-131-right` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (131, 131)・右打席 → `inside`) |
| `inside-outside-grid-132-right` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (132, 131)・右打席 → `outside`) |
| `inside-outside-grid-131-left` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (131, 131)・左打席 → `outside`) |
| `inside-outside-grid-132-left` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (132, 131)・左打席 → `inside`) |
| `inside-outside-exact-center-right` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(非正準) (1/2, 1/2)・右打席 → `outside`) |
| `inside-outside-exact-center-left` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(非正準) (1/2, 1/2)・左打席 → `outside`) |
| `inside-outside-end-0-right` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (0, 131)・右打席 → `inside`) |
| `inside-outside-end-263-right` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (263, 131)・右打席 → `outside`) |
| `inside-outside-end-0-left` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (0, 131)・左打席 → `outside`) |
| `inside-outside-end-263-left` | 委任元(Claude) | 条文(付録B-3 の決定表)から書き直し、**`c` をゾーン枠から保存座標系で導いて厳密比較** | **一致**(保存(正準) (263, 131)・左打席 → `inside`) |

**27 件すべて一致・不一致 0。**

#### `c` ちょうどの点は正準表現の格子上に存在しない

ゾーン枠は画面座標で `left = 80`・`right = 183` なので、**`c = (80 + 183) / 2 / 263 = 1/2`**。正準表現 `k/263` で `1/2` を表すには `k = 131.5` が要り、**整数ではない**。

したがって「**中心ちょうどは打席左右によらず外角**」(付録B-3)は、**正準表現の入力だけでは到達できない**。ケースを 2 つに分けた:

| 何を示すか | 座標系 | 入力 |
| --- | --- | --- |
| **境界が効いていること** | 正準表現 | `k = 131`(`2k = 262 < 263`)と `k = 132`(`2k = 264 > 263`)× 打席左右 |
| **中心ちょうどの帰属** | 非正準(有理数) | `1/2` × 打席左右 |

**付録B-3 の入力は保存座標の `x` であって、付録B-7 の正準表現に限られない**(移行由来の値も内外角の導出の入力になり得る)ので、非正準の `1/2` を入力に置くのは条文と整合する。

#### ベクタで検査できないこと(申し送り)

**「量子化は保存値を書き換えない」は、計算結果のベクタでは検査できない。**ベクタが固定できるのは**写像の出力**であって、**副作用が無いこと**ではない。

本契約は量子化の**結果**(`1/2` → `132/263`)と**冪等性**を固定しているが、**保存列が書き換わらないこと**は製品側の検査が担う。**ステップ 7(CI 配線)の射程外**であり、**実装単位(U-F2 系の入力画面)の DoD へ送る申し送り**とする。

### 5-3. 打球方向導出ベクタ

**契約**: `backend/domain/batted_ball_direction_contract_v1.json`(**66 ケース** — 内点 30 / 境界 24 / 範囲外 12)。

**確認者は期待値を書いた主体とは別である** —— 期待値は委任先(Codex)が条文から導出し、**委任元(Claude)が要件書 `:1212` と `ADR-003:327` だけを根拠に、等角 5 分割の判定と打者相対の畳み込みを自前で書き直して**全件を突合した。**分類は整数の外積だけで行い、浮動小数を経由していない。**

**打者相対は ID の綴りではなく表示名で突合した**(表示名の正は要件書 `:1212` の「引っ張り / 流し」と `ADR-003:327` の「センター返し」)。

| caseId | 確認者 | 方法 | 結果 |
| --- | --- | --- | --- |
| `interior-left-ground-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left → batter-relative.pull / レフト → 引っ張り) |
| `interior-left-ground-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left → batter-relative.opposite / レフト → 流し) |
| `interior-left-line-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left → batter-relative.pull / レフト → 引っ張り) |
| `interior-left-line-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left → batter-relative.opposite / レフト → 流し) |
| `interior-left-fly-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left → batter-relative.pull / レフト → 引っ張り) |
| `interior-left-fly-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left → batter-relative.opposite / レフト → 流し) |
| `interior-left-center-ground-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left-center → batter-relative.pull / 左中間 → 引っ張り) |
| `interior-left-center-ground-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left-center → batter-relative.opposite / 左中間 → 流し) |
| `interior-left-center-line-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left-center → batter-relative.pull / 左中間 → 引っ張り) |
| `interior-left-center-line-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left-center → batter-relative.opposite / 左中間 → 流し) |
| `interior-left-center-fly-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left-center → batter-relative.pull / 左中間 → 引っ張り) |
| `interior-left-center-fly-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.left-center → batter-relative.opposite / 左中間 → 流し) |
| `interior-center-ground-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `interior-center-ground-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `interior-center-line-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `interior-center-line-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `interior-center-fly-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `interior-center-fly-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `interior-right-center-ground-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right-center → batter-relative.opposite / 右中間 → 流し) |
| `interior-right-center-ground-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right-center → batter-relative.pull / 右中間 → 引っ張り) |
| `interior-right-center-line-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right-center → batter-relative.opposite / 右中間 → 流し) |
| `interior-right-center-line-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right-center → batter-relative.pull / 右中間 → 引っ張り) |
| `interior-right-center-fly-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right-center → batter-relative.opposite / 右中間 → 流し) |
| `interior-right-center-fly-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right-center → batter-relative.pull / 右中間 → 引っ張り) |
| `interior-right-ground-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right → batter-relative.opposite / ライト → 流し) |
| `interior-right-ground-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right → batter-relative.pull / ライト → 引っ張り) |
| `interior-right-line-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right → batter-relative.opposite / ライト → 流し) |
| `interior-right-line-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right → batter-relative.pull / ライト → 引っ張り) |
| `interior-right-fly-right` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right → batter-relative.opposite / ライト → 流し) |
| `interior-right-fly-left` | 委任元(Claude) | 条文(要件書 :1212)から等角 5 分割を書き直し、**整数の外積だけで**区分を判定 | **一致**(batted-ball-direction.right → batter-relative.pull / ライト → 引っ張り) |
| `boundary-left-left-center-ground-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left → batter-relative.pull / レフト → 引っ張り) |
| `boundary-left-left-center-ground-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left → batter-relative.opposite / レフト → 流し) |
| `boundary-left-left-center-line-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left → batter-relative.pull / レフト → 引っ張り) |
| `boundary-left-left-center-line-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left → batter-relative.opposite / レフト → 流し) |
| `boundary-left-left-center-fly-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left → batter-relative.pull / レフト → 引っ張り) |
| `boundary-left-left-center-fly-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left → batter-relative.opposite / レフト → 流し) |
| `boundary-left-center-center-ground-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left-center → batter-relative.pull / 左中間 → 引っ張り) |
| `boundary-left-center-center-ground-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left-center → batter-relative.opposite / 左中間 → 流し) |
| `boundary-left-center-center-line-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left-center → batter-relative.pull / 左中間 → 引っ張り) |
| `boundary-left-center-center-line-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left-center → batter-relative.opposite / 左中間 → 流し) |
| `boundary-left-center-center-fly-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left-center → batter-relative.pull / 左中間 → 引っ張り) |
| `boundary-left-center-center-fly-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.left-center → batter-relative.opposite / 左中間 → 流し) |
| `boundary-center-right-center-ground-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `boundary-center-right-center-ground-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `boundary-center-right-center-line-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `boundary-center-right-center-line-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `boundary-center-right-center-fly-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `boundary-center-right-center-fly-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.center → batter-relative.center-return / センター → センター返し) |
| `boundary-right-center-right-ground-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.right-center → batter-relative.opposite / 右中間 → 流し) |
| `boundary-right-center-right-ground-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.right-center → batter-relative.pull / 右中間 → 引っ張り) |
| `boundary-right-center-right-line-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.right-center → batter-relative.opposite / 右中間 → 流し) |
| `boundary-right-center-right-line-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.right-center → batter-relative.pull / 右中間 → 引っ張り) |
| `boundary-right-center-right-fly-right` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.right-center → batter-relative.opposite / 右中間 → 流し) |
| `boundary-right-center-right-fly-left` | 委任元(Claude) | 同上。**境界レイ上の点が「先に定義された側」へ帰属する**ことまで確認 | **一致**(batted-ball-direction.right-center → batter-relative.pull / 右中間 → 引っ張り) |
| `outside-left-ground-right` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-left-ground-left` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-left-line-right` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-left-line-left` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-left-fly-right` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-left-fly-left` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-right-ground-right` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-right-ground-left` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-right-line-right` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-right-line-left` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-right-fly-right` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |
| `outside-right-fly-left` | 委任元(Claude) | 同上。**左翼線より外・右翼線より外がファウル域になる**ことまで確認 | **一致**(batted-ball-direction.foul-territory → batter-relative.foul-territory / ファウル地域 → ファウル地域) |

**66 件すべて一致・不一致 0。**

## 5-4. CI 配線の状態(ステップ 7)

**4 契約は既に CI で検査されている**(実測 2026-10-14)—— ルートの `tests/` は `harness` ジョブ、`backend/tests/` は `backend` ジョブで走る。paths フィルタは frontend 側に `contracts/**`、backend 側に `backend/**` と `contracts/**` が既にある。**`.github/workflows/ci.yml` は触っていない。**

**足した境界の検査**(`tests/test_field_geometry_ci_wiring.py`):

| 検査 | 状態 |
| --- | --- |
| **領域シードが 3 層の登録対象になっていない**(`ADR-003:322`) | **現状は空振り** —— 登録先の `backend/domain/manifest.json` が**まだ生成されていない**(段階① の範囲外)。**負例は `tmp_path` の合成 manifest で 3 層すべてを通る**ので、manifest が現れた時点で実効になる |
| **(β)⑦ を `frontend/` が参照していない**(`ADR-003:332`) | **実効**。ソースと設定を静的に走査し、契約名・パス文字列・エイリアス・`backend/domain` への一括参照を拾う。**変異で確認**(`frontend/src/lib/` にパス文字列を 1 行置くとちょうど 1 件赤) |

### (α) の全件消費は本タスクでは書けない(射程の是正・PO 判断 2026-10-14)

**(α) の製品実装が存在しない**(実測 2026-10-14):

| 探した場所 | 結果 |
| --- | --- |
| `frontend/src/lib/courseInputView.ts` | **捕手/投手視点の左右反転だけ**。画面⇄保存の変換ではない |
| `frontend/src/lib/displayGeometry.ts` | 幾何の定数と SVG の補助。(α) の計算ではない |
| `frontend/` 全体 | **捕球選手推定・内外角導出は無い** |
| `backend/src/pitchlog/` | **3 つとも無い** |

**消費する実装が無い状態で消費テストを置くと「1 ケースも消費していないのに緑」になる** —— 計画書のステップ 7 がもともと禁じていた形そのものである。**要件書 `:966` が「正解ベクタの完成をもって発効する」と定めており、ベクタ先行・実装後行が正しい順序**なので、**全件消費は実装と同じ PR で入れる**。申し送りとして計画書 5 節へ記録した(起票はステップ 9)。

**なお `courseInputView.ts` は保存座標を `0`〜`263` の整数として扱っており、付録B-7 の正準表現(単位 `1/263` の整数)と表現が一致する。** 呼称のずれ(1-1)は残るが、**値の形は揃っている**。
## 6. 旧実装との照合結果(ステップ 4)

### 6-1. 全格子の突合(ステップ 3 で実施)

**領域シードと旧規則を、旧 263 格子の全点 `0..263 × 0..263` = 69,169 点で突合し、不一致 0。**委任先の報告とは独立に、委任元が旧ルールを書き直し、`openEdges` を解釈する内外判定を自前で実装した。

### 6-2. ベクタの 31 ケースでの三者突合(ステップ 4)

**ベクタの期待値 / 領域シードの帰属 / 旧規則の帰属**を突き合わせた。領域シードの解釈は委任元が書き直したもので、`openEdges`(辺ごとの開閉)と「**先に定義された領域が優先**」のタイブレークを実装している。

| caseId | 入力(保存座標) | 多角形の帰属 | 旧規則の帰属 | 一致 | 備考 |
| --- | --- | --- | --- | --- | --- |
| `interior-catcher-rectangle` | (123, 33) = 旧 (123, 230) | 2 | 2 | ○ | — |
| `interior-first-base-rectangle` | (180, 83) = 旧 (180, 180) | 3 | 3 | ○ | — |
| `interior-third-base-rectangle` | (50, 78) = 旧 (50, 185) | 5 | 5 | ○ | — |
| `interior-pitcher-rectangle` | (125, 98) = 旧 (125, 165) | 1 | 1 | ○ | — |
| `interior-anchor-8` | (116, 197) = 旧 (116, 66) | 8 | 8 | ○ | — |
| `interior-anchor-7` | (56, 162) = 旧 (56, 101) | 7 | 7 | ○ | — |
| `interior-anchor-9` | (174, 162) = 旧 (174, 101) | 9 | 9 | ○ | — |
| `interior-anchor-6` | (88, 119) = 旧 (88, 144) | 6 | 6 | ○ | — |
| `interior-anchor-4` | (152, 119) = 旧 (152, 144) | 4 | 4 | ○ | — |
| `interior-anchor-5` | (77, 89) = 旧 (77, 174) | 5 | 5 | ○ | — |
| `interior-anchor-3` | (153, 89) = 旧 (153, 174) | 3 | 3 | ○ | — |
| `interior-anchor-1` | (123, 70) = 旧 (123, 193) | 1 | 1 | ○ | — |
| `interior-anchor-2` | (123, 61) = 旧 (123, 202) | 2 | 2 | ○ | — |
| `rect-boundary-catcher-closed-y205` | (123, 58) = 旧 (123, 205) | 2 | 2 | ○ | — |
| `rect-boundary-first-closed-corner-155-165` | (155, 98) = 旧 (155, 165) | 3 | 3 | ○ | — |
| `rect-boundary-third-closed-corner-75-165` | (75, 98) = 旧 (75, 165) | 5 | 5 | ○ | — |
| `rect-boundary-pitcher-closed-left-x105` | (105, 113) = 旧 (105, 150) | 1 | 1 | ○ | — |
| `rect-boundary-pitcher-closed-top-y140` | (125, 123) = 旧 (125, 140) | 1 | 1 | ○ | — |
| `rect-boundary-pitcher-closed-bottom-y190` | (125, 73) = 旧 (125, 190) | 1 | 1 | ○ | — |
| `rect-boundary-pitcher-inside-right-x144` | (144, 113) = 旧 (144, 150) | 1 | 1 | ○ | — |
| `rect-boundary-pitcher-open-right-x145` | (145, 113) = 旧 (145, 150) | 4 | 4 | ○ | — |
| `equal-distance-anchor-8-vs-6-first-8` | (102, 158) = 旧 (102, 105) | 8 | 8 | ○ | — |
| `equal-distance-anchor-8-vs-4-first-8` | (121, 152) = 旧 (121, 111) | 8 | 8 | ○ | — |
| `equal-distance-anchor-6-vs-4-first-6` | (120, 143) = 旧 (120, 120) | 6 | 6 | ○ | — |
| `equal-distance-anchor-6-vs-5-first-6` | (77, 104) = 旧 (77, 159) | 6 | 6 | ○ | — |
| `equal-distance-anchor-4-vs-3-first-4` | (159, 104) = 旧 (159, 159) | 4 | 4 | ○ | — |
| `equal-distance-anchor-1-vs-2-first-1` | (123, 65) = 旧 (123, 198) | 1 | 1 | ○ | — |
| `range-edge-left-x0-valid` | (0, 163) = 旧 (0, 100) | 7 | 7 | ○ | — |
| `range-edge-top-y0-valid` | (123, 263) = 旧 (123, 0) | 8 | 8 | ○ | — |
| `range-edge-right-x263-valid` | (263, 163) = 旧 (263, 100) | 9 | 9 | ○ | — |
| `range-edge-bottom-y263-valid` | (123, 0) = 旧 (123, 263) | 2 | 2 | ○ | — |

**31 件すべて三者一致・不一致 0。**

### 6-3. 旧実装との意図的な差 —— センチネル 1 件

旧 `fielder.ts` は **`x <= 0 || y <= 0` のとき `null`(未入力)を返す**。**本契約はこれを適用しない。**

**理由**: 要件書 **付録B-7**(v2.13・2026-10-14 approved)が「**本項はセンチネル(未入力)の規則を持たない —— 保存座標では `0` が有効な値である**」と定めたため。付録B-5 の `0` センチネルは**旧データ固有の約束**であり、移行時にのみ働く((β)⑥)。

**この差が現れるケース 2 件**:

| caseId | 入力(保存座標) | 旧 263 系 | 旧実装 | 本契約 |
| --- | --- | --- | --- | --- |
| `range-edge-left-x0-valid` | (0, 163) | (0, 100) | `null`(未入力) | **7** |
| `range-edge-top-y0-valid` | (123, 263) | (123, 0) | `null`(未入力) | **8** |

**未入力をどう表すかは本タスクの射程外**(付録B-7 の射程宣言が別タスクへ送っている)。**座標の値としては `0` も有効**なので、本契約は旧の矩形 + 最近傍の規則をそのまま当てる。

**センチネル以外の不一致は無い。**
