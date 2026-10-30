# 座標計画 指摘対応表・境界仕様（2026-10-30）

対象計画: `docs/features/course-coordinate-single-operation/plan.md`
第1回 REPORT: `~/.cache/pitchlog/course-coordinate-plan-review-20261030/REPORT.md` SHA `19e0a36a…395a4b`（否決 P0=3/P1=12/P2=7）
再レビュー REPORT2: 同 `REPORT2.md` SHA `7ebb399d…2c30e`（否決 P0=2/P1=12/P2=7）
候補HEAD: `92453a3e`（本表の是正前）。本表と計画の是正差分を同一単位で固定する。
**過去の判定・件数・REPORTは書き換えない。** 下表は指摘IDを保持し、重複は関連付けで示す。

## 1. 対応表

| ID | 根拠（正本/実装/ケース） | 問題 | 是正差分 | 確認方法 | 状態 |
|---|---|---|---|---|---|
| R1-P0-1 | D18採用記録・計画 §3 旧ステップ2 | artifact改変・再生成・pinが7.3ゲート前 | ステップを「ベクタ/oracle/descriptor（前）→7.3→artifact（後）」へ | ステップ表の順序とゲート前変更の有無 | **解消**（R2でP0-1閉） |
| R1-P0-2 / R2-§4 | `sync/first_ball_execution.py`・`repositories/recorded_snapshot.py`・`sync/first_ball_course.py` | 「k/263は製品経路から除去済み」が事実と逆。受入が候補を無条件の正解に | 事実を訂正し、受入は既存B-7契約の変換で照合。Python `k/263` は候補と明記 | 実装のgrepと受入条件の文言 | **解消**（`92453a3e`） |
| R1-P0-3 / R2-P0-4 | `contracts/display-geometry/coordinate_transform_contract_v1.json`（42ケース）・D-6/D-8/D-11・B-7:1319-1322 | 契約の真部分集合を「単一実装の契約ベクタ」と認定。同じ計算の2本目ベクタを作る | 既存契約を**再利用**。量子化は**入力形成**、画面⇄保存は既存B-7。二段階境界を明記 | 42ケースの不変・新規計算ファイルの不在 | **解消**（`92453a3e`） |
| R2-P0-4（B-7） | 要件 B-7:1321「画面→保存では丸めを行わない」 | (a)がB-7改訂を隠す | B-7は変換自体の規定で、入力形成の量子化を禁止しないと原典で確認。**B-7の意味変更なし** | 原典行の引用と二段階仕様 | **解消**（本表 §3） |
| R1-P1-y / R2-P1 | B-2/B-7:1322、`StrikeZone.vue:51,70` | y軸の向き・`263−y`が未定義 | §3で「画面y下向き→保存 `y_norm=(263−y)/263`」を固定。量子化は画面yに適用 | 固定入力のy期待値 | **解消**（§3） |
| R1-P1-丸め / R2-P1 | 付録A-1、D-14-e 3、`Math.round(-0.5)` | 「DSLに除算が無い」は誤り。十進文法・スケール上限・BigInt剰余丸めが無い | §3/§4/§7.1の文法を最短往復表現（固定桁上限なし・指数可）へ統一し、BigInt剰余の half-up を §8 で実証 | 文法の一致と境界ベクタ | **未解消**（§7.1/§8の反映後に再確認） |
| R1-P1-範囲 / R2-P1 | B-7のクランプ・D-11のクランプ点 | 範囲外fail-closedがクランプと衝突 | **クランプは表示入力（StrikeZone）で行い、量子化は0..263外を拒否**。クランプ点は既存42ケースの意味を維持 | 0/263/263.4/-0.5の期待 | **解消**（§3/§4） |
| R1-P1-size / R2-P1 | 要件 B-7「正は `display_geometry_263_v1.json` の size」 | 263/`unit:"1/263"`の焼き込みが二重管理 | `size` を契約から供給し、operationはsizeを入力に取る。unit文字列は境界で契約から導出 | 263変更時の追随試験 | **未解消**（§3の「1/263」表現をsize導出へ統一して再確認） |
| R1-P1-3層 / R2-P1 | ADR D-6 のCI検査4項目・J2 | properties/mutation/descriptorが無い | 既存42ケースに properties（単調・範囲・反転不変）と mutation を追加。J2はADRで既に必須と確認 | descriptorの実在とmutation落ち | **未解消**（材料は§4、実装はゲート後） |
| R1-P1-manifest / R2-P1 | `frontend/public/domain/pitchlog-domain.json` ほか | `backend/domain/manifest.json`不在でdirectTargets/runner/収集器が未具体 | 既存の artifact 宣言（`frontend/public/domain/pitchlog-domain.json`）を更新対象とし、backend側manifestの実体を確認して計画に書く | manifestの実パスとpin対象 | **未解消**（実体確認が次） |
| R1-P1-float反転 / R2-P1 | `StrikeZone.vue` の `courseScreenXToStoredX`・NFR-018(c)例外 | 既存float反転と逐語移植例外の扱いが未記載 | 量子化後の**整数**反転へ置換し、float反転は削除。NFR-018(c)例外の失効をゲート対象に | 反転の単一実装grep | **未解消**（ゲート対象） |
| R1-P1-V7 / R2-P1 | backend `first_ball_payload.py` の formatter | V7組立の置き場・ステップ所有が未決 | V7は**artifactの単一formatter**（backendはホスト経由）を第一候補とし、ステップ3で確定・ステップ4が所有 | 同一JSの両実行 | **未解消**（ゲート判断） |
| R1-P1-封鎖 / R2-P1 | `GameScreenCommitGate.ts`・D02/U-X1 | 封鎖解除の前提が計画に無い | 解除は排他保持単位・U-X1凍結・D5/D2/queue/ACKの成立後。本計画は座標供給のみ | 前提チェックリスト | **未解消**（別単位） |
| R1-P1-D14m / R2-P1 | ADR-003 D-14-m・NFR-018 のT1/T2限定文・B-3 | 「追記」では足りず書き換えが必要 | ゲート対象に**書き換え**を明記（§5） | 改訂差分のレビュー | **未解消**（ゲート） |
| R2-P1-その他 | 計画の各節 | 是正が「ゲートで決める」に留まる | 本表§3/§4で材料化。残る新規意味だけ§5へ分離 | 本表の記載 | **一部解消** |

