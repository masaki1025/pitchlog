---
feature: runtime-contract-switch
type: research
date: 2026-09-26
---

# 調査メモ: ランタイム契約の製品資産への切り替え(TSK-443 / TSK-424 PR B)

## 問い

1. PR B の契約(`docs/features/product-authz-surface/design.md` 9 節 `:588-603`)は、**いまの develop で実行できるか**
2. 履歴の生存先の 3 案 — **(a) 継承 / (b) 廃止(tombstone)/ (c) 暫定資産を削除しない形**(TSK-448 が追加)— は、条文・既存の決定・現行の検査器のそれぞれに対してどこで当たるか
3. 契約 9 節に書かれていないが、PR B で必ず触れることになる箇所はどこか

調査の担い手: spec-checker(条文と要件の突合)/ decision-tracer(決定の経緯)/ 実装構造(Explore)。
旧システムは関係しないので legacy-analyst は使っていない。報告どうしの食い違いと主要な主張は原典で再確認した(「裁定」の欄)。

## 結論(要約)

1. **暫定資産を削除する案は、いまの develop では必ず不合格になる。** (a) と (b) はどちらも削除を含む(9 節 3 項)。検査器は削除を 2 段で拒否する: `load_contract` が 7 資産を無条件に読む(`scripts/check_tenant_boundary_bypass.py:1348-1351`)/ 比較元にあって HEAD に無い資産を無条件で拒否する(`scripts/frozen_history.py:294-297`)。**削除を通す機構は TSK-461(`未着手`)に送られている**(TSK-448 `plan.md:58`・1 節)
2. **削除しない案 (c) は、凍結基準の検査は通せるが、U-T1 の二状態契約と正面から衝突する。** `backend/tests/test_authz_runtime_contract.py:135-139` は、製品資産 `ddl-elements.json` があって暫定資産のファイルも残っていれば `PROVISIONAL_ASSET_REMAINS` を立てる。PR A1 は「このテストは変えない」と宣言している(`product-authz-surface/design.md:312`)。**(c) を採るなら、U-T1 と TSK-424 が決めた二状態契約と、9 節 3 項を人間の判断で改める**ことになる
3. **条文(設計書 7.7)は 3 案のどれも明文では禁じていない。** 条文との距離がいちばん近いのは (a)。同じ基準を別の資産の宣言から引き続き参照するのは「削除」ではなく「置き場の変更」だからである(`dev-harness-design-2026-08-07.md:560-561`)。**ただし (a) は仕組みとして成り立たない。** 製品資産は検査器の走査範囲(`contracts/tenant_boundary/` 直下)の外にあり、その中に `baseline_control` を置いても検査器は読まない(`check_tenant_boundary_bypass.py:5758-5813`)
4. **9 節は PR B の作業を少なく見積もっている。** 書かれていない必須作業がある: 生成器が**存在しない**ので新しく作る / 製品資産の exact なキー集合の検査 / 関数の件数 33 のべた書き / `runtime_contract` の 8 フィールドの導出規則(**未定義**)/ `SOURCE_DIGEST` / 暫定資産を比較元にしている未発効状態の照合 / テスト 7 本前後(詳細は 3 節)
5. **要件書に上位根拠は無い。** 法源は設計書 7.7 と 10.1・10.2 だけで、要件書 4.0-2 も NFR-012 も根拠にならない。正本の追随は `data-model.md:2846` の 1 行と変更履歴 1 行、`docs/README.md` で、ゲートは 7.6-3 前段(PR レビュー)で足りる

**→ 計画の最初に人間が決めることは「削除するか、しないか」である。** 選択肢の比較は 4 節。

## 詳細と典拠

### 1. PR B の順序条件の由来と、その前提の変化

