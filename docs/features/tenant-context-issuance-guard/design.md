---
feature: tenant-context-issuance-guard
type: design
date: 2026-10-06
---

# 詳細設計: TenantContext の発行境界

計画書 [plan.md](plan.md) 4 節から参照される詳細設計。調査の典拠は [research.md](research.md)。

## 1. 発行境界の保証単位(正式な宣言)

この宣言は `../tenant-boundary-enforcement/design.md` の 1-1 と 6-0 へ**逐語同文で追補**する。
既存の 4 箇所の逐語同文ブロック(条件 5 の保証単位)には**触れない**。

> **保証するもの**
>
> 1. 有効な `TenantContext` は、`pitchlog.repositories.context` が私有する**単一の発行能力**を
>    実引数に受けた構築からしか得られない。能力を渡さない構築・同型の別実体を渡した構築は
>    実行時に失敗する。判定は型ではなく identity で行う
> 2. 発行能力を名指すコードは、資産が列挙するモジュール
>    (`allowed_test_modules | allowed_product_modules`)**または資産が列挙する許可シンボル**の
>    中にしか置けない。import・属性参照・`getattr` のいずれでも、それ以外からの名指しは TB007 になる
> 3. **発行入口のシンボル**(資産が名指す発行関数)も同じ制限を受ける。ただし発行入口の 2 欄が
>    空のあいだは判定が働かない。したがって allowlist 外のモジュールは、発行能力を名指すことも、
>    発行入口が設定された後はそれをその名前で import して registry へ登録することもできない
>
> **保証しないもの**
>
> 4. **同一プロセス内で発行能力の導出経路へ到達する任意コード**。発行能力は同一プロセス内の
>    攻撃者に対する信頼境界ではない。これは発行証跡について既に置いた宣言と同じ境界であり、
>    本機構はそれを**撤回も縮小もしない**
> 5. **静的検査の母集団の外**。検査器が見るのは変更行であり、変更されない既存行は見ない
> 6. **構築された値の真正性**。従来どおり API 層(TSK-217 / U-A1)の責務
> 7. **名前が現れない転送**。本機構が追加する参照規則の照合は名前の直接比較(完全修飾名または
>    末尾名)であり、起源追跡はしない。別名に再公開した発行関数の持ち出し・`getattr` による
>    発行入口の取り出し・由来が静的に解決できない属性経由の呼び出しは**いずれも閉じない**。
>    これは 6-0「守らないもの 2」と同じ射程である。**既存の条件 5 の保証は 1 文字も縮まない** —
>    構築シンボルについては再輸出写像による起源解決が従来どおり働く

## 2. 3 枚の線

| 線 | 何で守るか | 守らないもの |
| --- | --- | --- |
| **実行時** | identity(`is` 比較)。同型の別実体でも落ちる | 能力を受け取った後のコード |
| **静的** | 名前。発行能力を名指せる場所が閉集合 | 変更行の外・名前が現れない転送 |
| **型** | 注釈。`ty` と読み手のためだけにある | **守っていない**(型は信用しない) |

裁定 1 の「capability 型」は、**型で守れという指示ではなく、能力を型として表現せよという指示**として読む。
守っているのは identity と名前である。

## 3. 「`registry[k].make_context(t)` 形が閉じる」の定義

呼び出し行が赤くなることではない。**発行能力と発行入口を、allowlist 外のモジュールが
直接その名前で名指せないこと**を指す。閉じる場所は呼び出し側ではなく名指す側である。

**なぜ列挙で閉じないか**: 「すべての抜け道」を条文の閉じた一覧で捉えようとすると、
敵対レビューが 1 周に 1 件ずつ出し続けて終わらない(`../../development/harness-evaluation.md:4014`。
U-T1 テナント境界が 4 例目で、有効だった手当ては**脅威モデルを明文化して線を引いた**こと)。
本タスクでも 1 周目「import 転送」→ 2 周目「別名再公開」と同型の指摘が続いたため、
**人間の判断で線を引いて打ち切った**(2026-10-06)。

## 4. 採らなかった案