## 2. 再利用と追加の分離

- **再利用（変更しない）**: `coordinate_transform_contract_v1.json` の42ケース（画面⇄保存・往復・内外角・クランプ点・打席左右）。B-7:1319-1322 の式と付録A-1の丸め。保存→画面の丸め。
- **追加（新規）**: **入力形成の量子化**（別計算 `course-input-quantization`）。operation は量子化に加え、**内部で既存B-7契約の変換を消費**して保存正準整数を返す（融合）。B-7 の別実装・2本目のベクタは作らず、`courseScreenXToStoredX` は削除する。ケースは最短往復表現・指数・境界・範囲外・量子化後の反転。
- **触らない**: 既存42ケースの意味・値・件数。V7の保存変換（B-7）と保存payloadの `unit:"1/263"`。

## 3. 境界仕様（呼出順・型・値域・丸め・拒否）

1. **タップ取得**: `StrikeZone` が画面座標（x右・y下、0..263の表示値、クランプ済み）を float で返す。
2. **入力形成（D11=A）**: 最短往復の十進文字列（`String(value)`、指数可、入力長≤400・|指数|≤400、`1.`/`.5` も文法上は受理）→ BigInt スケール整数 → `2r≥|d|` で half-up（負値は絶対値で丸めて符号を戻す）→ **整数の画面座標 0..size**（表示でクランプ済み）。範囲外・非十進・非有限は拒否。**丸めはここで一度だけ**。
3. **視点反転**: 量子化**後**の整数xに投手後方視点の左右反転を一度だけ適用（`courseScreenXToStoredX` の置換）。yは反転しない（B-7のy反転と別軸）。
4. **既存B-7変換**: `x_norm=x_screen/size`、`y_norm=(size−y_screen)/size`。**この向きでは丸めない**。保存→画面のみ付録A-1で丸める（記録経路では使わない）。
5. **payload/V7**: `course={unit:"1/size", x:"<k>", y:"<k>"}`（整数文字列）。V7はartifactの単一formatter。**二重丸め・二重反転なし**（丸め=2のみ、x反転=3のみ、y軸反転=4のみ）。

