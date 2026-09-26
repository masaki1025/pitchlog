---
feature: tenant-boundary-scope
type: design
date: 2026-09-25
---

# 逐行確認シート: 迂回検査の射程判定(TSK-440)

**機械生成**(`origin/develop...HEAD` の差分 + 契約資産から抽出)。**判定は人間が行う。**
コア領域(テナント分離)のため設計書 6.3 により逐行確認は必須で、**PR 作成者以外が実施する**。

**本 PR の性質**: **保証を正式に縮小する案件**である。縮小の代償として用意した
コア paths 拡大は敵対レビューで承認不可(P0×1)となり撤回した。
したがって**人間が残余リスクを明示的に受容するかどうかが、この確認の本題**である。

## 0. 見る順序

| 順 | 節 | 量 | なぜここを見るか |
| --- | --- | --- | --- |
| 1 | **A. 保証の宣言** | 13 行 | **ここだけで PR の是非が決まる**。以下はすべてこの宣言の実装である |
| 2 | **B-2 緩和の核心** | 32 行 | 宣言どおりに緩めているか。**緩め過ぎていないか** |
| 3 | **C. 条件 2 の裁定** | 5 件 | 裁定の理由が個別に妥当か |
| 4 | **E. 受理履歴** | 2 件 | 記録が事実か |
| 5 | B-1 / B-3 / D / F | 表 | 落ちてはいけないものが落ちていないか |

## 1. 機械が担保しない範囲(なぜ目視が要るか)

| # | 範囲 | 根拠 |
| --- | --- | --- |
| 1 | **負例 exact-set は「列挙したものが赤」しか見ない。列挙していない迂回形は見ない** | 台帳 §16-18「検出手段の対象集合が守りたい対象集合より狭い」。**本 PR 自身がこの型の是正である** |
| 2 | **センサスは旧 checker と新 checker の差分を見るだけで、両側に同じ誤りがあれば検出しない** | 永続 golden を置かない設計(ステップ 1)。母集団は merge-base の `backend/src` |
| 3 | **凍結基準の受理は「射影が動いたこと」を検証するが、動いた中身の是非は見ない** | `_validate_baseline_transition` は SHA の一致と履歴 1 件だけを見る |
| 4 | **Call 被覆の不変条件は 4 集合(AST / flow callable / flow receiver / scanner)の一致を見るが、集合の定義自体は検査器が決める** | 自己検査であり、定義を誤れば一致したまま漏れる |
| 5 | **`TenantContext.__init__` は公開のままで実行時防御がない** | 発行証跡は構築後の `tenant_id` 改竄しか捕まえない。封じ込めは別タスクへ起票済み |
| 6 | **資産を定数と実ファイルから同時に消すと、凍結検査の外へ静かに出せる** | `_validate_repository_histories` は `FROZEN_BASELINE_ASSETS` だけをループし、exact-set テストは両者の等式を見る。**develop 由来。TSK-431 が是正中**で本 PR の射程外 |

## 1-b. 機械が担保している範囲(変異で実測 — 2026-09-25)

**本 PR が新設した 4 機構について「関数は正しいが本番経路へ結線されていない」型がないかを変異で測った。**
検査器へ変異を 1 件ずつ入れ、173 件のテストを回した結果、**4 機構とも本番経路のテストが落ちた**。

| 変異 | 壊した機構 | 落ちた本番経路テスト | 計 |
| --- | --- | --- | --- |
| M1 | 再輸出写像を常に未供給扱い((v) 無効) | `..._real_commit_diff[5]` / `..._population_is_nonempty_and_green` / `..._always_supplies_reexport_maps_to_source_change` | 6 |
| M2 | 相対 import の `level` を常に 0 | `..._population_is_nonempty_and_green` | 3 |
| M3 | Call 被覆の不変条件を無効化 | `..._population_is_nonempty_and_green` | 4 |
| M4 | 条件 2 の裁定を全シンボルへ拡大 | `..._real_commit_diff[2]` / `..._population_is_nonempty_and_green` | 7 |

**したがって B-1 / B-3 / D の「実装が意図どおり動くか」は機械側の担保がある。**

## 1-c. 敵対レビュー 1 周目の結果(2026-09-26)

**判定はマージ不可。`P0` 2 件。** どちらも**同じ根**で、
**module-wide な名前解決が字句スコープの shadow を無視する**というものだった。**いずれも是正済み。**

| # | 内容 | 是正 |
| --- | --- | --- |
| P0-1 | **条件 5**: `from external.helpers import safe` の後に `def build(safe, t): return safe(t)` が**緑**だった。引数は実行時に何でも渡せるので `TenantContext` を渡せば構築できる。**宣言 (iii) では赤であるべき** | `:3926-3934` で**字句束縛を判定**し、束縛された裸名には module 側の import 情報を使わない |
| P0-2 | **条件 2**: 裁定シンボルを引数で shadow すると免除された。**裁定が exact-set として機能していなかった** | 同上の字句束縛判定を裁定側にも適用 |
| P1 | 受理履歴の `reason` の「狭めただけの受理を作れなくする」は**機構が保証していない** | 文言を訂正(釣り合いの判断は人間のレビュー事項と明記) |

