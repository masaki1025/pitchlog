---
feature: frozen-archive-literal-pins
type: design
date: 2026-10-01
---

# 詳細設計: frozen_archive のテストのリテラル固定を外す(TSK-466)

**典拠の正は [research.md](research.md)。** 本書は是正の設計だけを書く。

## 0. 問題の形

**守りたいもの**(維持する)と、**偶然そこにあるもの**(外す)が同じ assertion に同居している。

| | 守りたいもの | 偶然そこにあるもの |
| --- | --- | --- |
| `== 50` | **抽出が空集合で素通りしていない**([research.md](research.md) 2 — `design.md:92` の 4 周目 P1) | **現在の参照数がたまたま 50** |
| 版列 `[1,2,2,2,2,2]` | **v1 と v2 が混在した履歴を扱えている**(3 周目 P1) | **現在の記録数がたまたま 6** |
| metrics 4 値 | **実測値が閾値内で、孤児が比較元から増えていない** | **現在の snapshot 数がたまたま 83** |
| `len(authority_history) == 6` | **履歴が自明でない長さを持つ** | **現在の記録数がたまたま 6** |
| corpus digest | **比較 corpus の入力が動いたら落ちる** | **現在の履歴と snapshot の内容が digest に入っている** |

**是正の原則**: **左列を落とさずに右列だけを外す。** 「非空にする」「assert を消す」はいずれも左列を壊すので採らない。

## 1. 置換の設計(クラス A・B)

### 1-1. 参照集合 — **独立オラクルとの照合へ置き換える**

**いまの形**: `len(archive.extract_referenced_snapshot_names(history, root)) == 50`

**採る形**: **テスト側に独立した抽出を 1 つ置き、被検査実装の出力と集合として一致させる。**

```
expected = {
    ref
    for record in history
    if record.get("record_schema_version") == 2
    for aspect in ("external_snapshots", "asset_snapshots")
    for side in ("before", "after")
    for entry in record["change"][side][aspect]
    if (ref := entry["snapshot_ref"].removeprefix(SNAPSHOT_REF_PREFIX))
}
assert archive.extract_referenced_snapshot_names(history, root) == expected
assert expected  # 退化(空集合)を拒否する
```

**なぜこれで左列が守れるか**:

- **空集合での素通りを塞ぐ**: `assert expected` が非空を要求し、かつ**両辺が独立に計算される**ので、「常に空集合を返す」実装は不一致で落ちる
- **誤った extractor の割り当てを塞ぐ**(4 周目 P1 の本来の標的): `declaration` / `movement_policy` へ extractor を割り当てる変異を入れると、被検査側だけが余計な要素を返して不一致になる
- **記録数に依存しない**: 期待値が履歴から導出されるので、受理記録が増えても両辺が同時に増える

**NFR-018 との関係**: spec-checker の判定どおり、参照集合を数える処理は NFR-018 の対象列挙(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定 — 設計書 `:892`)に入らない([research.md](research.md) 3)。**テストが独立オラクルを持つことは重複実装ではなく、検査の前提である。**

**変異テストの事前条件**(`:139` `:164` `:198-200` `:210-212`)も同じ形に置き換える。

**オラクルの効力の限界(1 周目 P2-5 の反映)**: **分類を反転する変異は、抽出へ届く前に製品側の期待表照合(`scripts/frozen_archive.py:119-132`)で拒否される。** また `declaration` / `movement_policy` は配列ではないので、**誤割り当ては「余計な要素を返す」より先に型検査(`scripts/frozen_history.py:1574` `:1597`)で拒否される。** したがって上記オラクルが単独で捕まえるのは**退化(空集合)と抽出漏れ**であり、**分類誤りは既存の期待表照合が捕まえている。** 変異試験では **red の原因(どの検査が落としたか)を記録する**。**オラクル自体の効力を主張するなら、期待表照合を通過する誤抽出**(例: `external_snapshots` の extractor が `before` 側だけを見る)**を 1 件試験する。**

**metrics の孤児期待値も被検査抽出器を共有する**(1-3 が `_current_references()` を使うため)。**孤児の期待値については「独立オラクル」を主張しない** — 主張するのは「件数・バイト数が実測と一致し、比較元から増えていない」ことまで。**「変異前が green」の保証**は、`== 50` ではなく**上記の一致**が担う。

### 1-2. 版列 — **構造条件へ置き換える**

**いまの形**: `[record.get("record_schema_version", 1) for record in history] == [1, 2, 2, 2, 2, 2]`