## 4. 判断材料（ゲート前に確定できるもの）

| 項目 | 材料 | 出所 |
|---|---|---|
| y式 | `y_norm=(263−y_screen)/263` | 要件 B-7:1322 |
| 十進文法 | `^-?(0|[1-9]\d{0,2})(\.\d{1,6})?$`、超過拒否 | 表示解像度と二重丸め防止（技術具体化） |
| クランプ/拒否 | 表示入力でクランプ、量子化は範囲外拒否 | B-7:1319-1322・StrikeZone |
| size供給 | `display_geometry_263_v1.json` の `size` をoperation入力（十進文字列）へ | 要件 B-7 |
| 丸め軸 | x・yとも入力形成で一度、保存→画面は表示のみ | 付録A-1・B-7 |
| oracle | Python `Fraction` の独立half-up。264×2×2＋境界。実装から期待値を生成しない | NFR-019(a) |
| manifest | `frontend/public/domain/pitchlog-domain.json` を更新。backend側の実体は次に確認 | 既存artifact宣言 |
| 単一実装 | artifact TS→同一JSを両実行。Pythonはホスト経由 | D18=A |
| V7配置 | artifactのformatter（第一候補）。ステップ3で確定、ステップ4が所有 | 計画§3 |

**新たな意味判断として分離するもの**: なし（y式・丸め・反転・クランプは既存B-7/D11/付録A-1で決まる）。固定小数桁の上限は設けない（最短往復表現を受理）。範囲判定は表示クランプ後に行い、`size` 超・負値は拒否。

## 5. 検証ベクタ（固定入力・期待値）

| 入力（画面x,y / 視点） | 量子化後 | 保存k（x,y） |
|---|---|---|
| 131.5, 124 / 捕手 | 132, 124 | 132, 139 |
| 131.5, 124 / 投手後方 | 131, 124 | 131, 139 |
| 0, 0 / 捕手 | 0, 0 | 0, 263 |
| 263, 263 / 捕手 | 263, 263 | 263, 0 |
| -0.5, 124 | 拒否 | — |
| 263.4, 124 | 拒否 | — |
| `263.5`（→264） | 拒否（範囲外） | — |
| ` 1`, `01` | 拒否（非正準） | — |

既存42ケースは不変。追加期待値は上表の固定入力のみで、対象実装から生成しない。

## 6. 候補固定とレビュー

- 候補HEAD: `92453a3e`（本表・計画の是正コミットを同一単位で固定）。
- 差分SHA: 本表＋plan.md の差分を `git diff 92453a3e..<是正HEAD>` で固定。
- レビュー回数: 第1回・再レビューの2回を保持。次は**差分確認**（変更節のみ）を既存委任で行い、全文周が必要ならPO判断を記録する。未解消を残したまま可決扱いにしない。

## 7. 追加調査（2026-10-30、ユーザー指示2・3への回答）

### 7.1 十進6桁上限は**不採用**（正常入力を拒否し、境界を動かす）

- `StrikeZone.vue:51-53` のタップは `courseScreenXToStoredX` と `Math.max(0.1, Math.min(262.9, y))` を通る **float** で、
  canvas 比から 131.49999999999997 のような長い十進表現になり得る。6桁で切ると (a) 正常タップの拒否、
  (b) `toFixed(6)` による**二重丸め**（例 131.4999996→131.500000→132 の境界越え）が起きる。
- **採用（文法を §1/§3.2/§4/§5/§7.1 で同一に）**: 入力は `String(value)` の**最短往復表現**
  （`[+-]?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?`、指数は有限、値は有限）。**固定小数桁の上限を設けない**
  （最短表現は定義上17有効桁以内）。有理数対は採らない（最短表現が同じ double に復元され、`.5` との
  大小/一致を保つため）。UI は丸めない。**D11 の意味（half-up を一度だけ）を維持**する。
