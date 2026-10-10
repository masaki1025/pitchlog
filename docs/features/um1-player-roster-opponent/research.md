---
feature: um1-player-roster-opponent
type: research
date: 2026-09-24
---

# 調査メモ: U-M1 選手・在籍・対戦相手チーム(TSK-393)

## 問い

1. **要件**: FR-015 / 017 / 018 / 039 が U-M1 に何を要求するか。関連 NFR(005 / 018 / 019 / 023)と 4.0-2 の効き方。他単位との分担境界
2. **旧システム**: 選手・在籍・対戦相手チームの実データ構造と移行制約。88 列互換出力との対応
3. **決定経緯**: U-T1 が確定させた契約、U-00 / U-01 の既定、単位分割の裁定、コア判定の現状

**調査方法**: 調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列委任し、**結論に効く事実はすべて当方が原典で再実測した**。下表の「実測」は当方の確認済みを意味する。

## 結論(要約)

1. **U-M1 は現時点で DB に 1 行も到達できない。** U-T1 の公開面(operation registry・製品 capability・越境関数・`TenantContext` 製品 allowlist)は**すべて空**で、埋める所有者は **TSK-424**。依存は「U-T1」だけではなく**実効的に TSK-424 を含む**(W-1)
2. **マージは TSK-344 待ち**。12-4 ゲートの通過条件①「RLS のポリシーとロールの DDL が実スキーマへ適用されている」が未充足(`backend/migrations` に該当 DDL **0 件** — 実測)(W-3)
3. **U-M1 はコア領域(機械判定で確定)**。Notion カードの「機械判定: 非コア」「降格条件あり」は**承認後の是正より前のスナップショット**で、正本では**降格条件は消えている**。**5 条件では通せない**
4. **選手・在籍・対戦相手のデータモデルは既決**(D-20〜D-23 / I-12 / I-13 / data-model 7 章 / ORM 実装済み)。計画書で**再決定しない**
5. **U-M1 が決める側に回るのは 4 つ** — ページサイズの上限・`limit` の既定値の要否・カーソル書式(または「決めない」明示)・経路表。いずれも **TSK-346 従属の暫定規約**として記録する

## 詳細と典拠

### 1. 要件突合(spec-checker)

#### 1-1. 主所有 4 FR の要求(要件書 = `docs/requirements/requirements-pitchlog-2026-07-22.md`)

| FR | 位置 | 必須度 | 要求の骨子 |
| --- | --- | --- | --- |
| **FR-015** 選手の登録 | `:356-364` | **Must** | 不変の内部 ID / 名前・投・打 / **背番号は任意** / 同番号は**警告のみ・DB の一意制約を張らない**・OB 番号は再利用可 / **記録した時点の背番号で過去試合を表示** / 試合中のその場登録(**断中はクライアント生成の一時 UUID → 同期時にサーバーが正式 ID を確定・参照を置換**)/ **入部年度・学年は持たない** |
| **FR-017** 在籍ステータス管理 | `:374-383` | **Must**(区分 3 つ)/ ラベル自由化は Should | 現役・その他・OB の 3 区分 / OB は候補から**完全除外** / その他は**初期表示に出ないが明示操作で選択可** / **全区分可逆** / **一括変更はプレビュー→確認→実行** / **対戦相手チームレコードの選手にも適用** / カルテ・試合準備画面からも変更可 / **変更はキャッシュ無効化トリガー** |
| **FR-018** 誤登録選手のセルフ削除 | `:385-392` | **Should** | プレイ紐づけゼロ → **非表示化(論理削除・ゴミ箱 UI を経ない)** / 紐づく選手は**削除不可で OB 化へ誘導** / **紐づけ判定と削除が同一トランザクション** / **当該チームに進行中(未終了)試合があると削除不可**(断中端末の未同期キューが参照している可能性があり**サーバー側のトランザクションでは検知できない**ため) |
| **FR-039** 対戦相手チームレコード | `:405-414` | **Must**(FR-001 の前提) | テナント内レコード・**テナント間で共有されない** / 試合作成を中断せずその場登録 / **類似名は重複警告(意図的なら登録可)** / 削除は 4.0-2 準拠・**試合や選手が紐づくチームは削除不可でリネームへ誘導** / FR-035 のチーム登録とは別概念 / **共同分析グループの付与によっても共有されない(付与によらず 404)** |