**採る形**:

```
versions = [record.get("record_schema_version", 1) for record in history]
assert len(versions) >= 2          # v1 と v2 が混在しうる長さを要求する
assert versions[0] == 1            # bootstrap は v1
assert set(versions[1:]) == {2}    # 以降はすべて v2
```

**順序が意味を持つ(ステップ 3 の差し戻しで判明・2026-10-01)**: **長さ条件を最後に置くと、どの変異でも発火しない。** 履歴が 1 件(v1 のみ)のとき `versions[1:]` は `[]` で、`set([]) == {2}` が先に False になるため。**長さを先に見ることで、3 条件それぞれが別の変異で発火する。**

| 変異 | 発火する条件 |
| --- | --- |
| 履歴を 1 件に減らす | `len(versions) >= 2` |
| 先頭を v2 にする | `versions[0] == 1` |
| 途中に v1 を混ぜる | `set(versions[1:]) == {2}` |

**守るもの**: 「v1 と v2 が混在した履歴を扱えている」(3 周目 P1 — `design.md:80-86`)。**先頭が v1 であることは `check_tenant_boundary_bypass.py:82 PENDING_APPROVAL` の bootstrap 記録の性質から来る不変で、記録数とは独立。**

### 1-3. metrics — **独立計数との照合へ置き換える**

**いまの形**: `SnapshotArchiveMetrics(83, 2_958_228, 33, 1_214_665)` との exact 一致。

**採る形**: **ディレクトリを直接数えた値と照合する。**

```
files = sorted(p for p in SNAPSHOT_ROOT.iterdir() if p.is_file())
expected_count = len(files)
expected_bytes = sum(p.stat().st_size for p in files)
expected_orphans = {p.name for p in files} - _current_references()

assert metrics.snapshot_count == expected_count
assert metrics.snapshot_bytes == expected_bytes
assert metrics.orphan_count == len(expected_orphans)
assert metrics.orphan_bytes == sum((SNAPSHOT_ROOT / n).stat().st_size for n in expected_orphans)
assert metrics.snapshot_count <= archive.SNAPSHOT_COUNT_LIMIT
assert metrics.snapshot_bytes <= archive.SNAPSHOT_BYTES_LIMIT
assert comparison.head.orphan_count <= comparison.base.orphan_count
```

**守るもの**: 「`_measure_snapshot_archive` が正しく数えている」「閾値内」「孤児が比較元から増えていない」。**被検査実装の出力をそのまま期待値にしていない**(独立計数と照合している)。

**閾値ちょうどの受理を守る試験**(`:363-364` `:396-397`)は**合成 `tmp_path` で現況非依存**なので触らない([research.md](research.md) 1)。

### 1-4. `len(authority_history) == 6`

**採る形**: `assert len(authority_history) >= 2`。

**守るもの**: 「履歴が自明でない長さを持つ」。**この assert は `FROZEN_BASELINE_ASSETS` で parametrize されており 8 インスタンスに効く**(`tests/test_check_tenant_boundary_bypass.py:3323`)ので、**1 行の変更が 8 件の failure を解く**。

## 2. corpus digest(**本タスクの核心**)

### 2-1. 現状の digest が落ちる理由

`corpus_inputs.trees` に `contracts/tenant_boundary` がディレクトリごと入っており、**受理記録は `base-allowlist.json` の `baseline_control.history` を変え、`history-snapshots/` にファイルを足す**。どちらも digest 対象なので必ず動く([research.md](research.md) 6)。

**`history-snapshots/` だけを除外しても解けない**(authority 本体が動くため)。

### 2-2. 実測に基づく判断 — **期待値は記録数に不感応である**

**TSK-448 は比較元を 3 度動かし、そのたびに受理記録が増えた状態で 11 ケースを当て直している。**

| 比較元 | 11 ケースの結果 |
| --- | --- |
| `1a404101` | 緩和 0 件 / 締め `{4, 5, 6, 7, 11}` |
| `33afd352` | **同じ** |
| `ec02a0d2` | **同じ** |

(典拠: `docs/worklog/2026-09-26-frozen-history-7d-remainder.md` の 2026-09-30 の節、および `docs/features/frozen-history-7d-remainder/design.md` 6-3)

**つまり digest は、3 度にわたり「結果に影響しないと実測された変化」で発火している。** 検出すべき drift(検査器の変更・生成規則の変更・契約の形の変更)とは別物である。