**レビューが「問題なし」と確認した観点**: 既存負例 68 件は全件赤のまま / 裁定 5 件はいずれも記録権世代でない
(原典を確認)/ **4 機構の本番結線は成立** / Call 被覆の不一致は差分打ち消しの外 / **凍結連鎖はすべて一致**。

**Codex が使用上限に達したため(次回 2026-09-30)、この是正に対する再レビューは実施できていない。**
**設計書 6.3 はコア領域に敵対レビューを必須としているため、
このまま逐行確認へ進めるかどうかは人間の判断事項である。**

**目視の主対象は A(宣言の是非)・B-2(緩め方の妥当性)・C(裁定理由)・E(記録の正確さ)である。**

## A. 保証の宣言(逐語ブロック — 検査器 docstring と `design.md` の 2 箇所に同一文が入っている)

**機械突合の結果**: `scripts/check_tenant_boundary_bypass.py` に 1 回、
`docs/features/tenant-boundary-enforcement/design.md` に 2 回(6-0 と 1-1)、**逐語で一致**。

```text
条件 5(TenantContext 生成経路)の保証単位は「構築に使われる名前が、
変更ファイル内で読み取れること」である。型の解決可否は保証の条件にしない。
赤にするもの: (i) 完全修飾名が構築シンボルに解決される / (ii) 資産が列挙する禁止構築シンボル /
(iii) 名前が読み取れない callable(属性式でない呼び出し)/ (iv) 末尾名が構築シンボル末尾名に一致
(属性でも裸の名前でも)/ (v) 再輸出写像の可能な起源集合に構築シンボルが含まれる、
または内部再輸出の解決が unresolved(深さ上限 / star / 条件分岐 / 循環 / 自己参照 /
欠落した pitchlog.* モジュール / 未対応の静的代入)。

守らないもの(正式に縮小する — 人間承認の対象):
1. 再輸出元だけを変更し、利用側を変更しない漂流。CI の母集団が変更ファイルに限られるため
2. registry[k].make_context(t) のように、構築シンボル以外の属性名で、
   再輸出写像でも解決できない callable を経由した構築
3. (iii) と (iv)(v) の非対称は原理ではなく、既存負例が守る範囲を落とさないための線である
4. 引数・局所変数・クロージャ変数として外から渡された callable を経由した構築。
   依存性注入は型注釈でも由来を確定できず、赤にすると通常の設計パターンが
   機械的に通らなくなるため。
5. 実行時プロトコルが任意コードで値を変換・格納し、変更ファイルの AST に
   構築シンボルから callable までの起源関係が現れない経路。
   有限の構文軸による完全性は主張せず、残余は別タスクで扱う。
```

| # | 判定事項 | 判定 |
| --- | --- | --- |
| A1 | **「型の解決可否は保証の条件にしない」**という保証単位の置き方を受け入れるか | ☐ |
| A2 | 赤にするもの (i)〜(v) が**この 5 つで足りる**か | ☐ |
| A3 | **守らないもの 1**(再輸出元だけの漂流)を受け入れるか | ☐ |
| A4 | **守らないもの 2**(`registry[k].make_context(t)` 形)を受け入れるか | ☐ |
| A5 | **守らないもの 3**((iii) と (iv)(v) の非対称が原理でないこと)を受け入れるか | ☐ |
| A6 | **守らないもの 4**(**引数・局所変数・クロージャ変数として外から渡された callable を経由した構築**)を受け入れるか。**射程の裁定 2026-09-26 で追加**した項で、**本 PR の保証縮小はこれで 2 項目目**になる。決め手は「**TSK-235 側では直せない**」こと(`clock: Clock = time.monotonic` のような依存性注入は**型注釈を付けても由来が確定しない**) | ☐ |
| A7 | **線引きが妥当か** — **`global` で再束縛される名前は赤のまま**(module 束縛は字句束縛ではなく静的に追える)、**条件 2 の裁定も赤のまま**(裁定の exact-set 性は保証範囲内) | ☐ |
| A8 | **代償(コア paths 拡大)なしで縮小する**ことを受け入れるか | ☐ |

## B. 条件 5 の判定本体(逐行)

### B-1 `_check_tenant_context_call` のブロック分解(`scripts/check_tenant_boundary_bypass.py:4447-4727`)

**出所**: S5 = ステップ 5(強化) / S6 = ステップ 6(**緩和**) / 既存 = 本 PR 以前