- **範囲**: 表示入力で `[0, size]` にクランプした後に渡す。operation は範囲外（`size` 超・負値）を**拒否**する。
  したがって `263.4` と `-0.5` は**受理しない**。`262.9→263` は half-up の結果。
- 検証: `131.49999999999997`→131、`131.5`→132、`131.50000000000003`→132、`0.1`→0、`262.9`→263（クランプ入力後）、
  `263`→263、`263.4`は入力で拒否。固定入力で境界前/一致/直後を固定する。

### 7.2 呼出順の実測 — **float 反転が既に画面側にある（二重反転の危険）**

- 現行: `StrikeZone` が `courseScreenXToStoredX`（`263 − screenX`）を **float のまま**適用して emit →
  下書き → V7。D11=A は「量子化**後**に反転」なので、この順のまま量子化すると**反転が二重**になる。
- **確定（入出力型）**: `quantizeCourse({x, y, view, batterSide, size})`
  入力 `x,y`: 画面座標（x右・y下、float、表示で `[0,size]` にクランプ済み）、`view`: `catcher|pitcher`、
  `size`: `display_geometry_263_v1.json` の `size`。出力: `{unit:"1/<size>", x:"<k>", y:"<k>"}`（保存正準整数）。
  **内部順**: 画面x,yを half-up で整数化（1回）→ 投手後方視点の x 反転（1回）→ B-7 の y 軸反転
  `size−y`（1回）→ 整数文字列。`courseScreenXToStoredX` の float 版は削除する（U3の置換範囲）。
- **y の戻り経路**: キーボード入力・マーカー入力も同じ `quantizeCourse` に画面座標を渡す（保存値を
  直接渡さない）。表示は artifact の保存→画面変換（既存42ケース）を使う。
- 二重丸め・二重反転の検査: 量子化1回・x反転1回・y軸反転1回を、呼出順のベクタで固定。

### 7.3 manifest・V7・例外の実体

- **D-11 の manifest と artifact 宣言を区別する（P0）**: `backend/domain/manifest.json` は現状**不在**で、
  D-11/D-6 が要求する**計算 manifest（entrypoints/directTargets/比較面）**の置き場として**新設が必要**。
  `frontend/public/domain/pitchlog-domain.json`（`domainrt/host.py:17`）は artifact の SHA 宣言であり、
  manifest の代用ではない。更新対象は (a) `backend/domain/manifest.json` の新設と operation 登録、
  (b) `frontend/public/domain/pitchlog-domain.json`/`.js` の再生成と SHA、(c) `first_ball_payload_vectors_v1.json`
  の `artifactSha256`。**両者を取り違えない**。
- V7 formatter は backend の Python（`first_ball_payload.py`）にあり、artifact には無い。**座標ゲートの対象に
  V7 を含めない**（V7 組立は座標の出力を使う別単位）。座標ゲートは「量子化→画面座標→既存B-7の k」まで。
- `courseScreenXToStoredX` の float 反転は **本ゲートで置換を確定**する（量子化後の整数反転へ置換し、
  float 版を削除）。NFR-018(c) の逐語移植例外は、`COURSE_COORDINATE_SIZE` の既存計画の扱いを維持しつつ、
  **float 反転の例外は本ゲートで失効**させる。V7/画面の実装へ先送りしない。

### 7.4 ゲート前後の分割（拡大しない）

- **ゲート前**: 既存42ケースの不変確認、量子化の固定ベクタ（7.1/7.2）、独立oracle、properties/mutation の
  descriptor、ADR/要件/B-7注記の改訂差分、ゲート対象正本の列挙。
- **ゲート後**: artifact primitive/`quantizeCourse`・生成物・pin/manifest・StrikeZone の置換・V7 接続・
  properties/mutation の実行・U3/U4 の画面E2E。V7 formatter の配置は別判断として分離。

## 8. DSL 実現性（ゲート前・隔離検証）