#### 1-2. 横断要求

- **NFR-005**(`:818`): 「集計は DB 側絞り込み・集計を基本規律とし、**全件読み込み型の集計を実装しない**」「**一覧系画面はページングする**」。測定方法は**コードレビューで全件読み込みの不在を確認**(`:819`)。**ページサイズの数値は要件書・付録 C のどちらにも無い**
- **NFR-018**(`:892`): 対象は**状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定**の列挙が正。**U-M1 の CRUD は対象列挙に含まれない**。ただし fail-closed 条項(`:895`)— 区分に割り当てられない対象計算が生じたら**実装を開始せず本書の改訂で区分を確定する**(対象外として逃がすこともしない)
- **NFR-019(b)**(`:933`): 越境テストの合否は「越境が 1 件でもあれば fail」ではなく「**FR-034 の認可行列どおりに通り、行列外はすべて 404**」で判定する。**発効条項** — 経路が実装され外から到達できるようになった時点でその経路について発効する
- **4.0-2**(`:161-165`): **物理削除しない**(利用者操作は論理削除まで)/ **当時の値で表示**(記録時点の背番号)/ 黙殺しない / 正本は DB の 1 系統
- **NFR-023**(`:967`): **選手名・チーム名**・語彙ラベル等は全出力経路で構造として解釈されない。自動エスケープ標準・生 HTML 挿入禁止
- **語彙保全規律**(`:175`): 使用実績のある語彙は**削除不可・無効化のみ**。改名は表示名の変更として ID 経由で全履歴に反映
- **FR-034 認可行列**(`:641`): 「**第三者として記録した対戦相手データ → 付与によらず不可 → 404**」

#### 1-3. 分担境界(`docs/features/product-impl-unit-split/plan.md` / `design.md`)

**`design.md:86-92` の分担表に FR-015/017/018/039 の行は 1 つも無い** = この 4 FR は分担先なしで U-M1 が単独で閉じる建て付け。近接単位:

| 面 | 持ち主 |
| --- | --- |
| スタメンの記憶・復元(FR-016) | **U-M2** |
| 試合作成時の相手チーム選択(FR-001) | **U-G1** |
| 試合の削除とゴミ箱(FR-019) | **U-D1** |
| キャッシュ無効化**契約** | **U-T1**(発火は各トリガー所有単位) |
| 選手統合・分割、管理コンソール(FR-035/037) | **U-A2** |
| 移行のファンアウト・在籍棚卸し・名寄せ(FR-038) | **U-X5** |

**面が切れていない箇所(要注意)**: FR-015 の第 4 受入基準(断中の一時 UUID → 正式 ID 置換)は同期プロトコル正本が
**4-4「一時 ID → 正式 ID の置換契約」C1〜C4**(`docs/design/sync-protocol.md:367-378`)、参加区分「6 選手のその場登録」(`:589`)、
ACK 保証 A4(`:923`)、原子境界 T6(`:1198`)として**同期側の契約に組み込んでいる**。
にもかかわらず分担表に FR-015 の行が無く、`plan.md:242-252` の「面が切れなかったときの手順」も **FR-007/010/011/019 しか列挙していない**。
→ **U-M1 の計画書が面を明示するのが正しい置き場**(`plan.md:182` 契約 4 / `:525`)。

#### 1-4. 要件に記載が無いもの(計画書側で「不明」と扱う)

- ページサイズ・一覧の既定ソート(要件書・付録 C のいずれにも無し)
- 在籍ステータスラベルの**初期ラベルの実体一覧**(`:381` は「初期ラベル同梱」と言うが付録 D-4 は球種等のみ)
- 非表示化した選手の**復元 UI**(要件に明示なし。`data-model.md:2017` の PO 裁定 `A-8`・`RQ-04` が「復元できる」まで)
- 選手プロフィール・測定履歴(パリティ裁定 A-2 で TSK-310 へ要件化を送り済み。**現条文に受け皿なし = U-M1 の射程外**)

**Won't(`:96-109`)との衝突は無い。** 隣接するのは「個人アカウント・入力者の識別」のみで、選手はログイン主体ではない。
関連して 10 章 `:1083`「**チーム管理者ロールの導入 = 導入せず**」があるため、**選手管理に役割分離を設けない**。

### 2. 旧システムの事実と移行制約(legacy-analyst)

