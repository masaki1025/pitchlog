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
5. 未対応の式を経由して構築シンボルの起源が失われる経路。
   完全な解には制御フロー解析が要るため、別タスクで扱う。
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

### B-1 `_check_tenant_context_call` のブロック分解(`scripts/check_tenant_boundary_bypass.py:4371-4615`)

**出所**: S5 = ステップ 5(強化) / S6 = ステップ 6(**緩和**) / 既存 = 本 PR 以前

| 行 | 出所 | 何を判定するか | 注意 | 判定 |
| --- | --- | --- | --- | --- |
| `4373-4374` | 既存 | 変更ファイル以外は見ない | CI の母集団が変更ファイルに限られる。**「守らないもの 1」の直接の原因** | ☐ |
| `4375-4386` | **裁定** | **由来の判定**(「守らないもの 4」の実装本体) | **引数・由来不明な局所値・クロージャ値は免除**。**関数内 import と静的に解決できる局所 alias は免除しない**(3 周目 P0-1 の是正) | ☐ |
| `4387-4410` | 既存 | callable 名の解決 | `getattr` 経由の `object.__new__` を正規名へ畳む | ☐ |
| `4411-4431` | 既存 | 禁止シンボル `object.__new__` | `cls` が構築シンボル自身でなければ **無罪** | ☐ |
| `4432-4456` | 既存 | 禁止シンボル `object.__setattr__` | `__init__` 内の `self` と safe target は **無罪** | ☐ |
| `4457-4477` | 既存 | 禁止シンボル `dataclasses.replace` | **`non_db` のときだけ無罪**。`unknown` は免除しない(ステップ 6 の差し戻し 1 で是正) | ☐ |
| `4478-4486` | 既存 | 禁止シンボル `type(x)(...)` | — | ☐ |
| `4487-4518` | **裁定** | **`global` 再束縛は不明扱い** | **`global` は字句束縛ではなくモジュール全体で静的に追える**ので赤のまま。**`import` writer と star import も再束縛に含む**(3 周目 P0-2 の是正) | ☐ |
| `4519-4539` | S5 | **(iv) 末尾名一致** | 属性でも裸の名前でも、由来種別に関係なく赤。**強化側** | ☐ |
| `4540-4544` | **裁定** | 再輸出写像の解決 | **`global` 再束縛された名前には写像を引かない** | ☐ |
| `4545-4596` | **S6** | **緩和の核心** — 由来不明の callable | 属性式は `_reject_reexport_call` の**戻り値を見ずに return**(再輸出写像に載らなければ無罪) | ☐ |
| `4597-4615` | 既存 | **(v)** 再輸出写像で判定 → 構築シンボルでなければ無罪 | ここは戻り値を見る。**上の属性式経路との非対称が「守らないもの 3」** | ☐ |

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

**由来の判定**(`scripts/check_tenant_boundary_bypass.py:4375-4386` — 「守らないもの 4」の実装本体):

```python
 4375          lexically_bound_callable = (
 4376              isinstance(node.func, ast.Name)
 4377              and id(node.func) in self.lexically_bound_name_ids
 4378          )
 4379          globally_rebound_callable = (
 4380              isinstance(node.func, ast.Name)
 4381              and not lexically_bound_callable
 4382              and (
 4383                  self.module_bindings.has_star_import
 4384                  or node.func.id in self.module_bindings.global_names
 4385              )
 4386          )
```

**緩和の核心**(`scripts/check_tenant_boundary_bypass.py:4487-4615`):