| 行 | 出所 | 何を判定するか | 注意 | 判定 |
| --- | --- | --- | --- | --- |
| `4449-4450` | 既存 | 変更ファイル以外は見ない | CI の母集団が変更ファイルに限られる。**「守らないもの 1」の直接の原因** | ☐ |
| `4451-4462` | **裁定** | **由来の判定**(「守らないもの 4」の実装本体) | **引数・由来不明な局所値・クロージャ値は免除**。**関数内 import と静的に解決できる局所 alias は免除しない**(3 周目 P0-1 の是正) | ☐ |
| `4463-4502` | 既存 | callable 名の解決 | `getattr` 経由の `object.__new__` を正規名へ畳む | ☐ |
| `4503-4523` | 既存 | 禁止シンボル `object.__new__` | `cls` が構築シンボル自身でなければ **無罪** | ☐ |
| `4524-4548` | 既存 | 禁止シンボル `object.__setattr__` | `__init__` 内の `self` と safe target は **無罪** | ☐ |
| `4549-4585` | 既存 | 禁止シンボル `dataclasses.replace` | **`non_db` のときだけ無罪**。`unknown` は免除しない(ステップ 6 の差し戻し 1 で是正) | ☐ |
| `4586-4594` | 既存 | 禁止シンボル `type(x)(...)` | — | ☐ |
| `4595-4626` | **裁定** | **`global` 再束縛は不明扱い** | **`global` は字句束縛ではなくモジュール全体で静的に追える**ので赤のまま。**`import` writer と star import も再束縛に含む**(3 周目 P0-2 の是正) | ☐ |
| `4627-4647` | S5 | **(iv) 末尾名一致** | 属性でも裸の名前でも、由来種別に関係なく赤。**強化側** | ☐ |
| `4648-4652` | **裁定** | 再輸出写像の解決 | **`global` 再束縛された名前には写像を引かない** | ☐ |
| `4653-4708` | **S6** | **緩和の核心** — 由来不明の callable | 属性式は `_reject_reexport_call` の**戻り値を見ずに return**(再輸出写像に載らなければ無罪) | ☐ |
| `4709-4727` | 既存 | **(v)** 再輸出写像で判定 → 構築シンボルでなければ無罪 | ここは戻り値を見る。**上の属性式経路との非対称が「守らないもの 3」** | ☐ |

### B-2 緩和の核心(変更前後の全文 — 条件 5 で「赤を減らす」変更はここだけ)

**対象は「由来を完全修飾名へ解決できない callable」(`known_callable is None`)の扱いである。**
**変更前も無条件で赤ではなかった** — 属性式に対し **provenance(受け手の由来種別)** で
無罪を決めていた。本 PR はこれを **名前駆動**(再輸出写像の起源集合 + 末尾名一致)へ置き換えた。

**変更前**(merge-base `e62aced` の `scripts/check_tenant_boundary_bypass.py:2943-2970`):

```python
 2943          known_callable = self.flow.callable_symbol(node)
 2944          if known_callable is None:
 2945              if isinstance(node.func, ast.Attribute):
 2946                  provenance = self.flow.receiver_provenance(node)
 2947                  if (
 2948                      node.func.attr in self.contract.conservative_member_names
 2949                      or provenance in {"db", "non_db", "tenant_context"}
 2950                  ):
 2951                      return
 2952                  if (
 2953                      provenance in {"db_result", "non_db_attribute"}
 2954                      and node.func.attr
 2955                      != self.contract.tenant_context.constructor_symbol.rsplit(
 2956                          ".", 1
 2957                      )[-1]
 2958                  ):
 2959                      return
 2960              self._add(
 2961                  node,
 2962                  condition=5,
 2963                  code="TB007",
 2964                  symbol=resolved or "<unresolved-callable>",
 2965                  message=(
 2966                      "由来を完全修飾名へ解決できない callable は "
 2967                      "TenantContext の生成経路として拒否"
 2968                  ),
 2969              )
 2970              return
```

**由来の判定**(`scripts/check_tenant_boundary_bypass.py:4451-4462` — 「守らないもの 4」の実装本体):

```python
 4451          lexically_bound_callable = (
 4452              isinstance(node.func, ast.Name)
 4453              and id(node.func) in self.lexically_bound_name_ids
 4454          )
 4455          globally_rebound_callable = (
 4456              isinstance(node.func, ast.Name)
 4457              and not lexically_bound_callable
 4458              and (
 4459                  self.module_bindings.has_star_import
 4460                  or node.func.id in self.module_bindings.global_names
 4461              )
 4462          )
```

**緩和の核心**(`scripts/check_tenant_boundary_bypass.py:4595-4727`):