- **「PR B は 7D の後」の理由は 1 つだけ明文化されている**: 「暫定資産の削除は、凍結基準を動かす行為である(7.7-1)。削除記録を検査する機構が無い(既知欠陥 **7D**)。**7D を開けたまま削除はしない**」(`product-authz-surface/design.md:601`)。PR を 4 本に分けた判断(★8・人間の判断 2026-09-24)は `product-authz-surface/plan.md:43`・`design.md:653`・`docs/worklog/2026-09-24-product-authz-surface.md:18-26` にある
- **TSK-431 が develop に入れた 7D は最小限だけ**: 比較元 ∪ HEAD を走査し、比較元にあって HEAD に無い資産は無条件で不合格にする。記録の形は決めていない(`docs/features/tenant-boundary-baseline/design.md:147-151`・`:175`)
- **TSK-448 は PR B を開かないと決めた**(`feature/frozen-history-7d-remainder` の `plan.md:32-38`。未マージ)。理由は、`load_contract` が 7 資産を必須入力として読むため、退去は「実行できない」か「検査が空洞になる」かの二択になるから(同 `design.md:36-51`)。**「PR B が削除を選ぶ限り TSK-461(調査の時点の文書では「TSK-452」) を待つ。削除しない形なら待たない」**(同 `design.md:535`)
- **→ 「7D の後」は「7D が閉じれば削除できる」を前提にした条件で、その前提は崩れている。** 新しい順序条件は、削除する場合は TSK-461(退去の機構)、削除しない場合は無し(同 `plan.md:58`・`:169`)。
- **【Notion で確認 2026-09-26】Notion の TSK-452 は無関係のタスクで、ステータスは `取り下げ`**(題名「要件書の定義の穴を埋める — H/E/K/B・成績計上フラグの外延・終了判定の細部(TSK-236 の開始条件)」)。調査の時点で TSK-448 の文書が「TSK-452」と書いていたのは番号の衝突だった。**その後、退去の機構のタスクは TSK-461 として起票され(2026-09-26 10:04Z・`未着手`)、TSK-448 の文書も TSK-461 へ訂正済み**(448 `plan.md:38`・`:58-63` — 計画レビュー 1 周目 P2-1 で確認)

### 2. 3 案の判定

#### 2-1. 条文(設計書 7.7 — `docs/development/dev-harness-design-2026-08-07.md`)

- **削除も「動かす」に含む**(`:557`)。**ただし、同じ基準を別の資産の宣言から引き続き参照する場合は「置き場の変更」**(`:560-561`)
- **削除のとき**: 凍結対象が 1 つも残らないなら宣言から取り除き、対応が残るなら基準の宣言を残す(`:574-576`)。**取り除いたことを表す宣言を残さない。記録は 7.7-2 の履歴が持つ**(`:577`)
- 7.7-2: 1 行為につき 1 記録。取り除くときも記録が要る。履歴は追記のみ(spec-checker 報告 `:581-605`)
- 7.7-4: 何を凍結するか、同一性の粒度、受理単位は各資産が定める(同 `:617-622`)

| 案 | 条文上 | 論点 |
| --- | --- | --- |
| **(a) 継承** | **適合** — `:560-561` の「置き場の変更」に当たる。条文との距離がいちばん近い | 9 節 4 項の (a) は**暫定資産の削除を含む**(9 節 3 項)ため、1 の検査器の拒否に当たる。**加えて、製品資産は凍結の走査範囲の外にある**(`check_tenant_boundary_bypass.py:5758-5813` — `contracts/tenant_boundary/*.json` だけを列挙する)ので、製品資産に `baseline_control` を置いても**検査器は読まない**。9 節の合格条件(`:598`「base の旧資産と HEAD の生存先を exact に突き合わせる」)には検査器の改修が要る |
| **(b) 廃止** | **条件付きで適合** — tombstone が**履歴だけ**を持つなら `:577` に当たらない(`:577` の後段「記録は 7.7-2 の履歴が持つ」)。tombstone に `baseline_control` を残すと `:578-579` に当たる | 削除の拒否に当たるのは (a) と同じ。tombstone を `contracts/tenant_boundary/` に置くと追加資産として検査されるので、定数とディレクトリの一致テスト(`tests/test_check_tenant_boundary_bypass.py:2497-2505`)にも当たる。**`:574`(対応が残らない)と `:575`(対応が残る)のどちらに当たるかは条文から読み切れない** — この資産の射影の外部ファイル 3 件は、他の 6 資産とも共通である(`runtime-authz-contract.json:19-23`) |
| **(c) 削除しない形** | **適合しうる** — TSK-448 の読み: PR B で消えるのは「暫定的な値」で「凍結する対象」ではないので、`:575` の「対応が残る」の正規の扱いになる(448 `design.md:285-298`) | **凍結基準の検査は、いまの機構のまま記録 1 件で通る**(448 `design.md:535`・実装構造の報告 D-4)。**ただし U-T1 の二状態テストに当たる**(`test_authz_runtime_contract.py:135-139`)。9 節 3 項(削除する)とも、PR A1 の「既存テストは変えない」(`product-authz-surface/design.md:312`)とも矛盾する |

- `superseded_by` のような退役を表す宣言が `:577` に当たるかどうかは、**条文に書かれていない**。448 は「当たる可能性がある」としているが(448 `design.md:273`)、条文上の根拠は示していない
- 別の系列には正規の退役経路がすでにある: `contracts/authz/frozen-baselines.json` の `series_retired`(`scripts/check_frozen_baselines.py:77-88`・`:995-1002`)。**`tenant_boundary` 側の資産単位の機構にだけ退役経路が無い**(spec-checker 報告)