| 案 | 採らなかった理由 |
| --- | --- |
| **`__new__` 封鎖 + private factory**(前例 `cache_invalidation.py:267-291`) | 検査器 `:4540` が `TenantContext.__init__` をハードコードで免除しており、資産の `integrity_proof_factory_allowed_symbols` も同シンボルを指す。この 2 つを追加で動かす必要がある。`copy` / `pickle` も閉じられる利点はあるが、それらは正当に発行された文脈の複製であって偽造ではない |
| **フレーム内省**(`sys._getframe` で呼び出し元モジュールを同定) | リポジトリに前例ゼロ。デコレータでフレームがずれる。同一プロセス内コードは `exec` + 細工した `globals` で詐称でき、**信頼境界にならないのに境界であるかのような保証文を誘発する** |
| **新しいモジュール allowlist 欄の新設** | U-M1 に 2 箇所の登録を強いる。既存の `allowed_test_modules \| allowed_product_modules` の再利用で足りる |
| **TB008 の新設**(構築シンボル等が呼び出し以外の値の位置に現れたら赤) | 発行能力の名前を守るだけで import・registry 登録が閉じる(右辺は Load 文脈)。負例が 3 本 → 10 本に増え、誤検出の面も広がる |
| **起源追跡による別名の追跡** | `_FlowProvenance` を使えば別名も閉じられるが、TSK-440 が同じ領域で 7 周回っており収束に時間がかかる。§3 のとおり線を引いた |

## 5. 申し送り

### U-M1 ステップ 8 へ

1. **発行入口の 2 欄に値を入れる**。`issuance_entrypoint_symbol` は発行関数の完全修飾名、
   `issuance_entrypoint_allowed_symbols` は非空。**片方だけの設定は `ContractError` で拒否される**
2. **発行関数には、リポジトリ内で一意な固有名を選ぶ**。照合は末尾名でも一致するため、
   他モジュールの無関係な同名の関数・変数と衝突すると誤検出になる。
   設定時に**全行走査で衝突 0 件**を確認し、それをステップ 8 の合格条件に入れること
3. **発行モジュールを `PRODUCT_APPLICATION_PATHS`**(`../../../tests/test_check_tenant_boundary_bypass.py`)
   **へ追加する**。この一覧は固定列挙で、漏れると全行走査の母集団から外れる
4. U-M1 が行うのは「資産に 1 行」ではない。**0 件必須の分岐の解除**・その固定テストの改訂・
   `source_digest` と `contract_revision`・凍結資産の受理記録・発行モジュールの実体が要る
5. **越境アクセステスト(NFR-019b)はステップ 8 で発効する**。本タスクは経路を作らないため未発効だが、
   未発効は網羅の免除ではない

### U-X5(一括移行)へ

**移行は発行モジュールの利用者ではない。** 移行は専用ロール + `BYPASSRLS` で設計され
(裁定 A-3・2026-09-08)、`set_config` 方式は却下済み(`../../design/data-model.md:316`)。
移行実装は `backend/` 配下に置かれ静的検査の母集団に入るため、
移行コードが `TenantContext` を構築しようとすれば検査が赤になる。これは守りとして正しく働く。

### 他の担当へ

- `../ua1-team-auth/design.md:264`・同 `plan.md:110`・`../../design/data-model.md:16` が
  `TenantContext` の生成を γ(TSK-469)の射程と書いたままになっている。
  裁定 b'(2026-10-05)で U-M1 ステップ 8 へ移った。**現行化が要る**
- 移行バッチの監査ログの書き先 `admin_operation_logs` が
  `../../../contracts/authz/product/migration-batch-role.json` の `write_targets` に無い。
  裁定 A-3 は「このロールでの接続と一括投入を操作ログに残す」と定めている → **TSK-349 の担当へ**

## 6. ステップ 1 の是正: センサスの共通行差(2026-10-07・裁定 6)

`TenantContext.__init__` の署名 pin は製品定義への追随として必要であり、anchor と共通する
`allowed_symbols` の行に差が生じる。センサスの反実仮想は、anchor の**記号集合**を使って
現行行を記号単位で分け、次の 2 つを独立に測る。

1. anchor に無い記号の行と対応する正例 fixture だけを除く。共通行は現行値のまま残す
2. 署名だけが異なる共通行を、**1 記号ずつ** anchor の行へ戻す。ここで帰属できるのは、
   その記号の所属する製品モジュールに現れる、同じ記号の TB005 だけとする

この方式を `derivation.substituted_from = anchor_symbol_set_plus_scoped_signature_rows`
と宣言し、テストがその値を検証してから反実仮想を構築する。既存の宣言欄を使うため、
宣言フィールド全数表の範囲も変わらない。

個別測定の和集合だけを抑止集合とし、共通行の署名差を新規記号の効果へ混ぜない。
共通行の署名以外の差、または anchor の共通記号を現行から削除した場合は拒否する。
署名の合成変異は当該記号の差として認識し、許可 API の合成変異はその記号・欄を示して
拒否する。現行 checker による製品定義と署名 pin の一致検査は従来どおり働く。

退けた案は、anchor を現行へ繰り上げる案(反実仮想の比較元を失う)、旧署名 pin を維持する案
(製品定義との契約不一致)、共通行を一括して anchor 行へ戻す案(複数の行差が混ざり、
無関係な `removed` まで吸収し得る)、共通行をすべて現行値のまま残す案(署名差によって
消えた実際の TB005 を説明できない)、特定の署名差だけをテストにハードコードする案
(宣言からの導出にならない)である。