```python
 4595          rebound_bare_name = globally_rebound_callable
 4596          callable_value = (
 4597              _UNKNOWN_FLOW_VALUE
 4598              if rebound_bare_name
 4599              else self.flow.callable_value(node)
 4600          )
 4601          known_callable = callable_value.symbol
 4602          allowed_modules = (
 4603              self.contract.tenant_context.allowed_test_modules
 4604              | self.contract.tenant_context.allowed_product_modules
 4605          )
 4606          if (
 4607              self.contract.tenant_context.constructor_symbol
 4608              in callable_value.origins
 4609          ):
 4610              if self.module in allowed_modules:
 4611                  return
 4612              self._add(
 4613                  node,
 4614                  condition=5,
 4615                  code="TB007",
 4616                  symbol=self.contract.tenant_context.constructor_symbol,
 4617                  message=(
 4618                      "可能な callable 起源に TenantContext が含まれるため拒否"
 4619                  ),
 4620              )
 4621              return
 4622          if (
 4623              known_callable == self.contract.tenant_context.constructor_symbol
 4624              and self.module in allowed_modules
 4625          ):
 4626              return
 4627          constructor_name = (
 4628              self.contract.tenant_context.constructor_symbol.rsplit(".", 1)[-1]
 4629          )
 4630          callable_name = (
 4631              node.func.id
 4632              if isinstance(node.func, ast.Name)
 4633              else node.func.attr
 4634              if isinstance(node.func, ast.Attribute)
 4635              else None
 4636          )
 4637          if callable_name == constructor_name:
 4638              self._add(
 4639                  node,
 4640                  condition=5,
 4641                  code="TB007",
 4642                  symbol=callable_name,
 4643                  message=(
 4644                      "TenantContext と同名の callable は由来種別に関係なく拒否"
 4645                  ),
 4646              )
 4647              return
 4648          reexport = (
 4649              None
 4650              if rebound_bare_name
 4651              else self._reexport_resolution(node.func, resolved)
 4652          )
 4653          if known_callable is None:
 4654              if isinstance(node.func, ast.Attribute):
 4655                  self._reject_reexport_call(
 4656                      node,
 4657                      resolved=resolved,
 4658                      callable_name=callable_name,
 4659                      resolution=reexport,
 4660                      allowed_modules=allowed_modules,
 4661                  )
 4662                  return
 4663              # 起源集合を分岐・コンテナ・閉包まで保持し、TenantContext 起源が無く
 4664              # 未解決でもない外部入力だけを保証外 callable として免除する。
 4665              if (
 4666                  lexically_bound_callable
 4667                  and callable_value.external_input
 4668                  and not callable_value.unresolved
 4669              ):
 4670                  return
 4671              alias_resolved = self.aliases.resolve(node.func)
 4672              # resolve() は未知の裸名も生テキストで返す。known_symbols を読む
 4673              # resolve_known() でも解決できた Name だけを既知 callable とする。
 4674              known_alias_callable: str | None = None
 4675              if (
 4676                  isinstance(node.func, ast.Name)
 4677                  and alias_resolved is not None
 4678                  and not rebound_bare_name
 4679                  and (
 4680                      not lexically_bound_callable
 4681                      or not callable_value.storage_ids
 4682                  )
 4683              ):
 4684                  known_alias_callable = self.aliases.resolve_known(node.func)
 4685              if (
 4686                  known_alias_callable is not None
 4687                  and self.aliases.canonical(known_alias_callable)
 4688                  != self.contract.tenant_context.constructor_symbol
 4689              ):
 4690                  self._reject_reexport_call(
 4691                      node,
 4692                      resolved=resolved,
 4693                      callable_name=callable_name,
 4694                      resolution=reexport,
 4695                      allowed_modules=allowed_modules,
 4696                  )
 4697                  return
 4698              self._add(
 4699                  node,
 4700                  condition=5,
 4701                  code="TB007",
 4702                  symbol=resolved or "<unresolved-callable>",
 4703                  message=(
 4704                      "由来を完全修飾名へ解決できない callable は "
 4705                      "TenantContext の生成経路として拒否"
 4706                  ),
 4707              )
 4708              return
 4709          if self._reject_reexport_call(
 4710              node,
 4711              resolved=resolved,
 4712              callable_name=callable_name,
 4713              resolution=reexport,
 4714              allowed_modules=allowed_modules,
 4715          ):
 4716              return
 4717          if known_callable != self.contract.tenant_context.constructor_symbol:
 4718              return
 4719          if self.module in allowed_modules:
 4720              return
 4721          self._add(
 4722              node,
 4723              condition=5,
 4724              code="TB007",
 4725              symbol=known_callable,
 4726              message="TenantContext は生成箇所 allowlist 内のモジュールだけで構築できる",
 4727          )
```

**委ねられる先**(`scripts/check_tenant_boundary_bypass.py:4282-4317` — 本 PR がステップ 5 で新設):

```python
 4282      def _reject_reexport_call(
 4283          self,
 4284          node: ast.Call,
 4285          *,
 4286          resolved: str | None,
 4287          callable_name: str | None,
 4288          resolution: _ExportResolution | None,
 4289          allowed_modules: Set[str],
 4290      ) -> bool:
 4291          """危険または解決不能な再輸出 callable を拒否したか返す。"""
 4292          if resolution is None:
 4293              return False
 4294          if resolution.unresolved:
 4295              self._add(
 4296                  node,
 4297                  condition=5,
 4298                  code="TB007",
 4299                  symbol=resolved or callable_name or "<unresolved-reexport>",
 4300                  message="再輸出 callable の起源を一意に解決できない",
 4301              )
 4302              return True
 4303          if (
 4304              self.contract.tenant_context.constructor_symbol
 4305              not in resolution.origins
 4306          ):
 4307              return False
 4308          if self.module in allowed_modules:
 4309              return True
 4310          self._add(
 4311              node,
 4312              condition=5,
 4313              code="TB007",
 4314              symbol=resolved or callable_name or "<tenant-context-reexport>",
 4315              message="再輸出経由の TenantContext 構築は許可されない",
 4316          )
 4317          return True
```