```python
 4487          rebound_bare_name = globally_rebound_callable
 4488          callable_value = (
 4489              _UNKNOWN_FLOW_VALUE
 4490              if rebound_bare_name
 4491              else self.flow.callable_value(node)
 4492          )
 4493          known_callable = callable_value.symbol
 4494          allowed_modules = (
 4495              self.contract.tenant_context.allowed_test_modules
 4496              | self.contract.tenant_context.allowed_product_modules
 4497          )
 4498          if (
 4499              self.contract.tenant_context.constructor_symbol
 4500              in callable_value.origins
 4501          ):
 4502              if self.module in allowed_modules:
 4503                  return
 4504              self._add(
 4505                  node,
 4506                  condition=5,
 4507                  code="TB007",
 4508                  symbol=self.contract.tenant_context.constructor_symbol,
 4509                  message=(
 4510                      "可能な callable 起源に TenantContext が含まれるため拒否"
 4511                  ),
 4512              )
 4513              return
 4514          if (
 4515              known_callable == self.contract.tenant_context.constructor_symbol
 4516              and self.module in allowed_modules
 4517          ):
 4518              return
 4519          constructor_name = (
 4520              self.contract.tenant_context.constructor_symbol.rsplit(".", 1)[-1]
 4521          )
 4522          callable_name = (
 4523              node.func.id
 4524              if isinstance(node.func, ast.Name)
 4525              else node.func.attr
 4526              if isinstance(node.func, ast.Attribute)
 4527              else None
 4528          )
 4529          if callable_name == constructor_name:
 4530              self._add(
 4531                  node,
 4532                  condition=5,
 4533                  code="TB007",
 4534                  symbol=callable_name,
 4535                  message=(
 4536                      "TenantContext と同名の callable は由来種別に関係なく拒否"
 4537                  ),
 4538              )
 4539              return
 4540          reexport = (
 4541              None
 4542              if rebound_bare_name
 4543              else self._reexport_resolution(node.func, resolved)
 4544          )
 4545          if known_callable is None:
 4546              if isinstance(node.func, ast.Attribute):
 4547                  self._reject_reexport_call(
 4548                      node,
 4549                      resolved=resolved,
 4550                      callable_name=callable_name,
 4551                      resolution=reexport,
 4552                      allowed_modules=allowed_modules,
 4553                  )
 4554                  return
 4555              # 起源集合を分岐・コンテナ・閉包まで保持し、TenantContext 起源が無く
 4556              # 未解決でもない外部入力だけを保証外 callable として免除する。
 4557              if (
 4558                  lexically_bound_callable
 4559                  and callable_value.external_input
 4560                  and not callable_value.unresolved
 4561              ):
 4562                  return
 4563              alias_resolved = self.aliases.resolve(node.func)
 4564              # resolve() は未知の裸名も生テキストで返す。known_symbols を読む
 4565              # resolve_known() でも解決できた Name だけを既知 callable とする。
 4566              known_alias_callable: str | None = None
 4567              if (
 4568                  isinstance(node.func, ast.Name)
 4569                  and alias_resolved is not None
 4570                  and not rebound_bare_name
 4571              ):
 4572                  known_alias_callable = self.aliases.resolve_known(node.func)
 4573              if (
 4574                  known_alias_callable is not None
 4575                  and self.aliases.canonical(known_alias_callable)
 4576                  != self.contract.tenant_context.constructor_symbol
 4577              ):
 4578                  self._reject_reexport_call(
 4579                      node,
 4580                      resolved=resolved,
 4581                      callable_name=callable_name,
 4582                      resolution=reexport,
 4583                      allowed_modules=allowed_modules,
 4584                  )
 4585                  return
 4586              self._add(
 4587                  node,
 4588                  condition=5,
 4589                  code="TB007",
 4590                  symbol=resolved or "<unresolved-callable>",
 4591                  message=(
 4592                      "由来を完全修飾名へ解決できない callable は "
 4593                      "TenantContext の生成経路として拒否"
 4594                  ),
 4595              )
 4596              return
 4597          if self._reject_reexport_call(
 4598              node,
 4599              resolved=resolved,
 4600              callable_name=callable_name,
 4601              resolution=reexport,
 4602              allowed_modules=allowed_modules,
 4603          ):
 4604              return
 4605          if known_callable != self.contract.tenant_context.constructor_symbol:
 4606              return
 4607          if self.module in allowed_modules:
 4608              return
 4609          self._add(
 4610              node,
 4611              condition=5,
 4612              code="TB007",
 4613              symbol=known_callable,
 4614              message="TenantContext は生成箇所 allowlist 内のモジュールだけで構築できる",
 4615          )
```

**委ねられる先**(`scripts/check_tenant_boundary_bypass.py:4206-4241` — 本 PR がステップ 5 で新設):