### 2-3. 採る形 — **digest を残し、「追記不感応・改竄検知」の形へ変える**(**1 周目 P1-1 / P1-2 の反映**)

**初稿は「`baseline_control.history` と `history-snapshots/` を digest 入力から落とす」としていたが、敵対レビュー 1 周目で却下した。**

**却下の理由(原典で確認)**:

1. **既存履歴の改竄が検出されなくなる。** 初稿は「`_validate_snapshot_append_only` と `_validate_repository_identifier_record` が独立に検査している」と書いたが、**成立しない。** `_validate_snapshot_append_only` は **snapshot だけ**を比較する(`scripts/frozen_history.py:1661-1672`)。既存記録の書き換えを拒むのは**比較元との prefix 一致**(`scripts/frozen_history.py:224-230`)であり、**corpus は現況を合成 base にコピーする**(`tests/test_check_tenant_boundary_bypass.py:1125-1150`)ので、**現況の既存記録を書き換えると両側が同じ値になり prefix 検査を通る**
2. **既存 snapshot の削除も見えなくなる**(subtree を丸ごと外すため)

**採る形: 全体の digest ではなく「生成時点の prefix と集合」を固定する。**

| 対象 | 固定するもの | 追記したとき | 改竄・削除したとき |
| --- | --- | --- | --- |
| `base-allowlist.json` の `baseline_control.history` | **先頭 `k` 件の内容の digest**(`k` は corpus 生成時点の件数。**正規化した JSON 値であってバイト列ではない** — 実装の敵対レビュー 1 周目 P2) | **`k` 件目までは不変 → 通る** | **prefix の digest が動く → red** |
| `contracts/tenant_boundary/history-snapshots/` | **生成時点に存在した `m` 件の名前と内容** | **新規ファイルは digest の対象外 → 通る** | **固定した 1 件でも欠ける・変われば red** |
| それ以外(検査器 6 本・資産の宣言部・資産のメンバシップ・`runner.py`・正規化 manifest) | **現状どおり全内容** | — | **red**(変更なし) |

**なぜこれが正しいか**: **凍結履歴の規律そのものが append-only である**(設計書 7.7-2 `:607`)。**corpus が主張すべきは「生成時点に存在したものが変わっていない」ことで、「その後に何も足されていない」ことではない。** 初稿は後者を主張していたため、追記のたびに発火していた。

#### 識別値も除外する(**ステップ 5 の実測で判明・2026-10-01・山田正輝承認**)

**適法な受理記録の追記は、履歴と snapshot だけを動かさない。** ステップ 1 の合成の実測:

| `base-allowlist.json` の変化 | |
| --- | --- |
| `contract_revision` | 19 → 20 |
| `baseline_control.identity.current_identifiers` | 19 → 20 |
| `baseline_control.history` | +1 件 |
| `history-snapshots/` | +1 ファイル |

**識別値の繰り上げは受理記録と不可分**(identity 機構の本体)。初稿の除外では digest が動いたまま(現況 `f4ef1aac…` / 合成 `700e8729…`)。

**したがって除外へ「`baseline_control.identity.field` が指すトップレベル欄と `current_identifiers`」を加える。** **ただしフィールド名はハードコードせず、資産自身の `baseline_control.identity` 宣言から導出する。** これは TSK-235 が台帳候補 4 件目で引いた境界(**免除の根拠が宣言の中にあり実測で照合できる場合に限る**)と同じ形である。

#### 安全上の検討(**人間の判断 2026-10-01**)

**「他で検査されているから安全」という論法は、履歴については敵対レビュー P1-1 で潰されている。** 識別値について同じ論法が使えるかを**構造で確認した**:

| | 履歴(P1-1 で潰された) | 識別値 |
| --- | --- | --- |
| 検査の形 | **比較元と HEAD の prefix 一致**(`scripts/frozen_history.py:224-230`) | **資産 1 本の中の整合**(`scripts/check_tenant_boundary_bypass.py:374` の `_validate_baseline_control(asset, location)` は**単一資産**を受け取る) |
| corpus が現況を両側へコピーすると | **両側が同じ値になり素通り** | **base が何であろうと成立する** |

**識別値の整合は資産内で閉じているので、corpus のコピーで抜けない。** 履歴とは構造が異なる。

**現状維持のほうが危険である**、という判断も記録する。**いまの digest は適法な変更のたびに必ず発火し、TSK-444 は既に 1 回手で再導出している。** #74・#87・#443 も同じことをする。**毎回鳴る検知器は反射的に再導出されるようになり、本物の drift が混ざっても見られなくなる。**

