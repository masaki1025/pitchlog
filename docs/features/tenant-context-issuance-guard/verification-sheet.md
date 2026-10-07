---
feature: tenant-context-issuance-guard
type: design
date: 2026-10-07
---

# 逐行確認シート: TSK-457(コア領域 — テナント分離)

ADR-001 により**人間の逐行確認が必須**。差分は 19 ファイル・+1744 / -14 行だが、
**製品コード・検査器・契約資産は 4 ファイル 129 行**で、残りはドキュメントとテストである。
本シートはその 129 行を 1 行ずつ並べ、**何を変えたか / なぜ / どのテストが固定しているか**を示す。

確認後に `/implement` のステップ 7(凍結資産 8 本の繰り上げと受理記録 1 件)へ進む。
**承認が先、記録はその後**(`change.after` を繰り上げ後の射影で算出するため)。

## 1. `backend/src/pitchlog/repositories/context.py`(+21)

| # | 変更 | なぜ | 固定しているテスト | 確認の観点 |
| --- | --- | --- | --- | --- |
| 1-1 | `TenantContextIssuanceCapability` を新設(`@final` + `__slots__ = ()` の空クラス) | 発行能力を**型として表現**する。ただし守っているのは型ではない(下記 1-3) | `test_issuance_capability_is_final` | 空クラスでよいか。状態を持たせる必要はないか |
| 1-2 | `_ISSUANCE_CAPABILITY = TenantContextIssuanceCapability()` をモジュール私有で 1 個だけ置く | 前例は `transaction.py:28` の `_HANDLE_CREATION_TOKEN` | — | **アンダースコア名が `ruff` で守られない**(`SLF001` は select に無い)。守るのは検査器の TB007 だけでよいか |
| 1-3 | `__init__` の署名に `issuance_capability` を足し、**`is not _ISSUANCE_CAPABILITY` で拒否** | **identity 判定**。型で判定すると同型の別実体を作られて素通りする | `test_tenant_context_requires_issuance_capability` / `test_tenant_context_rejects_another_issuance_capability_instance` | `is` であって `isinstance` でないこと。例外が `TypeError` でよいか |
| 1-4 | docstring に発行境界の段落を**追補** | 裁定 2(保証単位を機構の境界として書く) | `test_tenant_context_documents_unverified_authenticity_boundary` | **既存の 5 逐語が 1 文字も変わっていないこと**。「実行時に保証されている」と読める表現が無いこと |

**変えていないもの**: `_TENANT_CONTEXT_SECRET` / `_tenant_context_proof` / `_has_valid_integrity_proof` /
`@final` + `@dataclass(frozen=True, slots=True, init=False)` の 3 点セット。

## 2. `backend/src/pitchlog/repositories/binding.py`(+10)

| # | 変更 | なぜ | 固定しているテスト | 確認の観点 |
| --- | --- | --- | --- | --- |
| 2-1 | `isinstance(context, TenantContext)` → `type(context) is not TenantContext` | 4 強制点のうちここだけが**派生型を許していた**。他 3 箇所は exact | `test_all_tenant_context_enforcements_check_exact_type_and_proof` | **既存の例外メッセージが逐語のまま**であること(既存テストが固定している) |
| 2-2 | **発行証跡の検査を追加**(無いと通っていた) | TSK-444 の `P0-3` と同型。新しい発行経路を足すなら最弱点を残さない | `test_tenant_transaction_direct_call_rejects_invalid_context_without_sql` | 拒否が **`set_config` の前**に起きること(SQL 発行 0 件)。新しいメッセージの文言 |
| 2-3 | docstring の `Raises:` に「発行証跡不一致」を追記 | 2-2 の追随 | — | — |

**射程拡大の扱い**: これは DoD に無い既存コードの強化で、**人間の裁定 4(2026-10-06)で含めると決めた**もの。

## 3. `scripts/check_tenant_boundary_bypass.py`(+90)

### 3-A. 契約の読み込み(+47)

| # | 変更 | なぜ | 固定しているテスト | 確認の観点 |
| --- | --- | --- | --- | --- |
| 3-1 | dataclass に 4 フィールド / `_strict_keys` に 4 欄名 | 欄は exact-set なので足さないと落ちる | `test_generated_allowlist_matches_asset` | 欄名が資産・配布モジュール・テストで一致していること |
| 3-2 | **発行能力の 2 欄**: `pitchlog.` 前置 + 許可シンボル非空を要求 | 既存の発行証跡の秘密と**同じ強さ** | `test_issuance_capability_requires_nonempty_closed_symbols` | 既存 2 件と同じ検査になっているか |
| 3-3 | **発行入口の 2 欄**: 空を許す。両方空なら不活性 / 非空なら完全修飾名を要求 / **片方だけは `ContractError`** | U-M1 ステップ 8 が値を入れるまで不活性にする必要がある。既存の `_string` は空文字を拒むので専用の検証を書いた | `test_issuance_entrypoint_allows_empty_or_complete_pair` / `test_issuance_entrypoint_rejects_one_sided_pair` / `test_issuance_entrypoint_requires_fully_qualified_symbol` | **空を許す欄を混ぜたこと**の是非。片側だけを拒否する判定(`bool(a) != bool(b)`)でよいか |

