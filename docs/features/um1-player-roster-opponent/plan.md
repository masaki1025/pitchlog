---
feature: um1-player-roster-opponent
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7
branch: feature/um1-player-roster-opponent
created: 2026-09-24
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-M1 選手・在籍・対戦相手チーム

## 1. 背景・目的

**Notion**: [TSK-393 U-M1 選手・在籍・対戦相手チーム](https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7)
**出所**: TSK-363 / [`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)(承認済 2026-09-13)`:212`
**計画段階の調査**: [research.md](research.md) — 調査サブエージェント 3 本 + 当方の原典実測。**本書の判断根拠は同メモを正とし、内容をここへ複製しない**(設計書 7.1-1)

**U-M1 は pitchlog 最初の製品コードになる。** 主所有 FR は次の 4 件:

| FR | 必須度 | 要求の骨子 |
| --- | --- | --- |
| [FR-015](../../requirements/requirements-pitchlog-2026-07-22.md#FR-015) 選手の登録 | Must | 不変の内部 ID / 名前・投・打 / **背番号は任意**・**一意制約を張らない**(同番号は警告のみ・OB 番号は再利用可)/ 記録時点の背番号で過去試合を表示 / 断中のその場登録 / **入部年度・学年を持たない** |
| [FR-017](../../requirements/requirements-pitchlog-2026-07-22.md#FR-017) 在籍ステータス管理 | Must(区分 3 つ)/ ラベルは Should | 現役・その他・OB の 3 区分固定 / **全区分可逆** / 一括変更は**プレビュー→確認→実行** / **対戦相手チームレコードの選手にも適用** / 変更はキャッシュ無効化トリガー |
| [FR-018](../../requirements/requirements-pitchlog-2026-07-22.md#FR-018) 誤登録選手のセルフ削除 | **Should** | プレイ紐づけゼロ → **非表示化(ゴミ箱 UI を経ない)** / 紐づく選手は **OB 化へ誘導** / **紐づけ判定と削除が同一トランザクション** / **進行中(未終了)試合があると削除不可** |
| [FR-039](../../requirements/requirements-pitchlog-2026-07-22.md#FR-039) 対戦相手チームレコード | Must | テナント内レコード・**テナント間で共有されない** / 試合作成を中断せずその場登録 / **類似名は重複警告** / **試合・選手が紐づくチームは削除不可でリネームへ誘導** / **付与によらず 404** |

### 着手時点の与件が覆った点(調査の結論)

> **U-M1 はコア領域(機械判定で確定)であり、降格条件は存在しない。**
> Notion カードの「コア判定(機械): 非コア」「降格条件: 6.3 の確定ゲートで (i) が確定すること」は、
> [`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:292-315`【承認後の是正】より前のスナップショット。
> **TSK-394 でも同一記述を確認済み**(葉 6 本が同型と見られる)。カード一括訂正の要否は PO 判断。

> **U-T1 の公開面は空で、現時点では DB に 1 行も到達できない。**
> 正本の依存は「U-T1」だけだが、**実効依存に TSK-424 を含む**(research.md 3-1)。

## 2. スコープ

**方針(人間の判断・2026-09-24)**: **ギリギリまで実装し、マージだけ外部タスク待ちにする。**
1 本の PR にまとめ、**第 1 群を実装して draft PR を開き**、外部依存が着地したら第 2 群を足してマージする。

### やること — 第 1 群(本計画で実装する。**経路を開かない**ので CI は green のまま)

- 選手・チームレコードの **DTO**(`backend/src/pitchlog/api/schemas/roster.py` 新設)
- **operation token 型**の定義(`backend/src/pitchlog/repositories/roster_tokens.py` 新設 — **registry へは登録しない**)
- **単体テストが唯一の呼び出し元**(`backend/tests/test_roster_schemas.py` 新設)
- 経路表・命名・ページング上限・在籍区分キーの確定 → [design.md](design.md)

### やること — 第 2 群(外部依存の着地後、本 PR に追記してマージ)

registry 登録 / セッション供給 / `route-registry.json` + `http-route-matrix.json` + lock / ルータ実装と `ROUTERS` 登録 /
`backend/tests/test_api_conventions.py:135` の期待値更新(述語 4)/ 越境テスト / FR-018 の削除ガード / `system_vocabularies` の seed

### やらないこと(所有者が別 — research.md 1-3)

スタメンの記憶・復元(**U-M2**)/ 試合作成時の相手チーム選択(**U-G1**)/ 試合の削除とゴミ箱(**U-D1**)/
キャッシュ無効化**契約**(**U-T1** — 発火点のみ U-M1)/ 選手統合・分割(**U-A2**)/ 移行のファンアウト・在籍棚卸し・名寄せ(**U-X5**)

### 面が切れていない箇所(単位分割の分担表に行が無い — 契約 4 `:182` に従い本書で明示する)

**FR-015 の第 4 受入基準**(断中の一時 UUID → 同期時にサーバーが正式 ID を確定・参照を置換)は
[`../../design/sync-protocol.md`](../../design/sync-protocol.md) が 4-4「一時 ID → 正式 ID の置換契約」C1〜C4(`:367-378`)・
参加区分「6 選手のその場登録」(`:589`)・ACK 保証 A4(`:923`)・原子境界 T6(`:1198`)として**同期側の契約に組み込んでいる**。
**面の切り方**: **一時 ID の発行・置換の機構は U-S1 が持ち、U-M1 は「サーバーが確定した正式 ID で選手を作る」側だけを持つ。**
U-M1 は同期セマンティクスの語彙(べき等キー・連番・墓標/改訂)を 1 語も持たない(4 節の条件②)。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` | **反映なし**(7 章の既決事項に従うのみ。再決定しない) | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/adr/` | **新設なし**(既決の制約の適用であり新しい決定を持たない。U-T1 と同じ判断) | — |
| `contracts/authz/route-registry.json` / `http-route-matrix.json` (+ lock) | **第 2 群で追記**(値域拡張の可否は TSK-346 / TSK-380 待ち — 4 節 R4) | PR レビュー |
| `docs/features/um1-player-roster-opponent/design.md` | **新設**(D1〜D6 の暫定規約) | PR レビュー |

## 4. 実装方針

**重さ分類 = コア領域**。根拠は **fail-closed の既定ではなく機械判定の確定**:
入口を開く → `route_id` の付与が正本の要求([`../../design/data-model.md`](../../design/data-model.md)`:2454`) →
`contracts/authz/*` を編集 → `.claude/core-areas.json:307`(`tenant-isolation`)に一致。
→ **sol xhigh・敵対レビュー・人間の逐行確認が必須**(降格の道は無い)。

詳細設計(経路表・DTO 定義・命名・暫定規約 D1〜D6)は [design.md](design.md) を正とし、本節では複製しない。

### 実測で確定した「進めない壁」(第 2 群が外部待ちになる理由)

| 壁 | 機構(実測) | 解除の所有者 |
| --- | --- | --- |
| **capability / operation registry** | `repositories/base.py:58-60` が `MappingProxyType({})`、`repository_contract.py:57-59` が 3 つとも `()`。**`backend/tests/test_authz_repository_contract.py:261` が「空であること」を assert**(docstring:「TSK-424 と所有単位の実装前は製品操作と越境関数を一件も開かない。」)。`repository_contract.py` は `contracts/tenant_boundary/repository-contract.json` からの**生成モジュール**(`SOURCE_DIGEST`)で手編集できない | **TSK-424** |
| **セッション供給** | `repositories/binding.py:38` の `_tenant_transaction(session, context)` は Session を引数で要求。**`backend/src` に `sessionmaker`/`Session(` が 0 件**。作る手段が `contracts/tenant_boundary/base-allowlist.json` の 5 シンボルに無い → 葉が作れば **TB005** | **未定**(誰も持っていない) |
| **RLS DDL(12-4 ゲート条件①)** | **`backend/migrations` に `CREATE POLICY`/`CREATE ROLE`/`ROW LEVEL SECURITY` が 0 件** | **TSK-344** |
| **認可経路レジストリの値域** | `route-registry.json` と `http-route-matrix.json` は **exact-set**(`scripts/check_authz_catalog.py:2437-2442`)で片側追加は必ず red。`route_kinds` は `{legacy_route, shared_data, control_read, management_operation}` の閉じた値域で、**検査器の定数 `ROUTE_KINDS`(同 `:92`)に固定**。**選手 CRUD を表す種別が存在しない** | **TSK-346 / TSK-380** |
| **`TenantContext` の生成** | `repositories/context.py:26`「テナント ID が認証済み主体のものであることは **API 層(TSK-217 / U-A1)の責務**」 | **U-A1**(ブロック中) |

### 非コアで通せる 5 条件 — **本単位には適用されない**が「面を混ぜない」規律として守る

[`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:254-258` が
「**対象(承認後の是正で 9 → 3): `U-00`/`U-01`/`U-02` の器 3 本だけ。葉 6 本は機械判定でコアが確定したので、本節の条件では通せない。
ただし 5 条件そのものは葉の計画書でも『面を混ぜない』規律として有効なので、下表は残す。**」と定めている。

**検査対象 = `git diff -U0 origin/develop...HEAD -- backend/src` の追加行。各式の一致 0 が合格。**
上流の「候補」を**そのまま確定**する(現時点の差分に実測で一致 0 を確認できるため)。

| # | 条件 | 確定した検索式(**一致 0 が合格**) | 許可側 |
| --- | --- | --- | --- |
| 1 | 新たな認可判定を追加しない | `\b(can_\|may_\|is_allowed\|has_permission\|check_.*_access\|require_role\|assert_.*_owner)` | U-T1 の公開関数の呼び出しのみ |
| 2 | 同期セマンティクスを扱わない | `\b(idempotenc\|idempotent_key\|seq_no\|sequence_no\|tombstone\|revision_no\|generation)\b` | — |
| 3 | NFR-018 の対象計算を含まない | `responsible_pitcher\|earned_run\|at_bat_result\|inning_state\|rbi\|era\|avg\|obp\|slg` | — |
| 4 | キャッシュ無効化契約に触れない | `\b(invalidate\|cache_clear\|evict\|purge_cache)` | `pitchlog.repositories.cache_invalidation` の公開シンボルのみ(第 2 群) |
| 5 | テナントデータは U-T1 の越境関数経由だけ | `\b(session\.(execute\|query\|scalars)\|select\(\|text\(\|engine\.\|raw_connection)` | U-T1 のリポジトリ基底の継承・呼び出しのみ |

**条件 3 の注意**(U-01 の先例 `../u01-dto-base/plan.md:150`): `era` は `operation` の部分文字列に一致する。
**差分行限定**で当て、語境界を守る。

### 面が切れなかったときの手順(`../product-impl-unit-split/plan.md:240-252` — DoD に入れることを同書が要求)

面が切れないと判明したら ① 本書に事実と典拠を書く ② 相手単位の所有者を特定する
③ **切り直しではなく「どちらが持つか」を人間へ上げる** ④ 決定を本書と相手単位の計画書の双方へ記録する。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**第 2 群を後から同じ表へ追記するため、ステップ記法に `/<N>` を書かない**
(表の総数と不一致になると現在地導出が「不整合」に落ちる — 設計書 6.1 の厳密文法③)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **選手・チームレコードの DTO を追加する** — `backend/src/pitchlog/api/schemas/roster.py` を新設し、`TeamRecordCreate`/`TeamRecordRead`/`PlayerCreate`/`PlayerUpdate`/`PlayerRead` を定義する。`BaseSchema`/`ReadSchema`/`EntityId`/`Timestamp` を再利用する | `backend/tests/test_roster_schemas.py` が green。背番号が任意で空文字を拒否すること・`PlayerUpdate` が `team_record_id` を含まないこと(R3)をテストで確認。`ruff check` / `ruff format --check` / `ty check` が green |
| 2 | **一覧要求の DTO にページ上限を課す** — 同ファイルに `PlayerListRequest(PageRequest)` を定義し、`limit` の上限 200 を強制する(D1)。`Page[PlayerRead]` を応答型として定義する | 上限超過が `ValidationError`、境界値 200 と下限 1 が通ることをテストで確認。`Page` の `next_cursor` が空文字を拒否することを確認。上記 3 コマンドが green |
| 3 | **operation token 型を追加する** — `backend/src/pitchlog/repositories/roster_tokens.py` を新設し、選手・チームレコードの操作 token を frozen dataclass(`slots=True`)で定義する。**registry へは登録しない** | token が `TenantOperationToken` の部分型で frozen/slots であること・`capability_id` が D6 の形式であることをテストで確認。**`test_authz_repository_contract.py` が引き続き green**(registry が空のまま)。`scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` の新規違反が 0 件 |

## 5. DoD(受け入れ基準)

Notion カードの DoD と同期。**第 2 群の項目は着地後に確認する**(本 PR のマージ条件)。

- [ ] **一覧はページングする**(NFR-005 — 全件読み込み型の集計を書かない)
- [ ] **削除は論理削除**(要件書 4.0-2。`Player`/`TeamRecord` とも `DeletionLifecycle.HIDDEN`)
- [ ] **経路表**(method / path / request DTO / response DTO / 既定拒否 / 越境テストのファイル)を [design.md](design.md) に書く
- [ ] **NFR-019 の越境テスト**を自経路ぶん持つ(裁定 C)— **第 2 群**
- [ ] **`backend/tests/conftest.py` の差分が 0 行**(`.claude/core-areas.json:326` の `backend/*conftest.py` に一致するため。fixture は `backend/tests/api_fixtures.py` へ置き明示 import する — U-00 の先例 `test_api_errors.py:7`)
- [ ] **`test_authz*` の命名を使わない**(同 `:319` に一致するため)
- [ ] pytest / ruff / **ruff format** / ty green
- [ ] 横断要求: **物理削除しない** / **テナント分離を全機能に適用** / **自動エスケープ**(NFR-023 — 選手名・チーム名・在籍ラベルは自由入力の発生源)
- [ ] **5 条件すべてに一致 0**(4 節の確定した検索式で実測)
- [ ] **面が切れなかったときの手順**を踏んだ(FR-015 第 4 受入基準 — 2 節に記録済み)

## 6. テスト計画

**第 1 群**(NFR-019 の「単体」):

| 対象 | 種別 | ファイル | 確認すること |
| --- | --- | --- | --- |
| DTO のバリデーション | 単体 | `backend/tests/test_roster_schemas.py` | 背番号が任意・空文字拒否 / `extra="forbid"` が効く / `PlayerUpdate` が未分類列を含まない(R3)/ 在籍区分キーが D4 の 3 値 |
| ページ上限 | 単体 | 同上 | `limit` の上限 200・下限 1 の境界 / `cursor`・`next_cursor` の空文字拒否 |
| operation token | 単体 | 同上 | frozen/slots / `capability_id` の形式 / registry が空のままであること |

**第 2 群**(NFR-019 の「越境」): 自経路ぶんの越境テストを**同一 PR** に含める(裁定 C・[`../../design/data-model.md`](../../design/data-model.md)`:2532`)。
合否は「越境が 1 件でもあれば fail」ではなく **「FR-034 の認可行列どおりに通り、行列外はすべて 404」** で判定する(要件書 `:933`)。
`test_authz*` を使えないため、**ファイル名は `backend/tests/test_roster_boundary.py` とする**(命名の衝突回避 — D5)。

**実行手順**(`backend/` で。CI と同じ順 — `.github/workflows/ci.yml:255-262`):

```
docker compose up -d                    # backend/tests/db/conftest.py が DB 必須テスト 0 件を失敗扱いにする
uv run ruff check .
uv run ruff format --check .            # backend では CI が強制する(AGENTS.md の注記はハーネス側のもの)
uv run ty check
uv run pytest -c pyproject.toml
```

**迂回検査は実装スケルトンの段階で当てる**(別タスクが 719 件出している — 後から直すと破綻する):

```
uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop
```

## 7. リスク

| # | リスク | 対応 |
| --- | --- | --- |
| **R1** | 第 2 群の解除に**外部所有者が 4 者**(TSK-424 / TSK-344 / TSK-346・TSK-380 / セッション供給の未定所有者)。1 つでも動かないとマージできず draft PR が長期滞留する | 第 1 群を独立して検証可能な形に保つ。滞留が長引いたら第 1 群の単独マージを人間へ提案する |
| **R2** | `test_owner.status: "implemented"` は**ハーネス側 `tests/` の pytest node ID** としか照合されない(`scripts/check_authz_catalog.py:2674-2685`)。`backend/tests/...` を書くと red | 第 2 群では **`planned` 止まり**にする |
| **R3** | `players.team_record_id` は immutability の protected / allowed いずれにも入らない**未分類列**(handoff `TSK-372`)。所属チーム変更の可否がコードから読めない | **`PlayerUpdate` の更新対象に含めない**。必要になったら TSK-372 へ上げる |
| **R4** | `system_vocabularies` に **seed が存在しない**(migrations に `bulk_insert`/`INSERT INTO` が 0 件)。選手を作るには `roster_status_key` の FK 先が要る | seed は migration = **5 領域すべてのコア paths**。**第 2 群で独立したコミット**に切る |
| **R5** | API 層は `api/**` の全ソース連結に対する部分一致検査を受け、**`Session`・`generation` を docstring・コメント含め 1 文字も書けない**(`backend/tests/test_api_conventions.py:22-37`) | D5 で命名を先に固定する。ステップ 1 の合格条件に含める |