署名差が `n` 件なら製品ソースの全走査は `n+1` 回になる。現行 102 ファイルの単独全走査は
約 3.9 秒で、`n=1` の現状では許容できる。署名差が増えたときは、対象ファイルだけを
計測する方式を検討する。

## 未解決・検討メモ

- `_check_integrity_reference` の新しい 2 件の許可判定が、条件式の形で重複している。
  まとめても挙動は変わらないが、4 件それぞれ別に持たせるという設計意図は読み取りにくくなる。
  整理するなら PR レビューで判断する

## 7. ステップ 1 の是正 2 件目: DB テストの派生型構築(2026-10-08・PR #101 の CI)

### 事象

PR #101 の CI(`backend` ジョブ)が `TypeError` で 1 件赤になった。

```
FAILED tests/db/test_tenant_transaction_scope.py::test_scope_rejects_non_exact_tenant_context_subclass
  - TypeError: TenantContext.__init__() missing 1 required positional argument: 'issuance_capability'
1 failed, 1336 passed, 4 skipped
```

当該テストは `derived_type(_TENANT_ID)` と旧シグネチャで `TenantContext` の派生型を構築して
いた。ステップ 1 で `__init__` に発行能力を必須化したため、**テスト本体へ到達する前に**
落ちていた。

### 是正

同一ブランチの `backend/tests/test_authz_tenant_binding.py` が既に解いている形へ揃えた。

```python
context = make_tenant_context(_TENANT_ID)
derived_context = cast(TenantContext, object.__new__(derived_type))
object.__setattr__(derived_context, "tenant_id", context.tenant_id)
object.__setattr__(derived_context, "_integrity_proof", context._integrity_proof)
assert derived_context._has_valid_integrity_proof() is True
```

**最後の assert が本体**である。これが無いと、拒否されたのが exact 型検査のためか証跡検査の
ためかを区別できず、テストの主張が空洞になる。`_tenant_transaction` と
`_TenantTransactionScope.__enter__` はいずれも exact 型検査 → 証跡検査 → `Session` 生成の順で
並んでいるので、証跡が有効であれば拒否は exact 型検査に帰属する。

逐語 match「TenantContext が無い」と、`created_sessions == []` /
`observed_statements == []` の 2 つの空集合 assert は 1 文字も変えていない。

### 敵対レビュー(sol xhigh・6 軸)

**P0 / P1 / P2 いずれもゼロ。** 軸ごとの判定は次のとおり。

| 軸 | 判定 | 要点 |
| --- | --- | --- |
| 主張の空洞化 | されない | `@final` は実行時の継承禁止ではなく、生成しているのは実際の派生型 |
| 拒否の帰属 | されない | 証跡 assert だけでは不十分だが、exact 型検査が証跡検査と `Session` 生成に先行する |
| 証跡の写し | されない | 証跡は秘密と `tenant_id.bytes` のみから計算し、型やインスタンス識別を含まない |
| 未初期化スロット | されない | 現行のフィールドは 2 つで、両方を設定している |
| 同型の見落とし | されない | `backend/tests/db/` の他 20 箇所はすべて `make_tenant_context` 経由 |
| 逐語性 | されない | match と 2 つの空集合 assert は差分で変更されていない |

### 申し送り(軸 4)

**`TenantContext` にフィールドまたは構築時の検証処理が増えたら、この構築形は再確認が要る。**
`object.__new__` は `__init__` を飛ばすので、新しいフィールドは未初期化のまま残る。
現行は `tenant_id` と `_integrity_proof` の 2 つで、テストは両方を設定している。

### 見逃した理由(検証の母集団)

共有開発 DB が消失しているため、ローカルの検証は一貫して `--ignore=tests/db` で回していた。
**この層は 6 ステップのあいだ一度も評価されていない。** 非 DB の件数は最後まで 960 passed の
まま動かず、件数でも終了コードでも差が出なかった。台帳の既存候補「検証コマンドを人が選ぶと、
CI が走らせるコマンドとの差分が黙って残る」へ 9 例目として記録し、対応案 (h) を足した
——**実行できないことは、静的に探せないことを意味しない**(本件は
`grep -rn "TenantContext(" backend/tests/db/` の 1 回で的中する)。

## 8. ステップ 7: 凍結基準の受理(2026-10-09)

PR 番号が確定したので、保留していた受理記録を書いた。`acceptance_id` は
`masaki1025/pitchlog#101`、`approved_by` / `approved_on` は人間が与えた値をそのまま置いた
(**この 2 欄は `scripts/frozen_history.py:1521-1523` が非空文字列と ISO 日付の形しか見ない
純粋な人間の申告**で、機構は突き合わせない。`acceptance_id` だけがマージ時に
GitHub event の `{repository.full_name}#{pull_request.number}` と照合される)。