#### 2-1. 旧の実データ構造

- **`player` は 4 属性のみ**: `チーム_id` / `背番号 TEXT NOT NULL` / `名前 TEXT NOT NULL` / `左右 TEXT NOT NULL` + `UNIQUE(チーム_id, 背番号)`(`docs/legacy/research/data-layer.md:31-39`)
- **「在籍」という実体は存在しない**。在籍区分列も年度列も from-to 期間列も無い。年度は `game.Season` / `試合日時` にしかない。
  **同一選手の複数チーム・複数年度は表現手段が無い**(別チームなら別 `player` 行)
- **業務キーは内部 ID ではなく `(チーム_id, 背番号)`**。CRUD 関数はすべて背番号キー(`data-layer.md:301-310`)。
  **背番号自体を更新する関数は資料に無い**(= 番号変更は削除+再登録相当)
- **卒業生の背番号を新入生が引き継げない**(`docs/improvements-from-baseball-scoring.md:118`)
- **対戦相手チームは自チームと同一の `team` テーブル**に同居し、`password_hash` の有無が実質の区別
  (`docs/legacy/baseball-scoring-db-structure.md:168`)。試合作成時に `ensure_team` で自動生成され、
  **相手選手も同じ `player` テーブルにフル登録**される
- **削除は物理 DELETE のみ**。退部・移籍・卒業の表現は無く、整理手段は物理削除しかなかった
  (`data-layer.md:304` / `improvements-from-baseball-scoring.md:125`)

#### 2-2. 88 列との対応

U-M1 に効くのは列 27/32/35(氏名)・20-25(走者氏名)・**63-71(登録名・背番号 = 「移行時に使用」)**・78-85(スタメン JSON)。
**「保持のみ」は 88 列中 列 72「入力項目」の 1 列だけで、U-M1 の射程外**(`docs/design/data-model.md:2265`)。

#### 2-3. 移行制約(U-M1 のテーブル形を縛るもの)

| # | 事実 | 典拠 |
| --- | --- | --- |
| 1 | **旧 `team.名前` はグローバル UNIQUE でテナント横断共有。新は共有しない** → **チーム・選手・`stamem`・在籍区分を所有テナント数だけ複製するファンアウトが必要** | `data-layer.md:28` / `data-model.md:1368-1400` |
| 2 | 件数突合は**旧原本行 / テナント別コピー / 隔離・未解決**の 3 区分 | `data-model.md:1402-1411` |
| 3 | 旧は `UNIQUE(チーム_id,背番号)` が成立。**新は背番号に DB 一意制約を張らない(P-15)** — 引きずると OB 番号再利用・複製・移行が全部詰む | `data-layer.md:39` / `data-model.md:1424`・`:1481` |
| 4 | **選手参照は氏名文字列が本体**。`play_player_link` は**背番号+氏名が一意に解決できた場合のみ INSERT する best-effort で欠損があり得る** | `data-layer.md:75`・`:385` |
| 5 | カルテ 4 系統は**氏名+チーム名テキストキー**で改名・同姓同名に弱く**孤児化する** | `data-layer.md:372` |
| 6 | 旧に在籍概念が無いので**全員「現役」で取り込み → 移行後の在籍棚卸し(歴代選手の一括 OB 化)が 8 章 DoD** | `baseball-scoring-db-structure.md:309` / 要件書 `:383` |
| 7 | **旧 `左右` 1 列 → 新「投」「打」2 属性のギャップ**。どちらへ写し他方をどう扱うかは**資料上未決** | `data-layer.md:38` / 要件書 `:358-360` |
| 8 | 旧は**全件読み込み型**(`get_all_players_with_team` は引数なし・ページングなし。`member_df` は全チーム選手を保持)。**検索・絞り込み UI は旧に存在しない** | `data-layer.md:308` / `services-shell.md:89`・`:182` |
| 9 | 規模: 「1 チーム数十名 × 年次入れ替わり」「無期限(卒業選手は OB 化)」 | `requirements-tsukuba-pss-v0.2.md:457-458` |

#### 2-4. 旧資料間の矛盾(裁定済み — U-M1 の判断には影響しない)