**corpus digest はセキュリティ制御ではない。** テナント境界を守るのは `check_tenant_boundary_bypass.py` と `frozen_history.py` で、実 PR の base/head に対して毎回走る。**corpus digest の仕事は 11 ケースの回帰試験が陳腐化しないこと**である。

#### 足す守り 3 つ(**承認の条件**)

1. **除外先を資産の `baseline_control.identity.field` 宣言から導出する。** フィールド名をハードコードしない(**列挙は黙って古くなる**)
2. **`pinned_prefixes` 自体を digest に拘束する**(`_normalized_manifest_input` に反映 — **除外範囲をあとで広げること自体を検出する**)
3. **fail-closed にする** — **`k` が実際の履歴長を超える**(= 記録が削除された)/ **`m` の snapshot が存在しない** / **宣言が読めない** / **`k < 2` や `m < 1` のような退化値**、これらはすべて **red**。保留・skip・中立を認めない(設計書 7.7-3 `:609-612` は既存の検査にも掛かる)

**とくに 3 が要。`k > len(history)` を黙って切り詰めると、記録の削除が通ってしまう。**

**`k` と `m` は「現況の件数」ではない。** **生成時点の記録を固定する値**であり、**受理記録が増えても動かない**。これは本タスクが外そうとしている「現況のリテラル固定」とは性質が異なる([research.md](research.md) の「守りたいもの / 偶然そこにあるもの」の区別)。

### 2-4. 既存の drift 変異テストの扱い(**1 周目 P1-2 の反映**)

**`tests/test_frozen_archive_case_runner.py:212 test_prepare_case_rejects_appended_history_record` は、履歴へ 1 件足して digest による拒否を要求する試験である。** 2-3 の設計とは**同時に満たせない**。初稿のステップ 5 の合格条件「drift 変異テスト 5 本が依然として red」は、この 1 本について**誤りだった**。

**採る形**:

| 試験 | 変更 |
| --- | --- |
| `:212`(履歴の追記) | **正例へ反転** — 「**適法な追記では digest が不変**」を要求する `test_prepare_case_accepts_appended_history_record` にする |
| **新設** | **既存履歴の書き換え**(先頭 `k` 件のいずれかの `reason` を変える)で **red** |
| **新設** | **固定済み snapshot の削除**で **red** |
| `:147` `:167` `:193` `:237`(検査器・生成規則・ケース定義ほか) | **無変更。red のまま** |

**つまり drift 検出は 4 本 + 新設 2 本 = 6 本になり、1 本だけが正例へ反転する。**

### 2-5. ケース 12 の定義(**1 周目 P1-3 の反映**)

**初稿は「ケース 12 で 11 ケースの結果不変を実測する」と書いたが、現行のケース形式では表現できない。** `CaseDefinition` は **1 ケース = 1 action + 前版/現版の終了コード**であり(`tests/fixtures/frozen-archive-cases/runner.py:60-75`、`:946`)、runner は各ケースを個別に構築する。**「12 件目の遷移表」では 11 ケース分の照合にならない。** また**現版の `recorded_exit_codes` は `null`** である(`manifest.json:31`)。

**採る形: ケースを足さず、`tests/test_frozen_archive_case_runner.py` に試験を 1 本足す。**

```
def test_appended_history_record_does_not_change_case_outcomes():
    """受理記録を 1 件足しても 11 ケースの終了コードが変わらないことを実測する。"""
    before = {case.case_id: _run_case(case, source_root) for case in MANIFEST.cases}
    appended_root = _with_appended_acceptance_record(source_root)   # 合成の適法な追記を 1 件
    after = {case.case_id: _run_case(case, appended_root) for case in MANIFEST.cases}
    assert after == before
```

**主張できること**: **この合成入力 1 件について、11 ケースの終了コードが追記に不感応である。**

**主張できないこと**: **あらゆる追記に対する不感応**(5 節 4 に明記)。

### 2-6. 採らなかった案