| 観点 | 変更前 | 変更後 |
| --- | --- | --- |
| 属性式で由来不明 | `conservative_member_names` か provenance が `db` / `non_db` / `tenant_context` なら無罪。`db_result` / `non_db_attribute` は**末尾名が構築シンボルでなければ**無罪。**それ以外は赤** | **再輸出写像で起源を一意に解決でき、構築シンボルでなければ無罪**。写像に載らなければ無罪。**unresolved なら赤** |
| 裸の名前で由来不明 | **常に赤** | `resolve_known()` が構築シンボル以外へ解決できれば無罪 |
| 末尾名が構築シンボルと一致 | **provenance 次第で無罪になりえた** | **由来種別に関係なく赤**(**強化側**) |

| # | 判定事項 | 判定 |
| --- | --- | --- |
| B2-1 | **由来の判定が「守らないもの 4」と過不足なく一致しているか** — 免除するのは**引数・由来不明な局所値・クロージャ値**だけで、**関数内 import と静的に解決できる局所 alias は (i)/(iv) へ流す**(3 周目 `P0-1` の是正)。**宣言より広く緑にしていないか** | ☐ |
| B2-2 | **`global` 再束縛が赤のまま**であること。**`import` writer(`is_imported()`)と star import も再束縛に含む**(3 周目 `P0-2` の是正) | ☐ |
| B2-3 | **属性式の経路は `_reject_reexport_call` の戻り値を捨てて無条件 `return` する**(再輸出写像に載らない属性式は無罪)。これが「守らないもの 2」と一致しているか | ☐ |
| B2-4 | 対して**再輸出写像の経路は戻り値を見て判定を続ける**。この**非対称が「守らないもの 3」で開示**されているか | ☐ |
| B2-5 | `unresolved` の列挙(**深さ上限・star・条件分岐・循環・自己参照・欠落 `pitchlog.*`・未対応の静的代入**)に漏れがないか | ☐ |
| B2-6 | **写像が未供給なら全件が無罪**になる。本番経路が必ず供給することはステップ 5 の差し戻しでテストに固定した | ☐ |
| B2-7 | **過剰拒否になっていないか** — 「import した名前をそのまま呼ぶ」「引数として受けた callable を呼ぶ」が**緑のままであることがテストで固定**されている | ☐ |


### B-3 TB007 の全送出点(19 箇所)

| 行 | 出所 | 関数 | 検出内容 | 宣言 | 判定 |
| --- | --- | --- | --- | --- | --- |
| `4298` |  | `_reject_reexport_call` | 再輸出 callable の起源を一意に解決できない | (v) | ☐ |
| `4313` |  | `_reject_reexport_call` | 再輸出経由の TenantContext 構築は許可されない | (v) | ☐ |
| `4494` |  | `_check_tenant_context_call` | TenantContext の __new__ / __init__ 直接呼び出しによる 構築迂回は禁止 | — | ☐ |
| `4518` |  | `_check_tenant_context_call` | 型を解決できない object.__new__ も TenantContext 生成迂回として拒否 | (ii) | ☐ |
| `4544` |  | `_check_tenant_context_call` | 正規構築箇所以外の object.__setattr__ による文脈改竄は禁止 | (ii) | ☐ |
| `4560` |  | `_check_tenant_context_call` | dataclasses.replace による TenantContext 複製迂回は禁止 | (ii) | ☐ |
| `4576` |  | `_check_tenant_context_call` | copy.copy による TenantContext 複製迂回は禁止 | — | ☐ |
| `4590` |  | `_check_tenant_context_call` | type(context) による TenantContext 複製迂回は禁止 | (ii) | ☐ |
| `4615` |  | `_check_tenant_context_call` | 可能な callable 起源に TenantContext が含まれるため拒否 | — | ☐ |
| `4641` |  | `_check_tenant_context_call` | TenantContext と同名の callable は由来種別に関係なく拒否 | (iv) | ☐ |
| `4701` |  | `_check_tenant_context_call` | 由来を完全修飾名へ解決できない callable は TenantContext の生成経路として拒否 | (iii) | ☐ |
| `4724` |  | `_check_tenant_context_call` | TenantContext は生成箇所 allowlist 内のモジュールだけで構築できる | (i) | ☐ |
| `4753` |  | `_check_integrity_reference` | message | — | ☐ |
| `4794` |  | `_check_dynamic_call` | getattr による TenantContext 発行証跡内部への参照は禁止 | — | ☐ |
| `4841` |  | `_check_dynamic_call` | TenantContext の動的構築は生成箇所 allowlist を迂回する | — | ☐ |
| `4948` |  | `visit_ClassDef` | 可能なクラス基底起源に TenantContext が含まれるため拒否 | — | ☐ |
| `4959` |  | `visit_ClassDef` | 起源を解決できない class base は TenantContext 継承迂回として拒否 | — | ☐ |
| `4983` |  | `visit_ClassDef` | 再輸出経由または起源不明の TenantContext 継承は禁止 | (v) | ☐ |
| `4998` |  | `visit_ClassDef` | TenantContext は生成箇所 allowlist 外で継承できない | (i) | ☐ |

## C. 条件 2 の裁定(全数 6 件)

**候補パターン `(?:^|_)generation(?:_|$)` は狭めていない。**
当初案(`generation_no` へ絞る)は**実在する `RecordingGeneration` の検出 14 件を消す**ことが
1 周目レビューで判明したため撤回した。代わりに**裁定済みシンボルの exact-set** を置き、
**未登録の新しい `*Generation` は赤のまま**にした。