`data-layer.md:17` は「テーブルは全 12 種」、`baseball-scoring-db-structure.md:17` は「13 個」で `game_lineup_snapshot` の有無が食い違う(CASCADE の有無・接続プール種別も同様)。
**当方の裁定**: `data-model.md:2634` の **裁定 `RQ-07`(`A-1`・山田正輝・2026-09-08)** が
「**旧側の存在は原典間で矛盾するが、存在しなければ移行 0 件で終わるだけ**」として**既に処理済み**。
`docs/design/sync-protocol.md:2105` も同 3 件を「移行仕様タスクが担う・本書の結論には用いない」と申し送っている。
**したがって U-M1 の計画では扱わない。**

### 3. 決定経緯・既存契約(decision-tracer)

#### 3-1. 【最重要】U-T1 の公開面は空 — U-M1 は DB に到達できない(W-1)

**すべて当方の実測**:

| 事項 | 実測値 | 典拠 |
| --- | --- | --- |
| operation registry | `_OPERATION_REGISTRY: Mapping[...] = (MappingProxyType({}))` — **空** | `backend/src/pitchlog/repositories/base.py:58-60` |
| 製品 capability / token 型 | `PRODUCT_CAPABILITY_IDS = ()` / `PRODUCT_OPERATION_TOKEN_TYPES = ()` | `repositories/repository_contract.py:57-58` |
| 越境関数 registry | `CROSS_TENANT_FUNCTIONS = ()` | 同 `:59` |
| `TenantContext` 生成 allowlist | `ALLOWED_TEST_MODULES = ("test_authz_tenant_context",)` / **`ALLOWED_PRODUCT_MODULES = ()`** | `repositories/tenant_context_contract.py:25-26` |

U-T1 自身がこれを**意図として**書いている —
「製品 capability 集合と越境関数 registry は**初期値ともに空集合**とし…**製品表操作は TSK-424 の表分類から生成する capability を受けて初めて有効化する**」
(`docs/features/tenant-boundary-enforcement/plan.md:174` / `design.md:421`)。

**帰結**: U-M1 の依存は正本上「U-T1」だけ(`product-impl-unit-split/plan.md:212`)だが、**実効的に TSK-424 にも依存する**。
計画書がこれを明示しないと「作れない計画」になる。

**関連(W-2)**: `backend/src` に `sessionmaker` / `Session(` が **0 件**(実測。唯一の一致は ORM の `class AdminSession`)。
基底は `_session` を抽象プロパティで要求するが、**それを満たす手段を U-T1 は公開していない**。
**セッション供給を誰が所有するかの決定は見つからない(不明)**。

#### 3-2. 【重要】マージは TSK-344 待ち(W-3)

12-4 ゲートの通過条件は「**① RLS のポリシーとロールの DDL が実スキーマへ適用されている ② その実スキーマに対して越境テストが green**」(`data-model.md:2529`)。
**実測: `backend/migrations` に `CREATE POLICY` / `CREATE ROLE` / `ROW LEVEL SECURITY` が 0 件。**
産出者は **TSK-344**(`product-impl-unit-split/plan.md:431`)。U-T1 は入口を開かないので対象外だったが、
「**待つのは『入口を開く単位』(帯 2 の葉・帯 3)である**」(同 `:436`)。
→ **着手は可能・マージは TSK-344 待ち。** 計画書に「マージの条件(着手とは別)」を書き、`data-model.md:2534` の判定記録を残す。

#### 3-3. コア判定は機械判定で確定済み — 降格条件は消えている

`product-impl-unit-split/plan.md:292-315`【**承認後の是正】(i) は機械判定で閉じた**】(2026-09-13・ADR-004 の approved を受けて):

> 本書の承認と同日、承認の直後に PR #60 がマージされ `data-model.md` v0.3 が approved になった。その `12-4` が次を要求する(`:2454`):
> 「**同ファイル(`contracts/authz/http-route-matrix.json`)に `route_id` を持たない HTTP の入口を開く PR は、同一 PR でその入口へ `route_id` を与える。**」
> `contracts/authz/http-route-matrix.json` は `tenant-isolation` のコア paths である。
> **帯 2 の葉 6 本はすべて DB のデータへ到達する入口を開くので、機械判定でコアになる。**
> **帰結**: **非コアで通せるのは器 3 本だけである**(承認時は 9 本と書いていた)。
> **降格条件は消えた — 6.3 の確定ゲートで (i) が確定しても、機械判定が独立にコアと判定する。**