```python
 4206      def _reject_reexport_call(
 4207          self,
 4208          node: ast.Call,
 4209          *,
 4210          resolved: str | None,
 4211          callable_name: str | None,
 4212          resolution: _ExportResolution | None,
 4213          allowed_modules: Set[str],
 4214      ) -> bool:
 4215          """危険または解決不能な再輸出 callable を拒否したか返す。"""
 4216          if resolution is None:
 4217              return False
 4218          if resolution.unresolved:
 4219              self._add(
 4220                  node,
 4221                  condition=5,
 4222                  code="TB007",
 4223                  symbol=resolved or callable_name or "<unresolved-reexport>",
 4224                  message="再輸出 callable の起源を一意に解決できない",
 4225              )
 4226              return True
 4227          if (
 4228              self.contract.tenant_context.constructor_symbol
 4229              not in resolution.origins
 4230          ):
 4231              return False
 4232          if self.module in allowed_modules:
 4233              return True
 4234          self._add(
 4235              node,
 4236              condition=5,
 4237              code="TB007",
 4238              symbol=resolved or callable_name or "<tenant-context-reexport>",
 4239              message="再輸出経由の TenantContext 構築は許可されない",
 4240          )
 4241          return True
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


### B-3 TB007 の全送出点(16 箇所)

| 行 | 出所 | 関数 | 検出内容 | 宣言 | 判定 |
| --- | --- | --- | --- | --- | --- |
| `4222` |  | `_reject_reexport_call` | 再輸出 callable の起源を一意に解決できない | (v) | ☐ |
| `4237` |  | `_reject_reexport_call` | 再輸出経由の TenantContext 構築は許可されない | (v) | ☐ |
| `4426` |  | `_check_tenant_context_call` | 型を解決できない object.__new__ も TenantContext 生成迂回として拒否 | (ii) | ☐ |
| `4452` |  | `_check_tenant_context_call` | 正規構築箇所以外の object.__setattr__ による文脈改竄は禁止 | (ii) | ☐ |
| `4468` |  | `_check_tenant_context_call` | dataclasses.replace による TenantContext 複製迂回は禁止 | (ii) | ☐ |
| `4482` |  | `_check_tenant_context_call` | type(context) による TenantContext 複製迂回は禁止 | (ii) | ☐ |
| `4507` |  | `_check_tenant_context_call` | 可能な callable 起源に TenantContext が含まれるため拒否 | — | ☐ |
| `4533` |  | `_check_tenant_context_call` | TenantContext と同名の callable は由来種別に関係なく拒否 | (iv) | ☐ |
| `4589` |  | `_check_tenant_context_call` | 由来を完全修飾名へ解決できない callable は TenantContext の生成経路として拒否 | (iii) | ☐ |
| `4612` |  | `_check_tenant_context_call` | TenantContext は生成箇所 allowlist 内のモジュールだけで構築できる | (i) | ☐ |
| `4641` |  | `_check_integrity_reference` | message | — | ☐ |
| `4682` |  | `_check_dynamic_call` | getattr による TenantContext 発行証跡内部への参照は禁止 | — | ☐ |
| `4729` |  | `_check_dynamic_call` | TenantContext の動的構築は生成箇所 allowlist を迂回する | — | ☐ |
| `4836` |  | `visit_ClassDef` | 可能なクラス基底起源に TenantContext が含まれるため拒否 | — | ☐ |
| `4859` |  | `visit_ClassDef` | 再輸出経由または起源不明の TenantContext 継承は禁止 | (v) | ☐ |
| `4874` |  | `visit_ClassDef` | TenantContext は生成箇所 allowlist 外で継承できない | (i) | ☐ |

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

## D. 落ちてはいけないもの — 新規負例(全数 43 件・負例総数 68 → 110)

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

| # | 判定事項 | 判定 |
| --- | --- | --- |
| D-1 | **緩和(B-2)を入れてもなお赤であるべき形**が、**この表の全件**で尽くされているか | ☐ |
| D-2 | **既存 68 件のうち 67 件は赤のまま。残る 1 件 `C5_CONTEXT_UNKNOWN_FACTORY` は射程の裁定で保証範囲外になり、負例から外れた** — 中身は `def forge_context(factory, t): return factory(t)` で、**まさに「守らないもの 4」の形**だった。**削除ではなく `test_parameter_bare_call_is_outside_condition_5_scope` で「緑であること」を固定**している。**この 1 件を落とすことを受け入れるか** | ☐ |
| D-3 | **保証範囲外にした 3 形**(引数 / 引数注釈 / 遅延束縛クロージャ)が**正例として緑を固定**されていること。**黙って消していない**ことの確認 | ☐ |

## E. 凍結基準の受理(全文 2 件)

### `contracts/tenant_boundary/base-allowlist.json`(contract_revision 13 → 14)

```text
source_commit  : 0db250c7996e72ba05c249a5cd1ea962f2bc4ea3
movement_fact  : movement_policy.movement_triggers に pass_fail_mapping が含まれるため、条件 5 の未解決 callable の既定値を名前駆動へ揃え、条件 2 に裁定 exact-set を置き、検査 visitor と flow の訪問漏れを閉じたことによる合否写像の変更が基準の移動に当たる。
reason         : TSK-440 で条件 5 の保証単位の明文化および条件 2 の裁定集合の導入により合否写像が動いたため。本受理では、射程を狭めた変更と厳しくした変更を同じ射影へ同時に記録した。両者の釣り合いが取れているかどうかは人間のレビュー事項である。承認者欄の marker「未承認(PR #72 のレビュー待ち)」は機構上の定数であり、本エントリの出所として PR #72 を指すものではない。
approved_by    : 未承認(PR #72 のレビュー待ち)
approved_on    : 未承認(PR #72 のレビュー待ち)
before(SHA-256): c46cac30740449759c7a0193ddd81ee0cf4b7ccabc24f4cff067ae7791bef6f7
after (SHA-256): 1f268abf209c18f9045a202533d6ea639491777960d3615d8df7df71d1d6d1a8
```

### `contracts/tenant_boundary/negative-fixtures.json`(fixture_set_revision 5 → 6)

```text
source_commit  : 0db250c7996e72ba05c249a5cd1ea962f2bc4ea3
movement_fact  : movement_policy.movement_triggers に pass_fail_mapping が含まれるため、検査 visitor と flow の訪問漏れ、相対 import、再輸出、条件 2 の裁定、および条件 5 の名前駆動境界を検証する負例 exact-set の変更が基準の移動に当たる。
reason         : TSK-440 で条件 5 の保証単位の明文化および条件 2 の裁定集合の導入により合否写像が動いたため。本受理では、射程を狭めた変更と厳しくした変更を同じ射影へ同時に記録した。両者の釣り合いが取れているかどうかは人間のレビュー事項である。承認者欄の marker「未承認(PR #72 のレビュー待ち)」は機構上の定数であり、本エントリの出所として PR #72 を指すものではない。
approved_by    : 未承認(PR #72 のレビュー待ち)
approved_on    : 未承認(PR #72 のレビュー待ち)
before(SHA-256): 6fdc311f0a0a429eef080017808edce854dbee70a06621a89712573e7d8194c1
after (SHA-256): 993156ac1edee4abbc92ec7b21657c9aff3f5df28bc02e7d4525d6adb0c71b6d
```

| # | 判定事項 | 判定 |
| --- | --- | --- |
| E-1 | `movement_fact` が**実際に動いた中身**を述べているか | ☐ |
| E-2 | `reason` の「射程を狭めた側と厳しくした側を同一の受理記録へ結び付け」が事実か | ☐ |
| E-3 | **`approved_by` / `approved_on` が未承認 marker のままであること**(承認はこの確認の結果として人間が行う) | ☐ |
| E-4 | marker が `未承認(PR #72 のレビュー待ち)` という**他 PR の名を借りた機構上の定数**であり、本エントリの出所が TSK-440 であることが `reason` に明記されていること | ☐ |
| E-5 | 他 5 資産が**無変更**であること | ☐ |

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
| B-3 TB007 の全送出点 | 16 | ☐ |
| C. 条件 2 の裁定 | 9 | ☐ |
| D. 落ちてはいけないもの — 新規負例 | 46 | ☐ |
| E. 凍結基準の受理 | 5 | ☐ |
| **合計** | **103** | ☐ |

**総合判定**: ☐ 承認 / ☐ 差し戻し(指摘を PR コメントへ)

**承認する場合**、契約資産 2 件の `approved_by` / `approved_on` を
未承認 marker から実名と日付へ更新する作業が残る(**本 PR では行っていない**)。