| # | シンボル | 理由 | 判定 |
| --- | --- | --- | --- |
| 1 | `pitchlog.domaincheck.runners.catalog_independence.TracedGeneration` | ドメイン計算カタログの独立性検査で使う追跡世代であり、同期プロトコルの世代ではない | ☐ |
| 2 | `pitchlog.domaingen.backends.common.BackendGenerationError` | ドメイン計算のコード生成 backend が送出する例外型であり、同期プロトコルの世代ではない | ☐ |
| 3 | `pitchlog.domaingen.core.EXIT_GENERATION_FAILED` | ドメイン計算のコード生成が失敗したことを表す終了コードの定数であり、同期プロトコルの世代ではない | ☐ |
| 4 | `pitchlog.domaingen.core.GenerationError` | ドメイン計算のコード生成が送出する例外型であり、同期プロトコルの世代ではない | ☐ |
| 5 | `pitchlog.domaingen.formatter.FormatterGenerationError` | ドメイン計算の表示コード生成が送出する例外型であり、同期プロトコルの世代ではない | ☐ |
| 6 | `pitchlog.domainmut.engine.MutationGeneration` | ドメイン計算 DSL の変異生成結果であり、同期プロトコルの世代ではない | ☐ |

| # | 判定事項 | 判定 |
| --- | --- | --- |
| C-1 | 5 件それぞれが**同期プロトコルの世代ではない**という判断が正しいか | ☐ |
| C-2 | **`RecordingGeneration` 14 件が赤のまま**であること(裁定に入れていない) | ☐ |
| C-3 | **裁定に無い新しい `*Generation` が赤になる**こと | ☐ |

## D. 落ちてはいけないもの — 新規負例(全数 45 件・負例総数 68 → 112)

**すべて赤(検出される)ことが機械で検証されている。目視の対象は「この表の形で足りるか」である。**