#### 2-2. 削除したときの検査器の判定(コード)

- **定数に残したまま消す**: `load_contract` の `:1350` で読みに行き、`:233` で ContractError になる(終了コード 2)
- **定数から外してから消す**: ディレクトリの列挙に比較元の資産として現れ、`frozen_history.py:296-297`「比較元に存在した資産を削除できない」で落ちる。**既存テスト `tests/test_check_tenant_boundary_bypass.py:2660-2700` がこの負例を固定している**
- **「定数を外す迂回」は効かない**: 母集団は定数ではなく、ディレクトリそのもの(比較元 = `ls-tree`、HEAD = `iterdir`)(448 `design.md:275-283`。実装構造の報告 D-1 でも独立に確認した)

#### 2-3. 削除しないとき(c)に動くもの

- 本文を変える(`provisional:false` など)と `baseline_value` の軸が動く。必要になるのは次のとおり: `runtime_contract_revision` を 4 から 5 へ上げる / `base-allowlist.json`(履歴の authority)に v2 記録を 1 件追記する / `history-snapshots` を追加する。**暫定資産自身の history には追記できない**(`frozen_history.py:519-527`)
- 射影の外部ファイルに製品資産を足すと `frozen_target_mapping` の軸が動く。ただし `_validate_baseline_control` は `included == all_top_level_fields` を固定で要求し(`check_tenant_boundary_bypass.py:439-442`)、テストは 7 資産の external_files が同じ 3 件であることを exact に assert している(`tests/test_check_tenant_boundary_bypass.py:2508-2525`)
- **検査器・`frozen_history.py`・`ci.yml` を 1 バイトでも変えると、7 資産すべての射影が動く**。7 資産とも revision を上げ、同期しているモジュール(`repository_contract.py`・`tenant_context_contract.py`・`runtime_contract.py`)も追随させる(コミット `a75549c0` の本文)。**PR B で検査器に触れるかどうかで、作業の量が大きく変わる**

### 3. 9 節に書かれていない必須作業(どの案でも生じる)

| # | 事実 | 典拠 |
| --- | --- | --- |
| 1 | **生成器が存在しない。** `runtime_contract.py` は「生成モジュール」と名乗っているが、実態は手で同期している。U-T1 から未解決の P1 として申し送られている(生成器のパス・入力・決定的な整形・`--check` 相当の CI コマンドの固定) | `scripts/`・`backend/src` を検索して 0 件(再確認済み)/ `docs/features/tenant-boundary-enforcement/design.md:637` / `product-authz-surface/research.md:134` |
| 2 | **製品資産のトップレベルのキー集合が exact に縛られている。** `pending_switch`・`provisional_contract_additions` が必須で、**`runtime_contract` を足すと不合格になる** | `scripts/check_authz_catalog.py:4250-4271`(再確認済み) |
| 3 | **関数の件数 33 がべた書きされている**(`!= 33` で CatalogError)。テストも `== 33` と `PROVISIONAL is True` を assert している | `check_authz_catalog.py:3962`(再確認済み)/ `backend/tests/test_authz_product_function_acls.py:179-186` / `backend/tests/test_authz_product_staging.py:152` |
| 4 | **未発効状態の照合は、暫定資産を比較元にしている**(staged の保護対象 == 暫定資産 ∪ 宣言済みの追加分)。**暫定資産のファイルがあるときだけ走る**。削除すれば黙って消えるので、保証をどこへ引き継ぐかを決める必要がある | `check_authz_catalog.py:4089-4167`・`:4321-4322` |
| 5 | **`runtime_contract` の 8 フィールドの導出規則が定義されていない。** 8 フィールドを定めているのはテストの `_asset_snapshot` だけ。`runtime_contract_revision` の初期値と `dangerous_endpoint_fixtures` は、製品の DDL 要素からは導けない | `test_authz_runtime_contract.py:87-124`・`:232-243` / U-T1 `design.md:340` |
| 6 | **`SOURCE_DIGEST` も差し替え対象**(9 節 2 項は挙げていない)。製品側では `runtime_contract` の object の digest になる | `runtime_contract.py:10` / `test_authz_runtime_contract.py:163-164` |
| 7 | **関数の件数**: 暫定資産は 33 件。migration のトリガ関数は 37 件。製品資産の関数は 38 件(トリガ 37 + `rls_helper` 1)。**`runtime_contract.py` の `PROTECTED_FUNCTIONS` を 37 件にするか 38 件にするかは未決** | `runtime-authz-contract.json:274-440` / `ddl-elements.staged.json:1020-`・`:1803` |
| 8 | **保護スキーマ**: テストが `set(PROTECTED_SCHEMAS) == {"public"}` を求める。製品資産のスキーマは `public` と `authz_private` の 2 つ | `test_authz_runtime_contract.py:192` / 実装構造の報告 C-1 |
| 9 | **U-T1 のロール真正性検査への影響は未検証。** `engine.py` は保護対象の所有者を危険ロールとして導く。製品資産へ切り替えると `pitchlog_shared_fn_owner` などが入る可能性がある | `backend/src/pitchlog/db/engine.py:259`・`:282-300` |
| 10 | **ロールの属性のキー名が違う**(暫定資産は `rol*`、製品資産は `superuser`・`bypass_rls` など)。書き写すときに対応付けが要る | 実装構造の報告 C-1(`ddl-elements.staged.json:9-54`) |
| 11 | 暫定資産のパスを直書きしている箇所: `check_tenant_boundary_bypass.py:74`・`check_authz_catalog.py:159-161`・`runtime_contract.py:9`・`backend/tests/test_authz_runtime_contract.py:16`・`backend/tests/test_authz_product_control_access.py:35`・`:108`・`tests/test_check_tenant_boundary_bypass.py:2670`。ci.yml には直書きが無い | 実装構造の報告 A-2 |
| 12 | 更新が要りそうなテスト: `test_authz_product_staging.py` / `test_authz_runtime_contract.py` / `test_authz_product_function_acls.py` / `test_authz_product_control_access.py` / `test_authz_product_classification.py` / `tests/test_check_tenant_boundary_bypass.py`(`:1165-1168`・`:2497-2525`・`:2660-2700`・`:3351-3377`)/ `tests/test_frozen_history.py:1066`(退去を実装する場合だけ) | 実装構造の報告 E |