**結論: 実現できる。** artifact は別個の DSL インタプリタではなく、`frontend/src/domain` の TS 正本を
`frontend/scripts/domain-build/build.mjs` で単一 JS（`pitchlog-domain.js`）へ閉じた生成物で、既に
BigInt・十進文字列 codec（`decimalCodec.ts`）・`globalThis.PitchlogDomain` を持つ。ブラウザと Python ホスト
（`domainrt/host.py` が Node で同一 JS を実行）で同じ実装が動く。字句検査の禁止は import/export/require のみで、
`BigInt` の `/`・`%` は使用済み。ドメインコードは `number`/`Math.round` を使わない。

**採用する方法**
- UI はタップの float を `String(value)`（最短往復表現）で渡す。**固定小数桁の上限を設けない**。
  最短表現は同じ double に復元され、`.5` との大小/一致関係を保つため、half-up の判定を変えない。
- artifact は十進（指数表記含む）を符号・整数部・小数部・指数へ分解し、`BigInt` のスケール付き整数にする。
  `q=|n|/|d|`、`r=|n|%|d|`、`2r≥|d|` で切り上げ、符号を戻す。
- **量子化後に整数で反転**（`size − k`）。`size` は `display_geometry_263_v1.json` の `size` を入力に取り、
  263 を焼き込まない。範囲外（0..size 外）・非十進・非有限は拒否。クランプは表示入力側。
- y は画面座標（下向き）を渡し、既存 B-7 が一度だけ `size − y` を行う。

**隔離検証（製品artifact/契約/凍結値は未変更。製品実装済みとは扱わない）**
- **隔離スクリプトは artifact の検証規則に適合しない**（`**`・正規表現・`throw`・三項・`Number` を使用）ため、
  **「実装可能」の根拠にはしない**（REPORT4）。以下は**丸め規則の数値確認**であり、artifact 実装の証明ではない。
  artifact 適合の最小プロトタイプ（許可された BigInt 演算のみ）は**ゲート前の別作業**として作成する。
- 参考（規則の数値確認）: Node の BigInt 実装と Python `Fraction` の独立 oracle で**丸め関数だけ**を照合:
  `131.49999999999997→131`、`131.5→132`、`131.50000000000003→132`、`0.49999999999999994→0`、
  `0.5→1`、`-0.5→-1`、`0.1→0`、`262.9→263`、`263→263`、`263.4→263`、`1e-7→0`。**全一致**。
  反転は `263−132=131`、`263−131=132`。期待値は Python の厳密有理数から独立に算出。
- **注意**: `-0.5→-1` と `263.4→263` は**丸め関数単体**の結果であり、operation の受理値ではない。
  operation は範囲外（負値・`size` 超）を拒否する（§7.1）。
- 制約: 指数表記の受理（`1e2`=100 も値として受理）、指数の有限性、`number`/`Math.round` 不使用、
  `size` の入力化、**反転は `view==='pitcher'` のときだけ**。範囲は表示クランプ後 `[0,size]`、`size` 超・負値は拒否。
- **結論の位置づけ**: 型・許可用語・同一JS実行から**実現可能**と判断するが、artifact 適合の実証はゲート前の
  最小プロトタイプで行う。製品実装済みとは扱わない。

**ゲートへの影響**: 実現性は確認済み。ゲート前の残りは非作者の差分確認と ADR/要件の整合改訂。
artifact への実装・pin・properties/mutation の実行は**ゲート後**。

## 9. artifact 適合の最小プロトタイプ（隔離・証拠）

前回の `quant.mjs` は撤回し、**artifact の検査器を通る最小プロトタイプ**を作成した。製品 artifact・正式契約・凍結値・公開経路は変更していない。

- **入力**: `{x, y, view, size}`。`x,y` は画面座標の最短往復表現（符号・整数・小数・指数を受理、先頭0と空指数は拒否）。
  `view` は `catcher|pitcher`、`size` は BigInt（契約 `display_geometry_263_v1.json` の `size`）。