| # | ID | 条件 | 期待 | 何を守るか | 判定 |
| --- | --- | --- | --- | --- | --- |
| 1 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_ASSIGNMENT` | 2 | TB002 | 裁定済み import と同名の局所代入を裁定 exact-set で免除する | ☐ |
| 2 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_CLASS_ASSIGNMENT` | 2 | TB002 | 裁定済み import と同名の class 代入を裁定 exact-set で免除する | ☐ |
| 3 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_EXCEPT` | 2 | TB002 | except as で裁定済み import 名を上書きして裁定 exact-set を迂回する | ☐ |
| 4 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_MATCH` | 2 | TB002 | match capture で裁定済み import 名を上書きして裁定 exact-set を迂回する | ☐ |
| 5 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_MODULE_ASSIGNMENT` | 2 | TB002 | 裁定済み import と同名の module 代入を裁定 exact-set で免除する | ☐ |
| 6 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_PARAMETER` | 2 | TB002 | 裁定済み import と同名の引数を裸名参照して裁定 exact-set を迂回する | ☐ |
| 7 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_STAR` | 2 | TB002 | star import による裁定済み import 名の上書きを裁定 exact-set で免除する | ☐ |
| 8 | `C2_ADJUDICATED_IMPORT_SHADOWED_BY_WALRUS` | 2 | TB002 | 裁定済み import と同名の walrus target を裁定 exact-set で免除する | ☐ |
| 9 | `C2_GENERATION_ARGUMENT_NAME` | 2 | TB002 | ast.arg の構文名 generation を条件 2 候補から外す | ☐ |
| 10 | `C2_GENERATION_ATTRIBUTE_ASSIGNMENT` | 2 | TB002 | 属性代入の構文名 generation を条件 2 候補から外す | ☐ |
| 11 | `C2_GENERATION_KEYWORD_ARGUMENT` | 2 | TB002 | keyword 引数の構文名 generation を条件 2 候補から外す | ☐ |
| 12 | `C2_GENERATION_MATCH_KEYWORD` | 2 | TB002 | match keyword pattern の構文名 generation を条件 2 候補から外す | ☐ |
| 13 | `C5_CONTEXT_AFTER_TERMINATOR` | 5 | TB007 | 終端文より後で TenantContext を構築する | ☐ |
| 14 | `C5_CONTEXT_CONDITIONAL_ALIAS_CLASS_BASE` | 5 | TB007 | 条件付き alias を関数内 class の基底にして TenantContext 起源を隠す | ☐ |
| 15 | `C5_CONTEXT_CONDITIONAL_ALIAS_CLOSURE` | 5 | TB007 | 条件付き alias をクロージャへ渡して TenantContext 起源を隠す | ☐ |
| 16 | `C5_CONTEXT_CONTAINER_SUBSCRIPT` | 5 | TB007 | コンテナと添字参照を経由して TenantContext 起源を隠す | ☐ |
| 17 | `C5_CONTEXT_IFEXP_ORIGIN_MERGE` | 5 | TB007 | IfExp で安全 callable と合流させて TenantContext 起源を消す | ☐ |
| 18 | `C5_CONTEXT_IF_ELSE_ORIGIN_MERGE` | 5 | TB007 | if-else の分岐代入で TenantContext 起源を消す | ☐ |
| 19 | `C5_CONTEXT_IN_ANNOTATED_ASSIGNMENT` | 5 | TB007 | 注釈付き代入の annotation で TenantContext を構築する | ☐ |
| 20 | `C5_CONTEXT_IN_CLASS_BASE` | 5 | TB007 | class base で TenantContext を構築する | ☐ |
| 21 | `C5_CONTEXT_IN_DEFAULT_ARG` | 5 | TB007 | 関数のデフォルト引数で TenantContext を構築する | ☐ |
| 22 | `C5_CONTEXT_IN_DICT_COMPREHENSION` | 5 | TB007 | 辞書内包表記の generator 条件で TenantContext を構築する | ☐ |
| 23 | `C5_CONTEXT_IN_EXCEPTION_HANDLER_TYPE` | 5 | TB007 | 例外 handler type で TenantContext を構築する | ☐ |
| 24 | `C5_CONTEXT_IN_FUNCTION_IMPORT` | 5 | TB007 | 関数内 import へ移した TenantContext 構築を字句束縛の免除で迂回する | ☐ |
| 25 | `C5_CONTEXT_IN_LAMBDA_DEFAULT` | 5 | TB007 | lambda のデフォルト引数で TenantContext を構築する | ☐ |
| 26 | `C5_CONTEXT_IN_LOCAL_ALIAS` | 5 | TB007 | TenantContext の静的な局所 alias を字句束縛の免除で迂回する | ☐ |
| 27 | `C5_CONTEXT_IN_SUBSCRIPT_TARGET` | 5 | TB007 | 添字代入先で TenantContext を構築する | ☐ |
| 28 | `C5_CONTEXT_MATCH_ORIGIN_MERGE` | 5 | TB007 | match の分岐代入で TenantContext 起源を消す | ☐ |
| 29 | `C5_CONTEXT_REEXPORT_CONDITIONAL` | 5 | TB007 | 条件分岐で複数起源を持つ再輸出名を呼び出す | ☐ |
| 30 | `C5_CONTEXT_REEXPORT_CYCLE` | 5 | TB007 | 循環する再輸出別名を呼び出す | ☐ |
| 31 | `C5_CONTEXT_REEXPORT_DEPTH_LIMIT` | 5 | TB007 | 再輸出別名の追跡深さ上限を超える | ☐ |
| 32 | `C5_CONTEXT_REEXPORT_FACADE` | 5 | TB007 | façade が再輸出した別名 Context から TenantContext を構築する | ☐ |
| 33 | `C5_CONTEXT_REEXPORT_MISSING_MODULE` | 5 | TB007 | 欠落した pitchlog モジュール由来の Context を呼び出す | ☐ |
| 34 | `C5_CONTEXT_REEXPORT_SELF_REFERENCE` | 5 | TB007 | 自己参照する再輸出別名を呼び出す | ☐ |
| 35 | `C5_CONTEXT_REEXPORT_STAR` | 5 | TB007 | star import 由来で起源不明の Context を呼び出す | ☐ |
| 36 | `C5_CONTEXT_REEXPORT_SUBCLASS` | 5 | TB007 | façade が再輸出した別名 Context を継承する | ☐ |
| 37 | `C5_CONTEXT_REEXPORT_UNSUPPORTED_ASSIGN` | 5 | TB007 | 未対応の静的代入で作った Context を呼び出す | ☐ |
| 38 | `C5_CONTEXT_RELATIVE_IMPORT` | 5 | TB007 | 同一 package から相対 import した TenantContext を構築する | ☐ |
| 39 | `C5_CONTEXT_TRY_EXCEPT_ORIGIN_MERGE` | 5 | TB007 | try-except の分岐代入で TenantContext 起源を消す | ☐ |
| 40 | `C5_IMPORT_REBOUND_BY_GLOBAL_IMPORT` | 5 | TB007 | 別関数の global import writer で import 由来 callable を差し替える | ☐ |
| 41 | `C5_IMPORT_REBOUND_BY_GLOBAL_WRITER` | 5 | TB007 | 別関数の global writer で import 由来の callable を差し替える | ☐ |
| 42 | `C5_IMPORT_REBOUND_BY_STAR` | 5 | TB007 | star import で module callable の起源を不確定にする | ☐ |
| 43 | `C5_SECRET_IN_DEFAULT_CAPTURE` | 5 | TB007 | 許可シンボルのデフォルト引数で発行証跡の秘密を捕捉する | ☐ |
| 44 | `C5_TENANT_CONTEXT_DIRECT_INIT` | 5 | TB007 | TenantContext.__init__ を既存 object へ直接適用する | ☐ |
| 45 | `C5_TENANT_CONTEXT_DIRECT_NEW` | 5 | TB007 | TenantContext.__new__ を直接呼んで constructor 検査を迂回する | ☐ |

| # | 判定事項 | 判定 |
| --- | --- | --- |
| D-1 | **緩和(B-2)を入れてもなお赤であるべき形**が、**この表の全件**で尽くされているか | ☐ |
| D-2 | **既存 68 件のうち 67 件は赤のまま。残る 1 件 `C5_CONTEXT_UNKNOWN_FACTORY` は射程の裁定で保証範囲外になり、負例から外れた** — 中身は `def forge_context(factory, t): return factory(t)` で、**まさに「守らないもの 4」の形**だった。**削除ではなく `test_parameter_bare_call_is_outside_condition_5_scope` で「緑であること」を固定**している。**この 1 件を落とすことを受け入れるか** | ☐ |
| D-3 | **保証範囲外にした 3 形**(引数 / 引数注釈 / 遅延束縛クロージャ)が**正例として緑を固定**されていること。**黙って消していない**ことの確認 | ☐ |

## E. 凍結基準の受理(v2 — **承認後に書く**)

**本 PR は受理記録をまだ書いていない。** TSK-431(PR #78)が先にマージされ、記録形式が v2 へ変わったためである。

**v2 では `approved_by` / `approved_on` / `movement_fact` / `reason` / `change.subject` に
予約 marker(`未承認` `PENDING` `TODO` `TBD` `未定` `レビュー待ち`)が使えない。**
**実在の承認者名と ISO 8601 日付が要る。** したがって順序は次になる。

> **逐行確認 → 人間の承認 → 承認者名で v2 記録を書く → CI → マージ**

**これは機構が強制する順序であり、循環ではない。** TSK-431 も同じ手順を踏んでいる。

### 承認後に書く内容(こちらで実装と同じ経路から確定済み)

| 項目 | 値 |
| --- | --- |
| `acceptance_id` | `masaki1025/pitchlog#80` |
| 記録を置く資産 | **authority = `base-allowlist.json` に 1 件だけ** |
| `new_baseline_identifiers` | **7 資産すべての map**(authority は 15 → **16**) |
| `triggered_tokens` | `baseline_value` / `pass_fail_mapping` |
| `affected_assets` | **7 件すべて**(検査器が 7 資産共通の `external_files` にあるため) |
| `change.before` / `after` | 4 キー(`declaration` / `movement_policy` / `external_snapshots` 3 件 / `asset_snapshots` 7 件) |
| `history-snapshots/` | **現在 47 件**。記録と**同じコミット**で before / after 両方を追記する |