### 4. 選択肢の比較(計画の最初に人間が決める)

| | X. 削除する((a) または (b)) | Y. 削除しない((c)) |
| --- | --- | --- |
| 待つもの | **TSK-461**(退去の機構 — `未着手`。1 節) | 無し |
| 条文との距離 | (a) がいちばん近い。(b) は条件付き | 448 の読みでは適合する。`superseded_by` を残すかどうかは条文に書かれていない |
| 改める既存の決定 | 無し(9 節のとおり) | **U-T1 の二状態契約**(`tenant-boundary-enforcement/design.md:343-344`)・**9 節 3 項**・**PR A1 の「既存テストは変えない」** — 人間の判断が要る |
| 凍結基準の検査器 | 改修が要る(TSK-461 の射程)。(a) なら走査範囲を製品資産へ広げることも要る | 現行の機構のまま、記録 1 件で通る(検査器に触れなければ) |
| 9 節の合格条件(`:598`) | 退去の機構の実装が前提 | 意味が変わる(削除が無いので「生存先」は同じパスになる)— 書き直しが要る |

**案 Z(分割)**: 3 節の 1〜10 の多く(生成器の新設、8 フィールドの導出規則、件数のべた書きの除去)は、削除するかどうかと関係なく必要になる。**生成器の新設だけを先の PR に切り出せば、暫定資産を入力にしたまま、今すぐ着手できる**。これは推論で、決定記録は無い。

### 5. 決定の記録と、履歴に残す値