| 案 | 採らない理由 |
| --- | --- |
| **`history` と `history-snapshots/` を digest から丸ごと外す**(**初稿**) | **既存履歴の改竄と既存 snapshot の削除が検出されなくなる**(2-3 の 1・2 — 1 周目 P1-1) |
| **digest を現況から再計算する** | **drift 変異テストが恒真になる。** digest 照合は drift 検出の**唯一の機構**([research.md](research.md) 2) |
| **digest を廃止する** | 同上。台帳が「黙って陳腐化するを落ちて気づくへ変えた」有効な手当てとして記録している(`harness-evaluation.md:4135`) |
| **`trees` から `contracts/tenant_boundary` を外し 8 資産を `files` に列挙** | **資産ファイルの新設を検出しなくなる**([research.md](research.md) 6) |
| **各 PR が digest を再導出する(列挙型)** | #74・#87・#443 が同じ作業を繰り返す。**本タスクの目的そのものに反する** |

### 2-7. 併せて必要な変更

| 対象 | 変更 |
| --- | --- |
| `runner.py` の `load_manifest`(`:228-229`) | `corpus_inputs` のキー集合 exact-set に `pinned_prefixes` を追加 |
| `runner.py` の `_normalized_manifest_input`(`:354-361`) | `corpus_inputs` のハードコードに `pinned_prefixes` を反映(**固定の改竄を digest で拘束する**) |
| `runner.py` の `corpus_input_digest`(`:411-423`) | **先頭 `k` 件の履歴**と**固定済み `m` 件の snapshot** を digest 対象にし、それ以降は対象外にする |
| `tests/test_frozen_archive_case_runner.py:47-58` | `files` / `trees` の exact-set assertion を `pinned_prefixes` 込みへ更新 |
| `tests/test_frozen_archive_case_runner.py:212` | **正例へ反転**(2-4) |
| `manifest.json` | `corpus_inputs.pinned_prefixes`(`history_record_count` と `snapshot_names`)の追加と `digest` の再導出 |

## 3. 7.7 の射程(**人間の判断を仰ぐ — ステップ 5 の前提ゲート**。1 周目 P1-4 の反映)

**設計書 7.7 は「検査が『この資産は変わらない』と主張するとき」全般に掛かり(`:520`)、基準の集合・対応の変更と削除を明記している(`:535` `:555`)。テストを除く文言は無い。**

**初稿は「対象外」と提案したが、1 周目 P1-4 で「二理由はいずれも条文上の除外条件ではない」と指摘された。** 実際、「テストの期待値だから」も「現行の `.py` 走査の対象外だから」も、**条文が定める除外ではなく当てはめである。** 指摘を受け入れ、**本書は結論を出さず、両分岐の作業を書いて人間に委ねる。**

**この判断は実装ステップ 5 の前提ゲートである。** 判断が出るまでステップ 5 へ進まない(ステップ 1〜4 は判断と独立なので先行できる)。

### 判断(**2026-10-01・山田正輝 — 分岐 A「7.7 の対象外」**)

**決め手は 7.7-2 の記録形式そのものである。** v2 受理記録の `change.before` / `after` は **4 側面の exact-set**(`scripts/frozen_history.py:20-27`):

```
declaration / movement_policy / external_snapshots / asset_snapshots
```

**どれも「資産が自分について宣言した基準」の側面で、テストの期待値を書く枠が無い。** つまり分岐 B を採ると「記録を 1 件追記する」ことが**構造的にできない**。できるようにするには `ASPECT_NAMES` へ第 5 の側面を足すことになり、**7.7 の版繰り上げを伴うハーネスの大改修**になる。

**記録形式が表現できない変更は、その記録制度の対象ではない** — これが採った読みである。

**補強(いずれも当てはめであり、条文の裏付けではない)**:

- 7.7-1〜7.7-4 の主語は一貫して**資産の `baseline_control`**(置き場・更新の記録・委任)
- 7.7 を強制する機構(`scripts/check_frozen_baselines.py:34`)は **`*.py` だけを走査**し、JSON の manifest を見ていない
- **反証法**: 7.7 がテストの不変主張全般に掛かるなら、**リポジトリ中のあらゆる exact-set assertion の変更に 7.7-2 の記録が要る**ことになる(`tests/test_core_guard.py` の exact-set、`tests/test_ci_wiring.py`、識別値の exact-list…)。**ハーネスは現にそう運用されていない**

**条文で決着をつけるには 7.7 の改訂(`/finalize-doc`)が要る。本タスクでは行わない。**

### 分岐 A の作業 — **追加作業なし**

[plan.md](plan.md) のステップ表と DoD をそのまま実行する。

**ただし、分岐 B の実質的な利点(変更が黙って起きないこと)は記録で担保する**:

1. **本書 2-3 に「何を・なぜ・いつ落としたか」を表で残す**(記載済み)
2. **worklog に実測つきで記録する**
3. **運用評価台帳の `## 候補` へ「7.7 の射程がテストの期待値に及ぶか条文が決めていない」を立てる** — **これは条文の穴そのものであり、いずれ別の PR が同じところで止まる**

### 分岐 B — **7.7 の対象と判断した場合**

**`corpus_inputs` の構成変更は「基準の集合・対応の変更」(`:535` `:555`)に当たるものとして扱う。** 次を追加する。

| 追加作業 | 典拠 |
| --- | --- |
| **7.7-2 の記録を 1 件追記する** — 何を・なぜ・いつ動かしたか。**既存記録は削除しない** | 設計書 `:583-607` |
| **記録の置き場を決める** — `corpus_inputs` は資産の `baseline_control` ではないため、**既存の置き場が無い。** 置き場の決定自体が 7.7-1 の射程に入る | 設計書 `:527-581` |
| **記録を検査が要求する形にする** — 抜くと red になること。**7.7-3 により、確かめられないときは不合格にしなければならない**(保留・skip・中立は不可) | 設計書 `:609-612` `:617` |
| **実装ステップを 1 件追加**(記録の追記と検査の結線)/ **DoD に「記録を抜くと red になる」を追加** | — |

**分岐 B は射程が増える。** **ただし「#82 の解除を優先して分岐 B を別タスクへ切り出す」案は採らない**(**TSK-444 の申し出 2026-10-01**)。理由: **分岐 B を切り出すと corpus digest が手つかずで残り、#82 は解除されない。** 解除されないなら切り出す意味が無く、**7.7-2 の記録の置き場という判断だけが先送りになる。** **他タスクの都合で設計判断を分割しない。**

**したがって人間へ諮るのは分岐 A か B の二択である。**

## 4. 射程外(送り出す)

| 事項 | 理由 | 送り先 |
| --- | --- | --- |
| `acceptance_id` の `#79` / `#81` literal 11 箇所(`test_check_tenant_boundary_bypass.py`) | **いまは落ちない。** 将来その番号を名乗る受理記録が出たら一斉に red。`runner.py:698-713` は動的回避で解いており非対称が残る | 新規起票 |
| `tests/test_frozen_archive.py:225-228` の無力な assertion | 退化実装が素通りする。**本タスクの標的(リテラル固定)とは別の欠陥** | 新規起票 |
| `design.md:120`(448)の「一意参照 18 件」が未更新 | 448 は閉じている | 新規起票 |
| 448 の `research.md` の典拠の行ずれ(`:605`→`:607` / `:900`→`:895`) | 同上 | 同上 |

## 5. 主張しない範囲

1. **11 箇所以外に現況依存のリテラルが無いことを、全リポジトリについては主張しない。** 走査は `tests/` `scripts/` `contracts/` に限る([research.md](research.md) 1)
2. **#74・#87・#443 が同じところで落ちることは未実測**(契約上そうなるという推論)
3. **TSK-444 の 48 件の内訳と本調査の 11 箇所の対応は、444 の突き合わせ報告による。** 合計が合わない点は未解明([research.md](research.md) 未解決)
4. **corpus digest の「追記不感応」は、2-5 の合成入力 1 件について実測したもの。** **あらゆる追記に対する不感応は主張しない**
5. **7.7 の射程判断は当てはめであり、条文の裏付けではない**(3 節)
6. **独立オラクル(1-1)が単独で捕まえるのは退化と抽出漏れまで。** 分類誤りは既存の期待表照合が捕まえており、**オラクルの効力として主張しない**
7. **2-3 の prefix 固定が守るのは「生成時点に存在したもの」まで。** **生成時点より後に追記された記録の改竄は検出しない**(その記録は corpus の主張の外にある)
8. **固定済み履歴の「改竄を検出する」は、正規化した JSON 値についての主張である**(**実装の敵対レビュー 1 周目 P2**)。**先頭 `k` 件は JSON として読み直してから正規化するので、バイト列としての改竄(例: 重複キーの挿入)は digest を通る。** **この反例で製品の判定値が変わるかは未確認。**
9. **新規孤児 snapshot の検出は、現況テストの `test_current_unpinned_snapshots_are_referenced` が担う**(**実装の敵対レビュー 1 周目 P1 の是正**)。**corpus digest は固定一覧に無い snapshot を見ない。** **製品検査器(`scripts/frozen_archive.py`)は実 PR の比較元と HEAD を受け取って新規孤児を拒否するが、それは本タスクの変更範囲外である。**