- **出力**: `{ok:true, value:{unit:"1/<size>", x:"<k>", y:"<k>"}}`。範囲外・非正準・不正 view は `ok:false` と閉じた code。
- **内部**: 十進/指数 → BigInt スケール整数 → `q=|n|/|d|`・`r=|n|%|d|`・`2r≥|d|` の half-up（符号を戻す）→
  **量子化後に** `view==='pitcher'` のときだけ x を `size−x` → y を `size−y`（B-7、1回）。
- **制約**: `number`・`Math.*`・`**`・`throw`・三項・正規表現を使わない（`for..of`・`BigInt`・`if/else`・文字列 codec のみ）。
- **証拠（固定入力・独立期待値）**
  - artifact 字句検査 `inspectArtifactTokens` = **violations 0**（`import/export/require` なし）。
  - **Node** 15ケース（境界・指数・不正・反転）= **全て一致**。
  - **Chromium** 14ケース＋反転 = **全て一致**。
  - **Python ホスト経由**（Python から Node を起動し同一 JS を実行）と Python `Decimal`→`Fraction` の独立 oracle
    15ケース = **全て一致**。
  - 反転: `131.5` は catcher で `x=132`、pitcher で `x=131`（y は両方 139）。
  - 境界: `131.49999999999997→131`、`131.5→132`、`131.50000000000003→132`、`0.5→1`、`0.49999999999999994→0`、
    `262.9→263`、`263→263`、`263.5→OUT_OF_RANGE`、`-0.5→OUT_OF_RANGE`、`1e2→100`、`1e-7→0`、` 1`/`01`/`1e`→INVALID_DECIMAL。
  - プロトタイプ SHA256: `eeb5603d6beac0e86dd3f77ed952a3560480df10b7075e3aa1aab856b8a8d302`。
- **位置づけ**: 実現性の隔離証拠であり、製品実装済みではない。製品化はゲート後に artifact へ移植し、
  properties/mutation・pin・manifest を同一段で行う。

### 9.1 REPORT5 の P1 4件を反映した再検証（プロトタイプ第2版）

- **SHA256（第2版・入力長判定の前倒し後）: 再実行で更新**（第1版 `eeb5603d…` は履歴）。入力長≤400 を走査前に判定（OOM回避）。独立 oracle の再現物: `/tmp/opencode/proto/oracle.py`。
- **判定点の固定（P1-1）**: 量子化の**前に**入力の厳密値が `[0,size]` かを判定する。`263.4`・`263.0001`・`-0.4`・`-0.0001`・`263.5` は **OUT_OF_RANGE**（`263.5` だけでは判別しない）。丸め後の範囲確認は安全側の二重チェック。
- **出力段の一本化（P1-4）**: 出力は「量子化→pitcher の x 反転→y=`size−y`」を**融合した保存正準整数** `{unit,x,y}`。量子化だけの別解は採らない（y の二重反転・B-7 の二重実装を避ける）。
- **指数・桁上限（P1-3）**: 指数の絶対値 ≤400、入力長 ≤400。`1e-1000000` / `1e1000000` は **INVALID_DECIMAL**（常駐 Node の VM 上限を踏まない）。
- **封筒（P1-2）**: 入出力を **JSON 文字列**、失敗を **`{ok:false,error:{code}}`** に統一。`size` は十進文字列。
  実ホストの凍結入口名（`PitchlogDomain.<operation>`）へのアダプタは**ゲート後**の製品実装で付ける（プロトタイプは `QuantPrototype`）。
- **再検証（22ケース）**: Node **22/22**、Chromium **22/22**、Python ホスト経由（Node 起動）と独立 `Decimal`→`Fraction` oracle **22/22**。
  固定入力: 131.5前後、0.5前後、0/263、262.9→263、`1e2`→100、`1e-7`→0、`263.4`/`263.0001`/`-0.4`/`-0.0001`/`263.5`→OUT_OF_RANGE、
  `1e±1000000`/` 1`/`01`/`1e`→INVALID_DECIMAL、pitcher 反転 `131.5→131`・`0.5→262`。
- **位置づけ**: 実現性の隔離証拠。製品実装・pin・manifest はゲート後。実ホスト入口の1ケース確認はゲート後の最初の実装検査。