**実測による裏取り**:
- `.claude/core-areas.json:307` に `"contracts/authz/*"`(`tenant-isolation` エリア配下)
- `contracts/authz/http-route-matrix.json` の `route_id` を全数列挙 → `ROUTE:FR-020`〜`FR-032` / `SHARED:*` / `CONTROL:*` / `MANAGEMENT:*` のみ。
  **`ROUTE:FR-015 / 017 / 018 / 039` は存在しない** → U-M1 は新規付与する側

**Notion カードとの食い違い**: カード(TSK-393)は「コア判定(機械): 非コア」「降格条件: 6.3 の確定ゲート(7.3)で (i) が確定すること」と書くが、
これは `plan.md:332-340`「**カードの `コア判定` は起票時点の既定 = (ii) で埋める**」に従った**是正前のスナップショット**。
**TSK-394(U-M2)にも同一の記述があることを実測で確認した。葉 6 本すべてが同型と見られる。**
→ 計画書に「**(i) が確定すれば降格**」と書くとこの是正と矛盾する。**U-T1 が採った形**
(「Notion カードとの食い違い」表で人間の判断を求める — `tenant-boundary-enforcement/plan.md:192-198`)に倣う。

#### 3-4. コア化の経路は 2 つ — 置き場の選択が逐行確認の範囲を変える(W-6)

| パス | 判定 | 典拠 |
| --- | --- | --- |
| `contracts/authz/*` | **tenant-isolation のコア** | `.claude/core-areas.json:307` |
| `backend/src/pitchlog/repositories/*` | **tenant-isolation のコア**(U-T1 が登録した) | 同 `:361` |
| `backend/tests/test_authz*.py` | 同上 | 同 `:319` |
| `backend/*conftest.py` | 同上 | 同 `:326` |
| **`backend/src/pitchlog/api/**`** | **どの area にも `guard_paths` にも該当しない = 非コア** | 一覧に存在しない(実測) |

→ **リポジトリを `repositories/` に置くと `contracts/authz/*` とは別経路でも機械判定コアになる。**
これは TSK-363 承認時点(2026-09-13)には存在しなかった効果(U-T1 が後から paths を登録したため)。**計画書で明示的に判断する。**