### 3-B. 参照規則(+34)

| # | 変更 | なぜ | 固定しているテスト | 確認の観点 |
| --- | --- | --- | --- | --- |
| 3-4 | `protected` を 2 件 → 4 件(発行能力・発行入口を追加) | `visit_ImportFrom` / `visit_Name`(Load)/ `visit_Attribute` の 3 入口から呼ばれるので、**守る名前を増やすだけで import も registry 代入も拾える** | `test_issuance_capability_reference_outside_allowlist_is_red` | 新しい検出ロジックを書いていないこと |
| 3-5 | ループ先頭に **`if not symbol: continue`** | 発行入口が空のあいだ判定を一切行わない | `test_empty_issuance_entrypoint_does_not_trigger_reference_rule` | 空判定がこの位置でよいか |
| 3-6 | **新しい 2 件だけ**に許可モジュール判定を足す(`allowed_test_modules \| allowed_product_modules`) | **既存 2 件の許可条件を広げない**。広げると許可テストモジュール内の未許可関数から秘密へ到達できる | `test_existing_proof_references_remain_red_in_allowed_test_module` | **既存 2 件の挙動が 1 ミリも変わっていないこと**。条件式が 2 つに重複している点(整理するか) |
| 3-7 | 許可シンボルによる例外は従来どおり | `context.py` 自身の内部参照を通すため | `test_issuance_capability_reference_from_allowed_symbol_passes` | モジュール単位の制限に開ける例外がこの 1 つだけであること |

### 3-C. `getattr`(+16)

| # | 変更 | なぜ | 固定しているテスト | 確認の観点 |
| --- | --- | --- | --- | --- |
| 3-8 | `getattr` 判定に**発行能力だけ**を足し、許可モジュールからは通す | 現行は末尾一致で**無条件**に TB007 を出すため、1 要素足すだけだと許可モジュールからの `getattr` も拒否してしまう | `test_issuance_capability_reference_outside_allowlist_is_red`(`getattr` 形) | 既存 2 件の `getattr` 判定が変わっていないこと |
| 3-9 | **発行入口は `getattr` 側に足していない** | 計画書の保証文 7 のとおり**意図的に保証外** | `test_issuance_entrypoint_getattr_remains_outside_reference_rule` | 「足し忘れ」ではなく「意図的に閉じていない」と読めること |

## 4. `contracts/tenant_boundary/tenant-context-allowlist.json`(+8)

| # | 変更 | 値 | 確認の観点 |
| --- | --- | --- | --- |
| 4-1 | `issuance_capability_symbol` | `pitchlog.repositories.context._ISSUANCE_CAPABILITY` | 実体の名前と一致していること |
| 4-2 | `issuance_capability_allowed_symbols` | `["pitchlog.repositories.context.TenantContext.__init__"]` | **1 件だけ**でよいか(`context.py` 内部の参照はこの 1 箇所) |
| 4-3 | `issuance_entrypoint_symbol` | `""`(空) | **U-M1 ステップ 8 が値を入れる**。本タスクでは空が正しい |
| 4-4 | `issuance_entrypoint_allowed_symbols` | `[]`(空) | 同上 |
| 4-5 | `source_digest` の再計算 | — | **`contract_revision` は 10 のまま**(繰り上げはステップ 7) |

**変えていないもの**: `allowed_product_modules` は `[]` のまま。`:1178-1185` の **0 件必須の分岐は解除していない**(裁定 1)。

## 5. 併せて確認いただきたい 3 点

1. **保証の線**(`design.md` 1 節)。閉じるのは「発行能力と発行入口を allowlist 外が**直接その名前で**名指せない」ところまでで、**別名での再公開・`getattr` による発行入口の取り出し・由来が解決できない属性経由は閉じない**。これは `tenant-boundary-enforcement/design.md` 6-0「守らないもの 2」と同じ射程で、**撤回も縮小もしていない**(敵対レビュー 2 周目を受けた人間の判断)
2. **`.claude/core-areas.json` を 1 行も変えていないこと**。触る全ファイルが既存 glob に該当する。DoD の「ディレクトリ全体を足さない」を**何も足さないこと**で満たしている
3. **凍結ゲートがステップ 1 から赤であること**(`射影が動いた資産は識別値の更新が必要`)。計画書のとおりで、ステップ 7 で解消する

## 6. テストの母集団(「全件」の根拠)

