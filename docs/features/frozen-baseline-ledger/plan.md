---
feature: frozen-baseline-ledger
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-21・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3dd93b75e68781cd8859dcc2c1e4eb88
branch: feature/frozen-baseline-ledger
created: 2026-09-20
計画レビュー周回: 5        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 凍結基準を検査器から台帳へ移す — 最小実装(TSK-421)

## 1. 背景・目的

調査結果の正: [research.md](research.md)(2026-09-20)

- **Notion**: [TSK-421](https://app.notion.com/p/3dd93b75e68781cd8859dcc2c1e4eb88)。DoD との対応は 5 節末
- **上流**: TSK-386(取り下げ)→ 条文は **TSK-420**(設計書 v1.16・完了)/ 実装が本タスク
- **対象条文**: 設計書 **7.7**(4 項)

**なぜやるか**: 凍結基準が検査器のソースへ直書きされており、**基準を動かす作業と検査器を書き換える作業が区別できない**。7.7-1 は**行為に掛かる**ので現存の直書きは違反状態ではなく、本タスクは**能動的な移設**である。

**下流がブロックされている**: 要件書を改訂すると `ORACLE_INPUT_BASELINE_COMMIT` を進める必要が生じ、その行為に 7.7-1 が掛かる。宣言の実体が無いので **TSK-306(ブロック中)と要件書改訂 9 件**が待っている。**本タスクが移すのはこの定数である。**

## 2. 信頼モデル(最初に宣言する)

計画レビュー 3 周を通じ、指摘はすべて同じ形だった — **「計画が機構で X を保証すると書いているが X は保証されていない」**。正本の側は既にこの領域で機構が保証しきれないことを認めている:

- **7.7-4**: 本節は網羅性を保証しない。塞がらない経路を名指ししている
- **`docs/development/github-setup.md:48`**: **PR は head 側の workflow・スクリプトを実行する**(循環は既知リスクとして明記済み)

したがって本計画は次を**最初に**宣言する。

> **台帳の健全性は、人間のレビューと管理統制に載っている。機械検査は多層防御であって証明ではない。**

**機械が保証すること** — **ただし前提条件がある**(4 周目 `P1-1`):

> **下の保証はすべて「レビュー済みの検査器と workflow が、記述どおりに実行された範囲」で成り立つ。**`github-setup.md:48` が明記するとおり、**PR は head 側の workflow・検査器を実行する。これは初回に限らずすべての PR に及ぶ。検査器・workflow 自身の改変の遮断は機械では保証せず、全 PR のコア領域逐行確認が担う。**

| 保証対象 | 内容 |
| --- | --- |
| スキーマ | トップレベル / 各領域の exact-key。未知の `aspect`・`identity` は red |
| replay | `fold(changes) == 規範状態`(exact) |
| 追記のみ | base 側台帳との比較。**同数置換も検出** |
| 受理遷移 | 直前/直後の算出・event 整合の照合・`base.ref == develop` の限定 |
| fail-closed | 確かめられないときは非 0 終了。保留・省略・中立を出さない |
| 走査 | 未登録の出現 / 見つからない登録の双方向 |

**機械が保証しないこと**(明示的な非保証):

| 非保証 | 理由 |
| --- | --- |
| **ambient authority 経由の迂回の遮断** | 同一プロセスで戦略を動かす限り `open` / `Path.cwd()` / `sys.modules` / `subprocess` / import 経由の参照は残る。**この点について保証するのは、列挙した変異に対して red になることだけである** |
| **初回 bootstrap を機械的に閉じること** | base に台帳も検査器も無く、head の workflow と head の検査器が head の期待集合を評価する。**初回の信頼根は人間の逐行確認である** |
| **検査器・workflow 自身の改変の遮断**(**全 PR**) | `github-setup.md:48` の循環は初回限定ではない。**全 PR のコア領域逐行確認が担う** |
| **base の最新性** | event と checkout の整合は照合するが、CI 後に develop が進む経路は塞がらない。`github-setup.md:39` の三点一致手続が担う |
| **`pending_removal` が「必ず次回消える」こと** | 機械は base からの継承か削除しか許さない。**除去そのものは後続タスクによる管理統制** |
| 7.7-4 が名指しした経路 | 基準・値・置き場・対応・粒度を維持したまま比較結果を合否へ写す規則だけを変える経路 |

**「全経路を塞いだ」とは書かない。**先例: TSK-420 は隔離プロセスを作らず、有限の変異実測で初回可決している。

## 3. スコープ

### 射程縮小の経緯(PO 裁定 2026-09-21)

計画レビュー 1 周目 `P0×4 / P1×9 / P2×1`(非起因)→ 全採用 / 2 周目 `P0×4 / P1×4`(**全件起因**)。P0 が減らず是正案のコストが跳ね上がった(隔離プロセス + サンドボックス / 2 PR 分割)。台帳の既知の型「**強い述語が細部を無限に呼ぶ輪**」と判断し、**述語を弱めて射程を縮小する**打ち切りを行った(TSK-335 が「述語を弱めることが収束手段になった 1 例目」)。3 周目 `P0×4 / P1×3`(全件起因)だが**是正コストは撤回 1 件 + スキーマ追加 3 件へ低下**したため継続した。

### やること — **`oracle_input` 1 系列のみ**

| 系列 | 移設元 | 現在値 | なぜこれか |
| --- | --- | --- | --- |
| **`oracle_input`** | `scripts/check_authz_catalog.py:109` `ORACLE_INPUT_BASELINE_COMMIT` | `24ef4fcc…` | ① **戦略に git が不要**(bytes → JSON pointer 値)なので **`basis_commit` を渡さずに済む** ② 消費者が **1 箇所**(`:4984`)③ **TSK-306 のブロックを解くのはこの定数** |

あわせて **台帳・検査器・走査・負例基盤**を新設する(後続タスクの土台)。

### やらないこと

| 除外 | 扱い |
| --- | --- |
| **残り 4 件の移設** | 走査の allow-list へ `pending_removal: true` で登録 + **後続 4 タスクを起票**(ステップ 8) |
| **`H-85` の 2 段コミット解消** / **`corpus_versions` と digest 辺の削減** / **`ci.yml` の action pin 19 件** / **`check_authz_catalog.py:4034-4037` の受取先差分閉包の基準固定** | PO 裁定(2026-09-20)。台帳候補へ受け取り先を作る |
| **`contracts/authz/` の oracle 入力 8 資産・封印 6 資産・第 2 階層 3 資産** | **触らない。再封印しない** |
| **`backend/`** | `oracle_meaning` が射程外のため。2 リーダ問題も生じない |

## 4. 影響する正本

**機械突合の対象**(`scripts/check_plan_docs_sync.py` は `docs/` 配下の `.md` 正本のみ):

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/development/harness-evaluation.md` | **`H-85` へ実測追記**(`shared-preconditions.json` が記述に無い 1 件 / 連鎖 20 ファイル・最小 3 コミット / **本タスクの台帳化では 2 段は消えない**)+ **候補の新規追記**(射程外の受け取り先 / 「**記録の欠落を推定で埋めた**」型)+ 変更履歴 1 行。**`H-*` 新規採番なし・版上げなし** | PR レビュー |
| `docs/README.md` | 台帳行を現行化 | PR レビュー |
| 設計書 / 要件書 / `data-model.md` / `sync-protocol.md` / ADR-001 / ADR-004 / 改善台帳 / `github-setup.md` | **反映なし** | — |

**正本体系外・同一 PR で運ぶもの**(機械突合の対象外 — 本節と PR 本文の両方に明記):

| 分類 | パス |
| --- | --- |
| **新設** | `contracts/authz/frozen-baselines.json` / `scripts/frozen_baselines.py`(リーダ)/ `scripts/check_frozen_baselines.py` / `scripts/frozen-baseline-scan-allowlist.json` / `tests/frozen_negatives/` / `tests/test_frozen_negative_inventory.py` |
| **改修** | `scripts/check_authz_catalog.py`(`:109` 削除・`:4984`)/ `tests/test_ci_wiring.py` / `.github/workflows/ci.yml`(harness ジョブへ結線のみ)/ **`.claude/core-areas.json`**(**6.3-⑤ の敵対レビュー + 人間承認の対象。`check_plan_docs_sync` の除外対象なので機械突合されない**)/ `pyproject.toml` |
| **作業文書** | `docs/features/frozen-baseline-ledger/{plan,research}.md` / `docs/worklog/2026-09-20-frozen-baseline-ledger.md` |

## 5. 実装方針

### 重さ分類 = **コア領域**

`contracts/authz/*` は `.claude/core-areas.json` の tenant-isolation の `paths`。`scripts/check_authz_catalog.py` は `guard_paths` 収録済み。→ **敵対レビュー + 人間の逐行確認が必須**(設計書 6.3)。

### 戦略の設計

> **戦略の入力は、呼び出し側が `frozen_targets` のパスだけから読んだ不変な `{ファイルパス: bytes}` のみ。** キーは**純粋なファイルパス**(JSON pointer を含まない)。pointer の解決は戦略の中で行う。

**`oracle_input` は git を必要としない**(bytes → JSON パース → pointer の値)。したがって **`basis_commit` を渡さない**。

層: リーダ(台帳を読む)/ 素材収集(パス列 → `{path: bytes}`)/ 戦略(bytes → 識別値)/ 照合(戦略の戻り値 対 履歴末尾)。

### 台帳の置き場 — `contracts/authz/frozen-baselines.json`

| 論点 | 実測 |
| --- | --- |
| 差分閉包が `contracts/authz` を 3 パスに限る件 | `scripts/check_authz_catalog.py:4046-4062` で **early-return する**(`TSK-270-GROUP-2` が 0 件) |
| core-guard の照合 | `scripts/core_guard.py:224-226` は **`guard_paths` 完全一致 `OR` 領域 glob 一致** |
| 台帳 | 領域 glob `contracts/authz/*` で**既に一致** → `guard_paths` 登録は不要 |
| 新設の検査器・リーダ・allow-list・負例 | **どれにも一致しない** → `guard_paths` 登録が要る(**件数は機械導出。先置きしない**) |

**early-return が将来発火する条件**: base 側 claim に `TSK-270-GROUP-2` が存在すると台帳が許可 3 パス外として red になる。実装開始時と `/pr` 前に再確認する。

### 台帳のスキーマ(JSON specimen)

```jsonc
{
  "schema_version": 1,
  "asset_kind": "frozen_baselines",
  "acceptance": {                                  // 規範状態 ①
    "unit": "pull_request",
    "base_ref": "develop",
    "prior_state": "event.pull_request.base.sha",
    "posterior_state": "checkout_head",            // = refs/pull/N/merge
    "parent_check": {"first": "base.sha", "second": "head.sha"},
    "acceptance_id_source": "repository_and_pr_number",
                                                   // ステップ 1 で draft PR を先に作り番号を確定する(5 周目 P0-1)。
                                                   // head_ref 案は CLOSED PR の reopen / 同一ブランチからの別 PR で
                                                   // (acceptance_id, series) 一意制約に衝突するため採らない
    "self_reference": "none"
  },
  "movement_rules": {                              // 規範状態 ②
    "triggers": ["value_change", "replacement", "addition", "removal",
                 "location_change", "first_placement", "rule_self_change"],
                                                   // 閉じた enum・配列・重複禁止・順序不問(集合として扱う)
    "universal_lower_bound": ["set", "value", "placement",
                              "target_correspondence", "identity_interpretation"],
                                                   // 条文 7.7-1 の 5 軸。宣言はこれを縮小できない
    "additional_targets": {},                      // trigger -> series の exact-set。全 trigger 必須ではない(欠落 = 追加分なし)
    "self_change": {"trigger": "rule_self_change", "targets": ["*"]}
  },
  "implementation_bindings": {                     // 規範状態 ③(4 周目 P0-2 で保守的に拡大)
    "code_assets": [                               // 順序は path の昇順に固定・重複禁止
      {"path": "scripts/frozen_baselines.py",       "sha256": "<64hex>"},
      {"path": "scripts/check_frozen_baselines.py", "sha256": "<64hex>"}
    ],                                             // digest 対象 = ファイルの生 bytes(復号・改行正規化をしない)
                                                   // symlink は解決せず red。base/head 双方で計算する
    "strategy_keys": ["literal_commit_string/json_pointer_value"],
    "registry": {"path": "scripts/frozen_baselines.py", "symbol": "COMPARISON_STRATEGIES"}
  },
  "placements": {                                  // 規範状態 ④(fold で復元する)。値は Locator[]
    "oracle_input": [{"kind": "ledger_series", "path": "contracts/authz/frozen-baselines.json",
                      "series": "oracle_input"}]
  },
  "declarations": {                                // 規範状態 ⑤
    "oracle_input": {
      "frozen_targets": [
        "contracts/authz/oracle-seal.lock.json#/oracle_commit",
        "contracts/authz/ddl-elements.json#/oracle_context/oracle_commit"
        // … 6 資産分
      ],
      "identity": "literal_commit_string",
      "granularity": "json_pointer_value",
      "basis_series": "oracle_input"               // 自系列を指す。将来 A の基準を B が参照する形に備えた欄
    }
  },
  "history": [
    {
      "acceptance_id": "masaki1025/pitchlog#<pr_number>",
      "series": "oracle_input",
      "new_identity":   {"present": true, "values": [{"kind": "literal_commit_string", "value": "24ef4fcc…"}]},
      "prior_identity": {"present": true, "values": [{"kind": "literal_commit_string", "value": "24ef4fcc…"}]},
      "changes": [ /* aspect ごとの before/after。下記 */ ],
      "placement_change": {                        // fold 対象(4 周目 P0-3)。タグ付き locator
        "before": [{"kind": "python_assignment", "path": "scripts/check_authz_catalog.py",
                    "symbol": "ORACLE_INPUT_BASELINE_COMMIT"}],
        "after":  [{"kind": "ledger_series", "path": "contracts/authz/frozen-baselines.json",
                    "series": "oracle_input"}]
      },
      "moved": true,
      "reason": "…",
      "approved_by": "…",
      "approved_at": "2026-09-__"
    }
  ]
}
```

**規範状態は 5 つ**: `acceptance` / `movement_rules` / `implementation_bindings` / **`placements`** / `declarations`。

> **上は説明用の specimen であり、実装契約ではない**(4 周目 `P1-2`)。**ステップ 2 の成果物として、省略記号もコメントも無い完全な初期 JSON fixture と JSON Schema を置く。**そこで確定するもの: `frozen_targets` の exact-set 全 7 件 / `changes[]` の aspect 別の完全形と**初期不在を表す sentinel** / `values[]` の順序・重複・`kind` enum・値形式 / `sha256` の形式と digest 対象 / locator の `kind` enum / **allow-list 自体の schema** / `additional_targets` の JSON 型と参照整合。

> **production は 1 系列のまま。**`identity` / `granularity` / `basis_series` を「別の有効値へ変える」変異は **production schema に別の有効値が存在しない**ので作れない(`basis_series` は前任で複数系列があったから意味を持った欄)。→ **合成 fixture にだけ第 2 系列・第 2 strategy を置いて 4 要素の感度を検証する。**

#### `implementation_bindings`(3 周目 `P0-4` → 4 周目 `P0-2` で拡大)

`identity` / `granularity` の**意味は戦略コードが担う**。文字列を据え置いたまま戦略を「全 40 桁一致」→「先頭だけ比較」へ変えても差分が出ないのを塞ぐ。

**3 周目案(単一関数の source digest)では足りなかった** — 同じ関数本文から呼ぶ pointer resolver・JSON parser・registry・import 先を変えれば意味を変えられる。**これは ambient authority ではなくリポジトリ内の静的な「識別値の解釈変更」であり、7.7-1 が明示した下限なので非保証へ送れない。**

→ **保守的なコード資産 binding にする**:

- `code_assets` = **ファイルの生 bytes の SHA-256** の配列(戦略・registry・collector・pointer resolver を置く**すべてのファイル**)。復号も改行正規化もしない。**symlink は解決せず red**。並びは `path` 昇順・重複禁止。**base / head の双方で計算する**
- `registry` = registry を置くファイルと symbol
- **`code_assets` のどれか 1 ファイルでも変われば `implementation_bindings` の movement を要求する**

コメント変更まで movement になるが、「**保守的に扱う**」という方針と整合する。

#### `placements` と `placement_change`(3 周目 `P0-3` → 4 周目 `P0-3` で決定元を閉じる)

2 周目で `location` を `aspect` から外したところ置き場の記録欄が消え、3 周目で証拠欄を足したが**決定元が閉じていなかった**(locator が無タグ / 導出アルゴリズム未定義 / fold 対象外なので履歴間の連続性を検査できない)。

→ **`placements` を規範状態 ④ として持ち、fold 対象に戻す**:

- **タグ付き locator に統一**。`{"kind": "python_assignment", "path", "symbol"}` / `{"kind": "ledger_series", "path", "series"}`。`kind` は閉じた enum で、**未知は red**
- **`placement_change.before/after` も同じ型**
- **fold で復元する**(`前回 after == 次回 before` と、**fold 末尾の `placements` == head 実体**を検査)
- **同時に、base / head の実体から機械導出した値との一致も要求する** — fold だけだと偽申告が通り、導出だけだと連続性が見えない。**両方を課す**
- **placement 導出関数と registry も `code_assets` の対象**にする

#### `bootstrap`(3 周目 `P0-2` の是正 — 撤回して人間を信頼根にする)

> **機械的に循環を切ったとは主張しない。**初回は base に台帳も検査器も無く、head の workflow と head の検査器が head の期待集合を評価する(`github-setup.md:48` が明記する循環)。**初回 bootstrap の信頼根は人間の逐行確認である。**

そのうえで機械側は次を行う:

- **検査器側の期待集合を、移設元だけでなく初期の規範状態 5 つ全体まで閉じる**
- 初回記録の `prior_identity` は **base ツリーの当該ソースから機械抽出した値**と一致すること
- **2 回目以降の台帳不在は必ず red**
- 通常更新は **base 側の規範状態だけで現在の遷移を評価する**(head 側は次回から有効)

**「マージ後は到達しない」は強すぎるので書かない。**正確には「**台帳を含む base SHA で新たに評価される develop 宛 PR では到達しない**」。台帳導入前の event/base SHA を使う workflow 再実行は到達しうる。

**人間確認の突合元は項目ごとに違う**(4 周目 `P1-1` — 「初期規範状態の全期待内容を base source と突合」は**実行不能**だった。新設する戦略とその digest は base に存在しない):

| 規範状態 | 突合元 |
| --- | --- |
| `acceptance` | **base** の CI 設定と `github-setup.md` の運用 |
| `movement_rules` | **base** の設計書 7.7 |
| `declarations` と初期識別値 | **base** の資産と旧定数 |
| `implementation_bindings` | **head の新設コード**(base に存在しない) |
| `placements.after` と消費結線 | **final head**(実消費はステップ 5 で結線されるため) |

→ **bootstrap の信頼根となる確認は、ステップ 3 で行ったうえで、ステップ 7 の最終 head でも再実施する。**

#### `history` のレコードと 7.7-2

| 7.7-2 の要求 | 対応 |
| --- | --- |
| 識別値は複数あればそのすべて | `values` を配列に |
| 1 つも無いときはその旨 | `{present: false, values: []}`。**`null` を使わず「履歴の先頭」の概念を持たない** |
| **何を変えたか + 変更前後の内容** | `changes[]`(fold 対象)+ **`placement_change`**(機械導出の証拠欄) |
| 事実・理由・承認者・承認日 | `moved` / `reason` / `approved_by` / `approved_at`(ISO 実在日) |
| 追記のみ | base 側台帳との比較。**同数置換も検出** |
| 取り除くときも記録 | `new_identity.present: false` + `changes[aspect=series_retired]`(**本タスクでは使わない。合成 fixture で検証**) |

**`changes[].aspect` は閉じた enum**: `frozen_targets` / `identity` / `granularity` / `basis_series` / `movement_rules` / `implementation_bindings` / `acceptance` / `series_retired`。**未知は red。**`aspect` ごとに `before`/`after` の型を固定(配列 / 文字列 / オブジェクト)。**同一 batch 内での同一 aspect の重複・競合を禁止。**

**replay 不変量**: **`fold(changes[] ∪ placement_change over history) == 規範状態 5 つ`(exact)**。**`placements.<series>` は `Locator[]`**(`placement_change.before/after` と同じ型)。**fold は `changes[]` と `placement_change` の双方を消費する** — `placement_change` は `placements` 専用の遷移入力であり、`changes[].aspect` には `placements` を置かない(二重入力にしない)。`prior_identity` / `new_identity` / `moved` / `placement_change` は**機械導出して申告値を使わない**。食い違えば red。

**`acceptance_id`** は `repository` + PR number から機械導出する。**PR 番号は履歴を作る前に確定させる** — **ステップ 1 で draft PR を作る**(5 周目 `P0-1`。`head_ref` は CLOSED PR の reopen や同一ブランチからの別 PR で一意にならない)。同一受理は **1 batch で原子的に fold**。`(acceptance_id, series)` 一意 / global aspect は batch 内 1 回 / 全レコードの before が同じ base 状態を指す。

### 走査(3 周目 `P1-2` の是正 — 数え方を訂正)

**40 桁と 64 桁の両幅。**判定は本文の**部分一致**。識別単位は **`(パス, 値)` の組**。未登録の出現も red・見つからない登録も red。

**実測ベースライン**(`grep -rnoE '\b[0-9a-f]{40}\b' scripts/ tests/ backend/tests/ --include=*.py` / 同 `{64}`):

| | 出現 | **一意な `(パス, 値)` 組** |
| --- | --- | --- |
| 40 桁 | 14 | **10**(恒久 6 + 凍結基準 4) |
| 64 桁 | 1 | 1(凍結基準) |

> **出現 14 のうち 5 出現が同一組**(`tests/test_verify_nfr021_evidence.py` の同じダミー値)。**出現回数と識別子数を混同しない。**

**本タスクの終端**: 40 桁 **13 出現・9 組** / 64 桁 **1 出現・1 組** / **allow-list 10 組 = 恒久 6 + `pending_removal` 4**。

### `pending_removal`(3 周目 `P0-1` の是正 — 閉塞を解く)

2 周目までの「base に台帳が無いときだけ許す」は、**マージ後は base に台帳があるので残り 4 件が即 red** になり、**後続 4 タスクへの分割と両立しなかった**。

3 周目の「head ⊆ base」案も**初回で閉塞した**(4 周目 `P0-1`)— base に台帳も allow-list も無いので base の pending は空集合で、`4 組 ⊆ 空集合` は必ず偽。さらに**集合包含だけでは `true→false` を検出できない**(head の pending 集合からキーが消えるので包含は成立し、**直書きを残したまま恒久 allow-list へ昇格できる**)。

→ **2 つの規則に分ける**:

**(a) bootstrap 規則** — **base に台帳と allow-list がともに無いときだけ**適用。**final head の pending 集合が残存 4 組の exact-set である**ことを要求する。

**(b) 通常規則** — **集合ではなくエントリ遷移を比較する**。base の各 pending 項目について許すのは次の 2 つだけ:

1. `path` / `value` / `reason` / `pending_removal: true` が**すべて同一のまま継承**
2. **エントリごと削除**(= 直書きが消えたこと。走査が裏を取る)

**追加 / 値変更 / パス変更 / `false→true` / `true→false` はいずれも red。**`true→false`(恒久化)は**直書きを残したまま債務を消す経路**なので明示的に禁じる。

**「必ず次回消える」とは主張しない**(2 節の非保証)。除去は後続タスクによる**管理統制**である。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ | 合格条件(その時点の成果物だけで判定する) |
| --- | --- | --- |
| 1 | **draft PR の作成と退行の物差し。** **先に draft PR を作り `acceptance_id` の PR 番号を確定する**(5 周目 `P0-1` — 履歴を作る前に番号が要る)。続いて `tests/frozen_negatives/` を作り、`tests/test_frozen_negative_inventory.py` が **pytest collection から node ID を導出**して変異表と**双方向 exact-set 照合**。`frozen_negative` marker は**導出済み全件に必須の属性**。走査ベースラインを worklog へ実測記録 | **draft PR が存在し PR 番号が確定している** / 導出集合と変異表が exact-set 一致 / **marker 無しの負例を足しても検出される** / **消した複製で red かつ足した複製でも red** / 識別単位が node ID の完全一致 / **走査を「出現」と「一意な組」の両方で記録**(コマンド併記)/ `uv run pytest tests/` green |
| 2 | **台帳と検査器の器**(git 非依存)。スキーマ exact-key・**`movement_rules` / `implementation_bindings` の exact-schema**・レコード形状・承認欄・**replay(規範状態 5 つ・`changes[]` と `placement_change` の双方を消費)**・**`aspect` の閉じた enum と型固定**・**`placement_change` の機械導出**・dispatch・**戦略への `{ファイルパス: bytes}` 受け渡し**・fail-closed | 検査器 exit 0 / **初期記録の識別値が作業ツリーのソース定数と逐語一致することを機械が照合**(検査器に値を書かない)/ 未知 `aspect`・未知 `identity` が red / **`movement_rules` の各項目を 1 つずつ削除・縮小する負例が red** / **戦略の内容 digest を変えると `implementation_bindings` の差分として履歴を要求する** / **`placement_change` の記録値が 2 木からの導出と食い違うと red** / 「履歴が無い」と「直前が無い」の混同が red / `prior_identity`/`new_identity`/`moved` が導出値と食い違うと red / 負例 **+14** / **変異表を worklog へ**・復元のバイト一致検証 |
| 3 | **受理遷移検査と CI 結線。** 直前 = `base.sha` / 直後 = checkout された `HEAD` / **親の照合** / **`base.ref == develop` の限定** / **`acceptance_id` の機械導出と batch 原子性** / **bootstrap(期待集合を規範状態 5 つ全体まで閉じる・2 回目の台帳不在は red)** / 追記のみ(同数置換も検出)/ 到達可能性 / 7.7-3。**イベント別に別コマンド。**harness ジョブへ結線 | 負例 **+8** / **受理遷移検査の経路に `skip`/`pass`/`neutral` が 0 件** / **`base.ref != develop` で受理検査が走らない** / **2 回目の台帳不在が red** / **必須チェック 9 件のまま** / `test_checkout_fetch_depth_is_exact_for_every_job` が無改訂で green / **CI 条件の手元再現を全段実行** / **人間の逐行確認①(暫定 — その時点で存在する項目に限る)** — **base に存在する項目だけを突合する**(`acceptance` = base の CI 設定と `github-setup.md` / `movement_rules` = base の設計書 7.7 / `declarations` と初期識別値 = base の資産と旧定数)。**`implementation_bindings` と `placements.after` はこの時点では突合できない**(head の新設コード / 実消費はステップ 5)ので**ステップ 7 へ送る**。**初回 bootstrap の信頼根となる確認はステップ 7 で完成する** + worklog へ実施記録 |
| 4 | **走査と allow-list の実装**(実走査はまだ有効化しない — 4 周目 `P0-1`)。40/64 両幅。**bootstrap 規則**(base に台帳と allow-list がともに無いときだけ・final head の pending が残存 4 組の exact-set)と**通常規則**(エントリ遷移の比較。継承または削除のみ。**`true→false` も red**)を実装する。**この時点では `ORACLE_INPUT_BASELINE_COMMIT` がまだソースに在る**(走査対象は 11 組)ので、**実走査の有効化はステップ 5 の後**とし、本ステップは**合成 fixture 上での検査**に限る | 合成 fixture で **bootstrap 規則 / 通常規則の双方が期待どおり**(継承 ok・削除 ok・追加 red・値変更 red・パス変更 red・`false→true` red・**`true→false` red**)/ 負例 **+6** / docstring・f-string 埋め込みの複製で red / AST 完全一致へ変異すると当該負例が落ちる / **64 桁を外すと `check_docs_status.py:63` を見逃す** / **実リポジトリに対する走査はまだ結線していない**ことを明示 |
| 5 | **移設 — `oracle_input`。** `check_authz_catalog.py:109` 削除・`:4984` を台帳読み取りへ。**あわせてステップ 4 の走査を実リポジトリへ結線する**(この時点で走査対象が final の 10 組になる) | `check_authz_catalog.py` exit 0 / 走査 **40 桁 14→13 出現・10→9 組**・**allow-list 10 組**(恒久 6 + pending 4)/ **台帳の値を誤った値へ変えると red** / **宣言の 4 要素すべてに独立した変異**(`frozen_targets` を 1 件外す → ①検査器が red かつ ②その対象を改ざんしても検知されなくなる / `identity`・`granularity`・`basis_series` は**合成 fixture の第 2 系列・第 2 strategy**で感度を示す — **production は 1 系列なので別の有効値が存在しない**〔4 周目 `P1-2`〕)/ `:4984` を no-op へ変異させると既存負例が落ちる / 台帳読み取りを定数へ戻すと**走査が red** |
| 6 | **`.claude/core-areas.json` へ未保護の新設物を登録**(6.3-⑤)。**全新設ファイルを `matched_paths()` へ通して未一致集合を機械導出**(件数を先置きしない) | 導出結果と登録内容が exact-set 一致 / `core_guard.py` が全新設ファイルを検知 / **台帳は領域 glob で既に一致するので登録しない** — **glob を外した複製では検知されなくなることを実測** / 既存 guard テスト green / **人間の逐行確認②** + worklog へ実施記録 |
| 7 | **最終コア差分の逐行確認を worklog へ記録して 1 コミット。****履歴の最終変更より後に置く**(4 周目 `P0-4`)。**bootstrap の信頼根となる確認を final head で再実施する**(`implementation_bindings` は head の新設コード、`placements.after` と消費結線は final head としか突合できない — 4 周目 `P1-1`) | worklog に最終差分全体の `対象= / 範囲= / 方法=` がある / **5 つの規範状態それぞれについて、突合元(base / head / final head)を明記した確認記録がある** / **確認後に差分が発生したら再確認する**ことを記録 |
| 8 | **正本反映とクローズ。** `H-85` へ実測追記 + 候補の新規追記 + 変更履歴 1 行。`docs/README.md` 現行化。**後続 4 タスクを起票**。**カードの DoD を現行化**。worklog 締めと `/pr`(**ステップ 7 の記録を PR 本文へ転記**) | `check_docs_status.py` / `check_plan_docs_sync.py` exit 0 / **`H-*` 新規採番なし・版上げなし** / **後続 4 件が起票され二重起票が無い** / **射程外 4 件の受け取り先が台帳の候補にある** / **最終 HEAD で CI 条件再現を全段 + base から統合ブランチを作って feature を `--no-ff` マージし全件実行** / **差分閉包の early-return 条件を再確認** |

## 6. DoD(受け入れ基準)

- [ ] **`ORACLE_INPUT_BASELINE_COMMIT` の直書きが 0 になり、台帳から読まれている**(走査 40 桁 14→13 出現・10→9 組。**出現と組を分けて記録**)
- [ ] **残り 4 組が `pending_removal` として登録されている。bootstrap 規則(base に台帳と allow-list がともに無いときだけ)と通常規則(エントリ遷移の比較・継承または削除のみ・`true→false` も red)が分かれている。**後続タスク 4 件を起票
- [ ] **宣言 4 要素すべてについて、変えると挙動が変わることを変異で示す**(`frozen_targets` は production・他 3 要素は**合成 fixture の第 2 系列**で)
- [ ] **比較を no-op にすると落ちる。**戦略には `{ファイルパス: bytes}` だけを渡し **`basis_commit` を渡さない**
- [ ] **2 節の信頼モデルどおりに保証/非保証が書き分けられている。**「全経路を塞いだ」「機械的に循環を切った」「必ず次回消える」と書いていない。**保証には「レビュー済みの検査器と workflow が記述どおり実行された範囲」という前提条件が付いており、検査器・workflow 自身の改変の遮断は全 PR の逐行確認が担うと明記している**
- [ ] **`acceptance_id` が実装開始時に確定でき、PR イベントから一意に再導出できる値である**(PR 番号を使わない)
- [ ] **ステップ 2 の成果物として、省略の無い完全な初期 JSON fixture と JSON Schema がある**
- [ ] **7.7-4 の委任 4 項を台帳が定めている**
- [ ] **`movement_rules` が exact-schema で定義され、下限を縮小できない**
- [ ] **`implementation_bindings` が `code_assets`(戦略・registry・collector・pointer resolver を置く全ファイルの生 bytes SHA-256)で閉じており、どれか 1 ファイルの変更が movement を要求する**
- [ ] **7.7-2 の 4 要求を満たす。**「何を変えたか + 変更前後の内容」は `changes[]` と **`placement_change`**(機械導出の証拠欄)で満たす
- [ ] **replay が規範状態 5 つを復元する。**`aspect` は閉じた enum で型が固定。導出値は申告値と食い違えば red
- [ ] **`placements` が fold で復元でき、`前回 after == 次回 before` と `fold 末尾 == head 実体` の両方を検査している。**locator はタグ付きで `kind` は閉じた enum
- [ ] **受理の前後状態が `--no-ff` と整合する**(直前 = `base.sha` / 直後 = synthetic merge / 親の照合 / `base.ref == develop`)
- [ ] **bootstrap の期待集合が規範状態 5 つ全体まで閉じている。人間の逐行確認は突合元を項目別に分けており**(`acceptance`・`movement_rules`・`declarations` = base / `implementation_bindings` = head / `placements.after` と消費結線 = final head)**、ステップ 7 の final head で再実施している。2 回目の台帳不在は red**
- [ ] **負例母集団が pytest collection から導出されている。**両方向の変異 / baseline green assert / 期待エラー文の逐語 assert / 負例 ↔ 変異の 1:1 対応表
- [ ] **`guard_paths` の登録内容が機械導出した未一致集合と exact-set 一致**
- [ ] **CI 条件の手元再現**を実行してから出す
- [ ] コア領域の**敵対レビューと人間の逐行確認**(ステップ 3・6 + **ステップ 7 の最終コア差分全体**)

### Notion カード DoD との対応

| カードの DoD | 本計画での対応 |
| --- | --- |
| 凍結基準の直書き 4 件が 0 になる | **本タスクは `oracle_input` 1 件のみ**(PO 裁定 2026-09-21)。残りは `pending_removal` + 後続 4 タスク。**クローズ時にカードを現行化** |
| 4 件それぞれについて変異で示す | `oracle_input` について宣言 4 要素すべてに実施 |
| 比較を no-op にすると落ちる | 実施 + **非保証を 2 節で限定** |
| 7.7-4 が委任する 3 つ | **4 項**(条文は受理の単位を含む) |
| 決定元が宣言 1 つに閉じている | `movement_rules` + `implementation_bindings` |
| `STEP2_BASE_REVISION` の履歴 / `AUTHZ_GUARD_BASE_REVISION` の非統合 / `_expected_step2_meaning_body` | **後続タスクへ。**なおカードは非統合の比較相手を `oracle_meaning` と書くが、値が同じなのは `authz_step2_base` との間。クローズ時に現行化 |
| コア領域の敵対レビューと逐行確認 | 実施 |

## 7. テスト計画

| 種別 | 内容 |
| --- | --- |
| **単体** | 台帳スキーマ・`movement_rules`・`implementation_bindings`・記録・replay・`aspect` 型・`placement_change`・走査・allow-list・受理遷移・bootstrap |
| **故障系** | **fail-closed 負例群**(7.7-3): 台帳欠落 / JSON 破損 / 未知の `identity` / 未知の `aspect` / `.git` 不在 / base 解決不能 / **親の照合失敗** / **2 回目の台帳不在** / 到達不能 commit。**いずれも非 0 終了であることを assert** |
| **退行** | `check_authz_catalog.py` の既存テストが変更前と同じく green。ステップ 1 で先に測る |
| **越境 / E2E / 一致性** | **反映なし** — 製品コードを 1 行も書かない。`backend/` を触らない |
| **変異** | 各負例に最低 1 つの変異が対応することを表で固定。**レビュー依頼の前に自分で測り、実測結果表を依頼文本体に貼る** |
| **静的** | 40/64 両幅の走査(**出現と一意な組の両方**)/ `oracle_input` の固定値が実装側に 0 件 / **エラー文の一意性** |

**負例が空洞でないことの証明**: 母集団を **pytest collection から導出** / 識別単位を **node ID の完全一致** / **両方向の変異** / **baseline green assert** / 期待エラー文の逐語 assert + 文言の一意性走査 / **負例 ↔ 変異の 1:1 対応表**。

**CI 条件の手元再現**(ステップ 3・8): 前任は**ローカル 1394 passed が CI で 1 件落ちた**。(A) CI の workspace は detached HEAD で `refs/heads/*` が空 / (B) `git clone` は元の `refs/heads/*` しか写さない → **(A) を clone すると `origin/develop` が存在しない**。scratchpad 内で再現し、**`ci.yml` から `run` を機械抽出してそのまま実行**。**synthetic merge の親も再現**。最終再現は **base から統合ブランチを作って feature を `--no-ff` マージ**。

**回すコマンド**:

```
uv run ruff check . && uv run ty check && uv run pytest tests/
uv run python scripts/check_authz_catalog.py && uv run python scripts/check_docs_status.py
uv run python scripts/check_frozen_baselines.py --invariants-only
uv run python scripts/check_frozen_baselines.py --acceptance --base <base.sha> --head <HEAD>
uv run python scripts/check_plan_docs_sync.py --plan docs/features/frozen-baseline-ledger/plan.md --base origin/develop
uv run python scripts/core_guard.py
```