- **v2 の受理(#78・#80)は、`base-allowlist.json` にだけ記録を追記した。** 暫定資産自身の history は v1 の 1 件のままで、`source_commit: PENDING_ACCEPTANCE`(`runtime-authz-contract.json:46`)と `approved_by/on = 未承認(PR #72 のレビュー待ち)`(`:66-67`)が残っている。**9 節 5 項が書くよう求めた事実(「PR #72 のマージ後も受理値へ更新されていなかった」)は今も成り立つ**
- **ただし「変更前の値」は 2 か所に分かれている**: ① 資産自身の v1 記録(PENDING のまま)、② authority が持つ現在の識別値 `runtime_contract_revision:4`(`base-allowlist.json:801-803`・`:824-826`)。**どちらをどう写すかは、9 節も 448 も定めていない**
- v2 は予約 marker を拒否する(`frozen_history.py:39-60`・`:1697-1737`)。退去の記録に `PENDING_ACCEPTANCE` を「変更前の値としてそのまま」載せるには、除外の追加が要る(448 `design.md:236`)
- **保護対象関数の漏れ 4 件**(0015・0016・0017・0024)は、`ddl-elements.staged.json:59-99` の `provisional_contract_additions`(`reason: provisional_contract_gap`)と `check_authz_catalog.py:168-179` に宣言されている。**「PR B へ申し送った」より先の決定は無い**(`product-authz-surface/design.md:346`)。カードは、削除記録にこの漏れを事実として書くよう求めている(Notion TSK-443 本文)

### 6. 要件とコア領域

- 要件書: テナント分離の上位根拠は **NFR-010**(`requirements-pitchlog-2026-07-22.md:846-850`)と **FR-034**(`:599`〜)。**ランタイム契約・凍結基準の規律に当たる FR/NFR は無い。** **NFR-012 は管理者操作の分離で、根拠にならない**(`:857-860`。`product-authz-surface/design.md:296` 付近の誤った典拠は TSK-445 が扱う)。**要件書 4.0-2 も根拠にならない**(設計書 `:900` の但し書き)。**要件書の改訂は不要**
- 正本の追随: `data-model.md:2846` に「ランタイム契約の切り替え = **TSK-443**(PR B)」と残件として明記されている(再確認済み)。PR B は同じ行・変更履歴 1 行・`docs/README.md` を更新する。**ゲートは 7.6-3 前段(PR レビュー)**。条文 7.7 自体を直す場合(`superseded_by` の扱いを書き足すなど)だけ、確定ゲートが要る
- コア領域: PR B が触れるパスはすべて**テナント分離**(`.claude/core-areas.json:307`・`:318-319`・`:363-365`)。`check_authz_catalog.py` と `ci.yml` は `guard_paths` にも当たる。**敵対レビューと人間の逐行確認が必須。** `core-areas.json` 自体の変更は不要な見込み(既存の glob で足りる)

### 裁定(報告の食い違い・再確認)

| 論点 | 報告 | 裁定 |
| --- | --- | --- |
| (a) の評価 | spec-checker: 条文との距離がいちばん近い / 実装構造: 検査器が読まない | **両立する。** 条文上は最も近いが、仕組みとしては成り立たない(2-1 の表) |
| 関数の件数 37 と 38 | spec-checker: 37 = 33 + 4 / 実装構造: 製品資産は 38 | **両立する。** トリガ 37 に `rls_helper` 1 を足して 38。どちらを保護対象にするかは未決(3 節の 7) |
| 条文の行番号 | 448 は `:574-579`・`:577` / spec-checker も同じ | 原典で確認: `:574` が「削除のとき宣言をどうするか」、`:577` が「取り除いたことを表す宣言を残さない」、`:560-561` が「置き場の変更」 |
| 二状態テスト | decision-tracer・spec-checker・実装構造の 3 本とも指摘 | 原典で確認: `test_authz_runtime_contract.py:135-139`(製品資産があれば暫定資産の存在だけで違反)・`:200-211` |
| 生成器が無い | 実装構造 | 原典で確認: `runtime_contract.py` を書き出すコードは `scripts/`・`backend/src` に 0 件 |

## 未解決・申し送り

1. **【人間の判断】削除するか、しないか**(4 節の X・Y。Z の分割を併用するかどうかも)
2. 退去の機構は TSK-461(`未着手`)。X を選ぶなら TSK-461 の完了が先(1 節)
3. **PR A2(TSK-442)とのマージの順序**: A2 は「`ddl-elements.staged.json` の差分 0 行」「最終パスを作らない」を不変条件にしており(`feature/product-authz-apply` の `plan.md:53`・`:87`・`:123`)、PR B の `git mv` は同じ資産を動かす。**A2 の後に B を置くのが自然**(推論)。A2 の plan `:47` は今も「PR B は 7D の後」と書いている
4. 3 節の 5(8 フィールドの導出規則)・7(37 件か 38 件か)・8(`authz_private` を保護スキーマに入れるか)・9(`engine.py` への影響)は、計画で決める
5. 「変更前の値」が 2 か所に分かれている件の写し方(5 節)
6. 台帳の候補 `docs/development/harness-evaluation.md:3923-3954`(単独メンテナのリポジトリでは PR の自己承認ができず、承認記録の出所が成り立たない)は、昇格の条件が「次に凍結基準を動かすタスク」になっている。**TSK-443 はこれに当たりうる**
7. 設計書 10.1 のジョブ表(`:834-845`)に `tenant-boundary-bypass` ジョブの行が無い(実 CI には `ci.yml:114` にある)。PR B で CI の配線を変える場合だけ、追随の対象になる(spec-checker 報告。補修するかどうかは人間の判断)