| 主張 | 母集団の決め方 | 固定しているテスト |
| --- | --- | --- |
| 強制点はこの 4 箇所で全部 | **宣言集合(5 件)と、独立した発見規則が拾う集合の exact-set 一致**。内訳は強制点 4 + 理由付き免除 1(`_execute_operation`) | `test_tenant_context_reader_set_matches_enforcements_and_exemption` |
| 5 つ目が増えたら落ちる | **変異を当てて落ちることを確認**している | `test_fifth_tenant_context_reader_fails_declared_set_check` |
| 免除 1 件は安全 | **呼び出し元が `execute` だけ**であることを assert | `test_exempt_context_reader_is_called_only_by_execute` |
| 既存 112 負例が緑化していない | 負例台帳の exact-set(`EXPECTED_NEGATIVE_IDS`) | 負例ランナー 2 本 |

新しい負例 3 件: `C5_CONTEXT_REGISTRY_ISSUER` / `C5_CONTEXT_CAPABILITY_IMPORT` / `C5_CONTEXT_CAPABILITY_GETATTR`。
発行入口の 2 件は**負例台帳に載せていない**(ランナーが実契約を読み、発行入口が空で不活性のため red にできない)。
合成契約の単体テストで扱っている。

---

## 7. 追補: ステップ 1 の是正(2026-10-07・裁定 6)

初回の承認(2026-10-07)の後、全件検証で `tests/test_census_baseline_check.py` の 8 件が赤になることが分かり、
人間の裁定 6 で**センサス基準の反実仮想導出を記号単位の行差へ一般化**した。
是正は 2 コミット(`62bebb31` / `ffaee32b`)で、差分は 3 ファイル・+291 / -88 行。

**逐行確認が要るのは契約資産の 1 行だけ**である(残りはテストと設計書)。

| # | ファイル | 変更 | 確認の観点 |
| --- | --- | --- | --- |
| 7-1 | `contracts/tenant_boundary/census-baseline.json` | `pass_fail_mapping.predicates[1].derivation.substituted_from` を `anchor_materialized_tree` → `anchor_symbol_set_plus_scoped_signature_rows` へ(**1 行のみ**) | 既存の宣言**欄**を使っており、欄を増やしていないこと。`anchor.commit`・`contract_revision`・`allowed_symbols` は 1 文字も動いていないこと |

### 何が変わったか(機構)

反実仮想を **2 つに分けて測る**ようにした。

1. **新規記号の効果** — 共通記号の行は**現行値のまま残し**、anchor に無い記号の行と対応する正例 fixture だけを除いて測る
2. **署名差の効果** — 署名だけが異なる共通行を、**1 記号ずつ** anchor の行へ戻して測る

2 から抑止集合へ入れるのは、**その記号の製品モジュールに現れる・同じ記号の・TB005** だけ(3 条件の同時成立)。
帰属が記号・コード・モジュールの 3 点で絞られるため、**署名差が無関係な `removed` を吸収できない**。

### 緩めた線と、緩めていない線

| | |
| --- | --- |
| **通るようになった入力** | anchor と共通する記号について、**非空文字列の `signature` だけ**を変えた行(複数行可) |
| **引き続き拒否する入力** | 共通記号の削除 / 記号の重複 / **署名以外の欄の差**(`allowed_api_ids`・`fixture`)/ 欠落・空・文字列でない署名 |

### 敵対レビュー 1 周目(`P0` なし)

| 重み | 指摘 | 対応 |
| --- | --- | --- |
| P1 | `_allowed_symbol_product_path` が `__init__.py` を見ず、同名モジュールが共存すると誤帰属し得る | **両方を探し、2 つ見つかったら落とす**形へ。**現行 102 ファイルに重複は 0 件**で、現に成立する欠陥ではなく将来の罠 |
| P2 | 帰属の 3 条件が実装内の定数で、外しても落ちるテストが無い | `_scoped_signature_suppression` へ切り出し、**3 条件それぞれを外した変異で落ちるテスト**を追加 |
| P2 | 変異テストが行分割ヘルパーだけを見ている | 記号削除と許可 API 差は**測定入口を通した経路でも拒否される**ことを確認。署名差の end-to-end 帰属は全走査が 1 回増えるため求めない(docstring に明記) |
| P2 | 全走査が署名差の件数 +1 回 | **申し送り**(design.md 6 節)。現行 `n=1`・単独全走査 約 3.9 秒 |

**偽の緑を 1 件解消した**: 変異テストの `signature` ケースは、従来**本タスクの実変更**が同じ入口で先に落とすため通っていた。
実変更のある行を避けて合成変異を作る形へ直してある。

### 是正後の実測

| 検査 | 結果 |
| --- | --- |
| `uv run pytest tests/test_census_baseline_check.py` | **54 passed**(是正前 48・develop も 48) |
| `uv run pytest tests/` | **2862 passed / 34 failed** — 赤は**凍結ゲートと比較 corpus digest の連鎖のみ**(ステップ 7 で解消) |
| `uv run ruff check .` / `uv run ty check`(ルート) | green |
| backend `ruff format --check` / `ruff check` / `ty check` | green |
| backend `pytest`(非 DB) | 960 passed / 4 skipped |