**`core-areas.json` 自体の編集要否**: 上記のとおり `repositories/*` と `contracts/authz/*` は**既に glob で被覆済み**なので登録不要。
`api/**` は非コアのまま。→ **現時点で `core-areas.json` を編集する必要は見当たらない**(見つかれば #74 の `verify_area_path_baseline()` の制約でコミット事前分割が要る)。

#### 3-5. DoD 2 件の機構(事故由来ではない)

- `plan.md:465`「**`backend/tests/conftest.py`** — 既に存在する(187 バイト)。新設しないだけでは不十分で、**1 行でも編集したら `backend/*conftest.py` に一致してコア**。fixture は `backend/tests/api_fixtures.py` に置き明示 import する」
- `plan.md:466`「`test_authz*` — **葉は使わない**。逆に U-T1 は**意図的に** `test_authz_tenant_binding.py` と命名して機械判定を効かせる」
- リスク⑤(`:482`)は**予防的リスク**であって実現した事故ではない(実現印はリスク①のみ)

#### 3-6. 5 条件の現在の位置づけ

`plan.md:254-277` の柱書: 「**対象(承認後の是正で 9 → 3): `U-00` / `U-01` / `U-02` の器 3 本だけ。
葉 6 本は機械判定でコアが確定したので、本節の条件では通せない。
ただし 5 条件そのものは葉の計画書でも『面を混ぜない』規律として有効なので、下表は残す。**」

検索式は**候補**であり確定は各単位の計画書が行う(`:275-277`)。条件②の候補式は
`\b(idempotenc|idempotent_key|seq_no|sequence_no|tombstone|revision_no|generation)\b` という**語彙 grep** で、
FR-018 の「同一トランザクション」「未同期キュー」も FR-015 の一時 UUID も**この語彙には当たらない**。
→ **「条件②に抵触するから FR-018 を切り出す」という動機は無い。**(切り出し判断は §4 の実装可能性の問題として残る)

#### 3-7. 【重要】迂回検査 TB004 が U-M1 の自然な命名を禁じる(W-4)

**実測**: `contracts/tenant_boundary/base-allowlist.json` に

- `:196` `"(?:^|_)(?:roster_status_change|change_roster_status)(?:_|$)"`
- `:189` `"(?:^|_)(?:player_merge|merge_player|player_split|split_player|player_identity)(?:_|$)"`
- `:185` `"(?:^|_)undo(?:_|$)"`

→ **在籍区分変更を主所有する U-M1 は `change_roster_status` / `roster_status_change` という識別子を `backend/src` の差分行に書けない。**
許可されるのは `pitchlog.repositories.cache_invalidation` の公開シンボルの import/呼び出しのみ。
なお既存 ORM 列名 `roster_status_key` は**トークン境界が違うため一致しない**(パターンの形から確認)。

**検査器の使い方**: `scripts/check_tenant_boundary_bypass.py` に `--base-ref`(`:4029`)。既定は `DEFAULT_BASE_REF`(`:3965`)。
**実装スケルトンの段階で当てる。**

#### 3-8. U-00 / U-01 が確定させた既定

**器(U-00)**:
- `create_app() -> FastAPI` が唯一の生成口。`ROUTERS: tuple[APIRouter, ...]` は**モジュールトップレベルの静的タプル**(動的探索を使わない — ADR-003 D-11)
- 経路記述 6 規約(`u00-api-shell/design.md:124-139`): `response_model` 明示 / `operation_id` 明示(snake_case `<領域>_<資源>_<動作>`)/
  `route-registry.json` の管理操作 8 件と重ねない / `route_id` は別軸で正は `http-route-matrix.json` / `tags` と `summary` は日本語
- エラー封筒 `{"error": {"message": ...}}`、**封筒に `code` を置かない**、**403 を受けたら 404 へ落とす(fail-closed)**、422 を 400 に読み替えない
- **例外メッセージ自体のマスキングは器の射程外 = 各単位の責務**(`design.md:110`)

**DTO 基盤(U-01)**: `backend/src/pitchlog/api/schemas/base.py`
- `PageRequest.limit: int` — **必須・既定値なし・下限 1・上限なし** / `cursor: str | None` — 空文字拒否
- `Page[ItemT]` — `next_cursor: str | None`(空文字拒否)・**`total` を持たない**
- **「`cursor` / `next_cursor` の中身は不透明で、書式は `U-01` で決めない(葉と `TSK-346` の判断)」**(`u01-dto-base/design.md:152`)
- **「件数上限の判定と拒否は各葉の責務であり、この型は値を詰めない」**(`schemas/base.py:38-40`)
- **「既定件数・上限件数の値は各葉の単位か設定値の正本が持つ」**(`design.md:200`)
- 根拠の層: **(A) 要件の直接帰結 = 破ってはならない / (B) U-01 の設計判断 = `TSK-346` が別の形を定めたら `TSK-346` が正**
- **`generation` を docstring・コメントにも書けない**(既存規約テストが `api/**` 全文連結に部分一致 — `u01-dto-base/plan.md:174`)

**前例**: U-00 は TSK-346 への申し送り 2 件(403→404 の fail-closed 写像 / 封筒に `code` を置かない)を
「**TSK-346 に従属する暫定規約**として `design.md` 2-2 (B) に記録」した(`docs/worklog/2026-09-16-u00-api-shell.md:124`)。**U-M1 も同じ形で残す。**

#### 3-9. 既決事項(計画書で再決定しない)

- **D-20**(選手 ID 管理)/ **D-21**(スタメン記憶 = 最後の 1 件・選手 ID で復元)/ **D-22**(在籍 3 区分固定 + ラベル自由・全区分可逆)/ **D-23**(削除の権限構造)— `docs/requirements/requirements-draft-pitchlog.md:159-187`
- **I-12**(選手識別を名前文字列 → 選手 ID)/ **I-13**(在籍ステータス導入)/ **I-14**(削除をゴミ箱方式・物理削除しない設計に強化)
- **data-model 7 章**: `kind`(`self`|`opponent`)で自他を判別し **`tenant_id` では判別しない**(敵対レビュー P0-1 の是正 `:1335-1347`)/
  **`UNIQUE (tenant_id) WHERE kind='self'`・`kind` は不変**(`:1348-1350`)/ **チーム名に一意制約を置かない**(`:1363-1364`)/
  **背番号に一意制約なし(P-15)**・**入部年度・学年を持たない(P-17)** / **当時の背番号の正本はイベント側**(先発 = スタメン / 途中出場 = 交代イベント。`:1430-1462`)
- **ORM は実装済み**: `backend/src/pitchlog/db/tenant_isolation/models.py` の `TeamRecord`(`:84-139`)と `Player`(`:142-219`)。
  `Player` の更新可列 = `name` / `throws` / `bats` / `uniform_number` / `roster_status_key` / `roster_label_key` / `hidden_at`、`protected_columns={"id"}`
- **キャッシュ無効化トリガー 14** = 在籍区分の変更。**対象範囲は ④ 共有集計だけ**(`data-model.md:2069`)。
  API は `build_cache_invalidation_request`(`repositories/cache_invalidation.py:312-386`)で、
  トリガーは `CacheInvalidationTrigger.ROSTER_STATUS_CHANGE`、対象範囲は **`{CacheScope.SHARED_AGGREGATE}` ちょうど**(過不足は `ValueError`)

### 3-10. 【方針決定後の実測】「どこまで進めるか」の到達境界

**方針**(2026-09-24・人間の判断): **ギリギリまで実装し、マージだけ TSK-424 待ちにする。**
その「ギリギリ」がどこかを実測で確定した。**境界は「HTTP 経路を開く直前」**である。

#### 進められる(CI green を保てる)

| # | 内容 | 根拠 |
| --- | --- | --- |
| 1 | **DTO(`api/schemas/`)** — 選手・チームレコードの request/response。U-01 の `BaseSchema` / `ReadSchema` / `EntityId` / `Timestamp` / `PageRequest` / `Page[T]` に乗る | DB に触れない |
| 2 | **リポジトリと operation token 型の定義**(クラスとして) | registry 登録をしなければ既存テストに触れない |
| 3 | **経路表と識別子の確定** — **TB004 の禁止語を避けた命名**を先に固定する | `base-allowlist.json:185`・`:189`・`:196` |
| 4 | **5 条件の検索式の確定**(葉では非コア通過の手段ではないが「面を混ぜない」規律として) | `product-impl-unit-split/plan.md:275-277` |
| 5 | **述語 4 の決定を置く** — `backend/tests/test_api_conventions.py:135-143` の `test_router_routes_are_only_meta_routes` は `len(routes) == 2` と `{"/health","/version"}` を固定しており、**経路を 1 本でも開くと落ちる**。同ファイルは `test_authz*` に一致しないので**非コア**であり U-M1 が編集できる。U-01 が「**決定は存在しない・U-T1 と葉の単位が最初に踏む**」と申し送っており(`u01-dto-base/plan.md:279-282`)、**U-T1 が経路を開かなかったので U-M1 が最初に踏む** | 実測 |

#### 進められない(外部タスク待ち — ここがマージ待ちの実体)

| # | 内容 | 阻む機構(実測) |
| --- | --- | --- |
| 6 | **capability / operation token の registry 登録** | `backend/tests/test_authz_repository_contract.py:261-272` の `test_product_capabilities_tokens_and_cross_tenant_registry_are_empty` が **`PRODUCT_CAPABILITY_IDS == ()`・`_OPERATION_REGISTRY == {}`・`CROSS_TENANT_FUNCTION_REGISTRY == frozenset()` を固定**。docstring は「**TSK-424 と所有単位の実装前は製品操作と越境関数を一件も開かない。**」。加えて `repository_contract.py` は `contracts/tenant_boundary/repository-contract.json` からの**生成モジュール**(`SOURCE_DIGEST` 付き `:1-8`)なので**手編集できない** |
| 7 | **セッション供給** | `_tenant_transaction(session, context)` は **Session を引数で要求する**(`binding.py:34-37`)が、**作る手段が `base-allowlist.json` の 5 シンボルに無い** → 葉が作ると TB005。所有者未定(W-2) |
| 8 | **越境テスト** | 12-4 通過条件①(RLS DDL の実スキーマ適用)が未充足 = TSK-344 |
| 9 | **HTTP 経路を実際に開く** | 6・7 が無いので開いても 500。かつ開いた瞬間に 12-4 の「同一 PR に外から直接叩くテストを含む」義務が発生する(`data-model.md:2532`) |

#### API 層の追加制約(実測 — 識別子設計に先に効く)

`backend/tests/test_api_conventions.py` は **`api/**` の全ソースを連結して部分一致**で検査する:

- `_DATABASE_TERMS`(`:21-29`)= `sqlalchemy` / **`Session`** / **`engine`** / `session.execute` / `select(` / `text(` / `raw_connection`
- `_SYNCHRONIZATION_TERMS`(`:30-36`)= `idempotenc` / `seq_no` / `tombstone` / `revision_no` / **`generation`**

→ **API 層には `Session` も `generation` も、docstring・コメントを含めて 1 文字も書けない。**

#### 帰結: 実装ステップを 2 群に分ける

- **第 1 群(いま実装する)**: 上表 1〜5。**経路を開かないので CI は green のまま**
- **第 2 群(TSK-424 + TSK-344 の着地後)**: 上表 6〜9。**ここを入れて初めてマージ可能**

## 未解決・申し送り

### 人間の判断が要るもの

1. **【着手の前提】TSK-424 への実効依存**(W-1)— U-T1 の公開面が空で、製品表操作の capability は TSK-424 が産出する。
   **U-M1 の実装ステップをどこまで進められるか**(スキーマ・DTO・経路の形まで作って capability 待ちにするか、TSK-424 を待つか)は計画方針の判断
2. **【マージの前提】TSK-344 待ち**(W-3)— RLS DDL が実スキーマに無いので 12-4 ゲートを通過できない
3. **【射程】FR-018 を切り出すか → 当方の推奨は「残す」**。条文(要件書 `:392`)を逐語で読み直した結果、
   条件は「**当該チームに進行中(未終了)の試合が存在する**」という**状態の問い合わせ**であり、
   「断中端末の未同期キューが当該選手を参照している可能性があり、サーバー側のトランザクションでは検知できないため」は
   **この保守的な規則を採った理由の説明**であって、機構要件ではない。**U-S1 の同期機構は要らない。**
   必要なのは ① プレイ紐づけゼロの判定 ② 進行中試合の存在判定 ③ ①②と削除の同一トランザクション化の 3 つで、
   いずれも読み取りで閉じる(試合の ORM は `backend/src/pitchlog/db/game_state/models.py` に実装済み)。
   なお FR-018 は **Should**、FR-015/017/039 は **Must**
4. **【所有者未定】`TenantRepositoryBase._session` を満たす手段を誰が持つか**(W-2)—
   器(U-00 / U-01)でも U-T1 でもなく**誰も持っていない**。**U-M1 の射程で決めるべきではない**。
   既定案: capability と一体でないと動かないため **TSK-424 の射程に含める**
5. **【カードの陳腐化】** Notion カードのコア判定が正本の【承認後の是正】より古い。**TSK-394 でも同一の記述を確認済み**で葉 6 本すべてが同型と見られる。
   カード側への訂正の要否は PO の判断

### 計画書が決める(TSK-346 従属の暫定規約として記録する)

5. **ページサイズの上限** と **`limit` の既定値を置くか**(U-01 が意図的に置いていない)
6. **カーソルの書式**、または「決めない」ことの明示
7. **経路表**(method / path / request DTO / response DTO / 既定拒否 / 越境テストのファイル)
8. **リポジトリの置き場**(`repositories/` に置くとそれ自体でコア paths — W-6)
9. **5 条件の検索式の確定**(葉では非コア通過の手段ではないが「面を混ぜない」規律として有効)

### 決定が存在しない(原典で確認できなかった)

- **製品コードへのセッション供給**を誰が所有するか(W-2)
- **在籍区分変更のキャッシュ無効化「発火」の受け皿**(U-T1 は契約と API までで発火を持たない。W-5)
- **`http-route-matrix.json` の新規行の `test_owner` に何を書くか**(裁定 C は「各 FR の実装タスクが持つ」と言うが、契約資産の記法への落とし込みは TSK-380 の射程。W-9)
- **述語 4(経路ちょうど 2 本)を葉がどう扱うか** — U-01 が「決定は存在しない」「U-T1 と葉の単位が最初に踏む」と明記(`u01-dto-base/plan.md:279-282`)。
  U-T1 は経路を開かなかったので **U-M1 が最初に踏む**(W-8)
- **旧 `左右` 1 列 → 新「投」「打」2 属性**の写し方(§2-3 #7)
- **U-M1 の ADR 要否**についての決定