**`affected_assets` は「宣言内容を書き換えた資産」ではなく「射影が動いた資産」である。**
**本 PR が内容を変えるのは 2 資産だが、検査器の変更が 7 資産すべての射影を動かす。**

| # | 判定事項 | 判定 |
| --- | --- | --- |
| E-1 | **記録がまだ無いこと**が正しい状態だと理解したうえで確認しているか(承認前に書けないため) | ☐ |
| E-2 | 承認する場合、**あなたの名前と確認日**が記録へ入る。それでよいか | ☐ |
| E-3 | **`affected_assets` が 7 件**(全資産)になる理由を受け入れるか — 検査器が 7 資産共通の外部凍結対象だから | ☐ |
| E-4 | authority の識別値を **15 → 16** にする。TSK-442 が 17 を使う段取りと整合しているか | ☐ |
| E-5 | **記録は 1 回で書き切る**(作り直すと snapshot が孤児として永久に残る。TSK-431 では 47 件中 29 件・1MB が回収不能になった) | ☐ |

## F. 残余 — TSK-235 への申し送り(全数 10 件)

**本 PR 適用後も TSK-235 のツリーに残る検出。いずれも規則どおりの検出で真の脆弱性ではない。**

| # | 位置 | 検出 | 判定 |
| --- | --- | --- | --- |
| 1 | `backend/src/pitchlog/domaingen/pregen_checks.py:582` | TB007 1 | ☐ |
| 2 | `backend/src/pitchlog/domainmut/engine.py:262,263,265,273,291,296,298` | TB002 7 | ☐ |
| 3 | `backend/src/pitchlog/domainmut/operators_display.py:469,479` | TB007 2 | ☐ |

**効果の実測**(現行 contract + 現行 checker を TSK-235 の `backend/src` へ当てた全文走査):

| | 適用前 | 適用後 |
| --- | --- | --- |
| **TB007** | **794** | **3** |
| **TB002** | **146** | **37** |
| TB005 | 137 | **137** |
| TB004 | 15 | **15** |

**TB001〜TB006 は不変。減ったのは TB007 と、裁定した TB002 だけ。**

## G. 判定サマリ

| 節 | 件数 | 済 |
| --- | --- | --- |
| A. 保証の宣言 | 8 | ☐ |
| B-1 `_check_tenant_context_call` のブロック分解 | 12 | ☐ |
| B-2 緩和の核心 | 7 | ☐ |
| B-3 TB007 の全送出点 | 19 | ☐ |
| C. 条件 2 の裁定 | 9 | ☐ |
| D. 落ちてはいけないもの | 48 | ☐ |
| E. 凍結基準の受理 | 5 | ☐ |
| F. 残余 | 3 | ☐ |
| **合計** | **111** | ☐ |

**総合判定**: ☐ 承認 / ☐ 差し戻し(指摘を PR コメントへ)

**承認する場合**、その名前と日付で v2 受理記録を書く作業が続く(**本 PR ではまだ書いていない**)。