### 編集順序

射影は他の資産の内容を取り込むため、**順序を違えると自分の書いた値が自分で腐る**。

1. 8 本の識別値(`frozen-inputs.json` は据え置き — 射影に検査器を含まない唯一の資産)
2. 各資産の `source_digest`
3. 配布モジュール 3 本(`tenant_context_contract` / `repository_contract` / `authz/runtime_contract`)の revision と `SOURCE_DIGEST`
4. `base-allowlist.json` の `baseline_control.history` へ受理記録 1 件(11 件目)
5. **最後に** `tests/fixtures/frozen-archive-cases/manifest.json` の `corpus_inputs.digest` を再 pin

### `base-allowlist.json` の射影は他資産の bump に連動する

ドライランで出した `base-allowlist.json` の受理後射影 `9791f9a629…` は**誤っていた**。
正しい値は `be5c884cdb2e71cbaa223f1abbb6cb061f9f82f12cc52edce47f033f3902cc0f`。

原因は `base-allowlist.json` が top-level に **`inventory` 欄で `db-api-inventory.json` の
`sha256` を pin している**こと。`db-api-inventory.json` の `inventory_revision` を 9 → 10 へ
上げると pin した hash が変わり、**`base-allowlist.json` 自身の射影も動く**。
ドライランは 8 本を互いに独立に bump して射影を出しており、この連鎖を模していなかった。

**一般則**: 射影の事前計算は、資産間の pin 関係を含めて**同時に**行わなければ合わない。
資産を 1 本ずつ独立に動かした見積もりは、pin の下流で外れる。

### 受理の対象は内容であって観測時点の識別子ではない

委任プロンプトの停止条件に「着手時の `origin/develop` が `347d7059` であること」と書いていた。
ドライラン中に PR #104 がマージされて develop が `7167c182` へ動き、**Codex は正しく止まった**。

人間が受理したのは **D の値と識別値の対応表**であって、観測時点の develop の SHA ではない。
#104 は pin した 6 ファイル・2 ツリーにも `contracts/tenant_boundary/` にも触れておらず、
**両方の base でドライランを回して D の指紋 `f6a9e0ac66957641` が一致する**ことを確認した上で、
停止条件を 2 つの不変量へ書き換えた —— **(A) 射影が動いた資産がちょうど 8 本**
**(B) 識別値の前後が受理された表と一致**。台帳の既存候補
「承認済み計画に書いた実測値が、他タスクのマージで同じ日のうちに何度も腐る」へ実測を足した。

### 敵対レビュー(sol xhigh・7 軸)

7 軸中 5 軸(識別値の整合 / digest と snapshot / 編集順序 / 人間判断の先取り / 予約 marker)は
「該当しない」。指摘 2 件は**いずれも受理記録の文面**で、実装の欠陥ではない。

| 重大度 | 指摘 | 是正 |
| --- | --- | --- |
| P1 | `reason` が「発行を専用モジュールへ機械的に封じ込めた」と**完了形**で書いていた。`allowed_product_modules` は `[]` のままで、専用モジュールの実体は U-M1 ステップ 8 の担当 | 成立した 2 つ(identity 一致の実行時検査 / 検査器の直接参照制限)に絞り、未了の範囲を明記した |
| P2 | `movement_fact` が追加欄を 2 件としていたが、実際は**発行入口を含む 4 欄** | 4 欄へ訂正し、発行入口の対が空で不活性であること・片側だけの対が `ContractError` になることを併記した |

**P1 の原因はタスク名の流用**である。TSK-457 の名前「発行を専用モジュールへ機械的に封じ込める」を
そのまま成果の記述に使うと、**裁定 1 で射程外にした部分まで完了したことになる**。
受理記録は凍結基準に恒久的に残るので、タスク名ではなく**その単位で成立した機構**を書く。

P2 は記録だけの数え違いで、実装は意図どおり(件名 `adfe2336`「…4 欄を足す」・
突合シート §3-3 / §3-5 / §3-9 / §4-3 / §4-4 で 2026-10-07 に人間確認済み)。

### develop(`7167c182`)の取り込み

衝突は **2 ファイル**(`docs/README.md`・`docs/development/harness-evaluation.md`)。
469 タブが PR #100 で踏んだ 5 ファイルのうち `docs/design/data-model.md` に由来する 3 件は、
**本 PR が `data-model.md` に触れていないため発生しない**。
`docs/README.md` の `data-model.md` 行と設計書行は本ブランチ側が merge-base と完全同一だったので
develop 側を採り、台帳行だけ両者を合成した。台帳の候補件数は取り込み後に再実測して **111**。
