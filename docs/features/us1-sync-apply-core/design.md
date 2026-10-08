---
feature: us1-sync-apply-core
type: design
date: 2026-10-08
---

# 詳細設計: U-S1 同期適用核(TSK-391)

本書は [plan.md](plan.md) 4 節から参照する詳細設計である。意味規則の正本は `docs/design/sync-protocol.md`(以下 SP。v0.4)、物理写像の正本は `docs/design/data-model.md`(以下 DM)5-4 節。**本書は正本の規則を再定義しない**。正本の節を、どのモジュールのどの関数が実装するかを対応づける。調査とスパイクの典拠は [research.md](research.md) にある(以下「スパイク S-n」は research.md の「スパイクの結果」節を指す)。

## 1. 置き場とモジュール構成

新しい製品コードは `backend/src/pitchlog/sync/` に置く。`backend/src/pitchlog/db/` には 1 ファイルも足さない(`docs/features/product-impl-unit-split/plan.md:467`)。同期表への SQL は `backend/src/pitchlog/repositories/sync_apply.py` に、UM01(#95)の operation 登録形式で置く。テストは平場の `backend/tests/test_sync_apply_*.py` に置く(同 `plan.md:464`。`backend/tests/db/` は全 5 領域に一致するため使わない)。

| モジュール | 責務 | 正本 |
| --- | --- | --- |
| `sync/model.py` | 要求・イベント・A5・境界結果(B1〜B14)・ACK の結果オブジェクトの型 | SP 6-2・6-3・7-1 |
| `sync/ports.py` | 注入境界 3 種と、ポートへ渡す制限付きの書き手(2 節) | SP 9-2(判定の所有者) |
| `sync/idempotency.py` | ④ D5 の内部分類(DI1〜DI5・I1〜I4)、イベントのトランザクション内での再照合、内容同一性 | SP 4-5・6-2 |
| `sync/prefix_path.py` | P1・P2 の 1 イベントの適用(T1+T6・T2・T3・T4)、墓標・改訂、一時 ID 写像 C1〜C4 | SP 6-1・8-1 |
| `sync/ordering.py` | T5(O1 の直列化・O2 の局所再採番・O4 の同値停止) | SP 5-5・8-1、DM 5-4 の T5 |
| `sync/rejection.py` | P5 / T9(B3a・B3b)と P4 / T8(B4・退避) | SP 8-1・9-2、DM 5-4 の M10 |
| `sync/change_path.py` | P3(③-b 復旧世代、B8〜B14、T7・I5、I6 の `accepted_at`) | SP 6-2 の P3 表・6-3 の P3 独立境界結果 |
| `sync/invalidation.py` | I5 の配信: 未配信の無効化意図を配信先ポートへ渡し、完了まで冪等に再試行する | SP 8-1 の T7・I5 |
| `sync/gate.py` | ③-a RG1 と ⑧ のコミット直前再検証(同期経路の範囲) | SP 6-2・6-3 の RG1 |
| `sync/apply.py` | 公開入口。1 要求 = 単一の (試合, D4)。段階③〜⑧の順序、D1 昇順の外部結果の確定、ACK の合成 | SP 6-2・6-3・7-1 |
| `sync/crash_points.py` | 名前付きのクラッシュ注入点(テストからだけ有効化) | SP 10-2・11-4 U-8、DM 5-4 の M20 |

**HTTP 入口は作らない**(裁定 R-3)。`sync/apply.py` の公開関数は、認証・認可済みの `TenantContext` と要求オブジェクトを受け、結果オブジェクトを返す。wire 形式への写像は、TSK-331 の後の入口 PR が持つ。

## 2. 注入境界とポートの拘束(裁定 R-2・スパイク S-2)

判定の所有者が U-S1 ではないものを Protocol で受ける。本物の実装は所有単位が差し込む。U-S1 のテストは合成実装を使う。製品コードには既定実装を置かない(未接続のまま本番経路が通ることを防ぐ。fail-closed)。

| ポート | 何を返すか | 所有単位 | 呼ぶ段階 |
| --- | --- | --- | --- |
| `RecordingRightsPort` | V12 の成否(VF1〜VF6)、要求作成時の復旧世代が現復旧世代と一致するか、復元調整中か(RG1) | U-R1(TSK-392)。RG1 の所有者は SP 9-2 に記載がない(research B-3) | ③-a・③-b・⑤・⑧ |
| `ProjectionPort` | T4 の投影更新(DM 5-4「サーバー側の T4 は投影の更新」) | U-X1(凍結中) | T4 |
| `ContentValidationPort` | ⑦ / P3 ⑥ の内容検証の可否と理由 | U-X1・U-G2 | ⑦・P3 ⑥ |
| `InvalidationSinkPort` | I5 の配信先(キャッシュ層) | 未定(キャッシュ層の所有単位。research の未解決) | `sync/invalidation.py` |

**ポートの拘束**: スパイクで、ポートの署名にハンドルを必須にしても、ポートが独自の `tenant_transaction_scope` を開いて書くことは防げないと分かった(スパイク S-2。外側をロールバックしても投影行が残った)。そこで 2 重に拘束する。

1. ポートには `handle` も `TenantContext` も渡さず、**operation token を受け付けるだけの書き手**(`PortWriter`)を渡す。書き手は適用核のトランザクションで token を実行する。ポートは SQL を直接実行できない
2. **ポートの実装は `TenantContext` を発行できない**。発行は既存の allowlist(`backend/src/pitchlog/repositories/tenant_context_contract.py` の `ALLOWED_PRODUCT_MODULES`)が許したモジュールに限られる。ポートは文脈を受け取らず作れもしないので、**どのスレッドでも**独自の `tenant_transaction_scope` を開けない(計画レビュー 2 周目: 同じスレッドの検査だけでは別スレッドを防げない)
3. 多層防御として、**適用核のトランザクションが開いている間は、同じスレッドで新しい `tenant_transaction_scope` を開けない**実行時の検査も足す(適用中の印をコンテキスト変数に立て、入口で拒否する)。repositories の基底に触れるので tenant-isolation のコア(4 節と同じステップ)

4. **ポート実装モジュールの登録表**: 適用核は、`sync/ports.py` の登録表にあるモジュールのポートだけを受け付ける(実行時)。登録表のモジュールは、pitchlog パッケージ内の推移的な import に、トランザクション・文脈・**DB 接続**・スレッド・非同期実行のモジュール(`pitchlog.repositories.transaction`・`pitchlog.repositories.context`・`pitchlog.db.engine`・`sqlalchemy`・`psycopg`・`threading`・`concurrent.futures`・`asyncio`・`multiprocessing`)を含めてはならない(静的検査。計画レビュー 4 周目: `pitchlog.db.engine` から別接続を作れば、同じスレッドでもスコープの拒否を通らずに書ける)

試験: ① ポートの署名に `TenantContext`・ハンドル・session が現れない(静的)② **テスト中だけ合成ポートを登録表に足し**(製品の登録表は空のまま。monkeypatch で差し込む)、同じスレッドで独自スコープを開こうとするポートを差し込むと、**ポートが呼ばれた後に**スコープの入口で拒否され(呼び出しと拒否を spy で記録して確かめる)、適用が失敗し何も残らない ③ 登録表にないポートは、呼ばれる前に拒否される ④ 禁止モジュール(DB 接続を含む)を推移的に import するモジュールを登録すると静的検査が落ちる(負例: `pitchlog.db.engine` から別接続を作るポート)

**残る穴(R-12 で受容)**: 外から有効な文脈を持ち込み、禁止モジュールを経由せずに別の実行単位へ書き込みを預け、待たずに戻るポート(例: 動的 import・外部プロセス)は、アプリの層では止められない。崩れるのは同じテナントの中の原子性で、テナント分離は破れない(RLS は効く)。逐行確認で防ぐ。**完全な遮断は DB 側**(投影の表に、適用核がトランザクション内で立てる印を要求するトリガ)で、表の持ち主の U-X1 が本物の投影ポートを作るときに入れる(申し送り)

## 3. トランザクションの単位と D5 の再照合(スパイク S-1・S-5)

- SP 8-1「単位は 1 要求ではなく連続して適用できた範囲」「T 要素は 1 イベントごとに束ねてよい」。U-S1 は **1 イベント = 1 トランザクション**を採る。スパイクで、この単位なら名前付き注入点を置け、どこで止めても全部確定か全部未確定になることを確かめた(スパイク S-1)
- 1 要求の流れ: ③認可(`TenantContext` 束縛済み)→ ③-a RG1 → ④ D5 の全件分類(読み取りだけ・内部候補)→ D1 昇順に、イベントごとのトランザクションで「D5 の再照合 → ⑤〜⑧」→ 最初の B2・B3・B4 で停止 → 以降を未処理にして ACK を合成する
- **D5 の再照合**: ④ の分類と、イベントのトランザクションの間に、別の要求が同じ D5 を確定し得る(計画レビュー 1 周目 P1-4)。各イベントのトランザクションの冒頭で D5 を照合し直し、確定済みなら保存済み結果の再掲(同じ内容)か B3b / B13(異なる内容)へ切り替える。スパイクで確かめたのは、**両方が未使用と分類した後に先着が確定してから後着を再開した場合**に、後着が再照合で B3b になることだけ(スパイク S-5)
- **再照合から INSERT までの窓**: 台帳の `(tenant_id, d5)` 一意制約を最後の防壁にする。PostgreSQL は一意制約違反でトランザクションを中断状態にするので、**台帳の INSERT を SAVEPOINT で囲む**。違反したら SAVEPOINT まで戻し、D5 を照合し直して再掲か B3b / B13 へ切り替える(トランザクション全体は失敗させない)。この窓の並行試験はステップ 7 で行う(スパイクでは未試験)
- **D3 の再照合**: 同じく、イベントのトランザクションの冒頭で、記録権世代行を `FOR UPDATE` で取ってから D3 を読み直す。⑥ の連続性はその値で判定する
- **ACK は確定の後に組み立てる**(SP 8-1)。各イベントのトランザクションがコミットしてから、その A5 を確定扱いにする

## 4. リポジトリ基底の拡張(tenant-isolation のコア・スパイク S-3)

UM01 の登録形式(`repositories/operation_registration.py`・`base.py`)を前提にする。スパイクで、適用核の書き込みのうち次の 3 つが #95 の形では表せないと実測した(スパイク S-3)。

| 足りないもの | 実測 | 拡張 |
| --- | --- | --- |
| 複合主キーによる UPDATE | T3 の `recording_generations` の D3 更新は `AttributeError: id`(`id` 列がない)。T2 の `event_slots` の版更新は、複合キー条件の式が未許可 | UPDATE の行識別条件として、宣言した複合主キーの全列の等値を受け付ける |
| 行ロック | `FOR UPDATE` を表す手段がない | 登録文に行ロックを宣言できる形を足す(O1 の直列化・D3 の再照合) |
| JSONB の結果 | 台帳の `result`(JSONB)を読むと、結果に `dict` を実体化できず `_TenantOperationError` | 結果の JSON 値を不変な表現(凍結した mapping と tuple)へ変換して返す |

あわせて、**operation registry を複数のモジュールから集める**形にする。現行の `repositories/operation_registry.py` は `ROSTER_OPERATIONS` だけを集めている(計画レビュー 1 周目 P1-2)。repository-contract の資産・生成物・迂回検査の allowlist も改訂し、凍結基準の履歴を追記する。

**#95 の UPDATE の是正を前提にする**: スパイク中に、#95 の UPDATE は実行時のパラメータのキー(`tenant_id`・`id`)が列名と重なって CompileError になることが分かった。UM01 が #95 の「ステップ 5 是正」で、WHERE の bind 名を列名と重ならない名前に替える(research.md)。U-S1 の UPDATE は是正後の bind 名に合わせる。

## 5. TB002(条件 2)との衝突の解き方

- 条件 2 は「同期セマンティクスを扱わない」を、`backend/src` の変更行の識別子で検査する(`contracts/tenant_boundary/base-allowlist.json:8102-8113`)。同期表の ORM 名(`IdempotencyLedger`・`is_tombstone`・`generation` 列)を参照するだけで当たるので、命名で避けることはできない
- 既存の `condition_2_adjudications` は「同期の世代ではない」と裁定したシンボルの例外で、同期そのものを通す用途ではない
- **案**: 条件 2 に「同期核の所有パス」を足し、所有パスでは条件 2 を適用しない。ほかの条件(1・3・4・5)は免除しない
- **免除は core-areas.json と機械で結ぶ**(計画レビュー 1 周目 P1-7): 所有パスは、検査の時点で `.claude/core-areas.json` の sync-protocol の paths に一致するパスに限って発効する。core-areas.json に登録していないパスは、宣言しても免除されない。このため、core-areas の宣言と登録を TB002 のステップより先に置く
- 負例: 所有パスの外(例: `repositories/roster.py`)に同期語彙を書くと、従来どおり TB002 で落ちる

## 6. T1 と T6・墓標・改訂・一時 ID 写像

- **T1 と T6 の台帳の確定結果は同じ書き込みで確定する**: 台帳の `result` は NOT NULL で、変更を禁止するトリガがある。そのため、D5 だけを先に書いて確定結果を後から書くことはできない(スパイク S-3)。T1 の INSERT で確定結果まで書く
- **T6 の一時 ID 写像は別の書き込み**: T6 は「確定結果と一時 ID 写像の保存」(SP:1220、DM:1041)で、写像は別表(`temporary_player_id_mappings`)に入る。写像表の保存の前後に注入点を置き、資産と runner から観測できるようにする(計画レビュー 2 周目)
- 墓標と改訂は独立した表ではない。`operation_events.is_tombstone` と `replaced_at`(有効スロットの部分一意 `replaced_at IS NULL`)で表す
- 改訂: 旧版の `replaced_at` を設定し、同じ D1 の新しい版を挿入する(新しい D5)。D3 は後退しない(R4)。単一イベントで拒否位置の改訂を受理したら、D3 はその位置まで前進する(スパイクで確認)
- 墓標: 同じ D1 の墓標版で置換し、D3 を前進させる(R3)
- **未決**: 「改訂版を名指す列が無く、通常版と区別できない」は表現できないセルとして TSK-373 へ引き渡されている(`backend/src/pitchlog/db/sync_protocol/event_kinds.py:185-190`)。U-S1 は列を足さない
- C1〜C4: その場登録(P1)では `temporary_player_id_mappings` を T6 として同じトランザクションで保存し、再送ではそれを再掲する。選手行そのものの作成は U-M1 の operation を呼ぶ(コピーしない)

## 7. NFR-019(d) の資産契約(TSK-332 の吸収・スパイク S-4)

TSK-332 の射程(Notion カード。設計の蓄積は `docs/features/sync-server-apply/design.md` の 3 章・6 章)を引き受ける。スパイクで書いた資産の形を出発点にする(スパイク S-4)。

| 項目 | 形 | スパイクでの扱い |
| --- | --- | --- |
| 構造 | 単一の `faultInjection`・`expected` をやめ、安定した `caseId` を持つ `cases` にする。観測点を case に結び付け、孤立を許さない。構造変更なので `schemaVersion` を上げる | 成り立った |
| 共通の期待フィールド | 既存 5 + `prefix`・`idempotentResult`・`temporaryIdMapping`・`recordingRight`・`tElementCommitment`。集合は無条件、省略可否だけを `applicationPath` で条件付きにする | 省略理由を持つフィールドは、DB で検証した値と同じ重みでは扱えない |
| `tElementCommitment` | 資産側は経路ごとの T ID の集合と期待状態。結果側は T ID を exact-key とする状態 record。**T の内部の保存単位**(T2 = スロット・イベント、T9 = 台帳・原本)を内側のキーにする。**`no-write`**(墓標の T4)と **`no-change`**(改訂の T3)を状態として持つ | 形を変える必要があった(資産側の `{mode}` だけでは比較できない) |
| P5 の判別共用体 | B3a = 未使用 D5 + 拒否原本 / B3b = 不変な先着原本 + 同じ D5・異なる内容の後着。値の関係を実行時に検査する | 成り立った |
| 到達しない注入点 | `expectedReachability: "unreached"` と hook の呼び出し 0 回 | 成り立った |
| 注入点の組 | 経路と T 要素の対応は `scripts/design_relations/sync-protocol.json` の `R-TXN-ROUTE` から導出し、二重定義しない | (スパイクでは手で列挙) |
| 契約検査と結果検査 | 別の validator にする(同じものを使うと既存 runner が必ず red になる) | — |
| 母集合 | 26 ID・観点 22 種・26 ペアを exact-set で照合する(`docs/features/sync-server-apply/design.md` 6-2) | — |
| 既存 4 資産 | 最終構造へ一度だけ移行する(途中の版を作らない)。frontend の消費側(`frontend/src/testing/failureScenarioAdapter.ts`・`frontend/src/lib/sync/failureScenarioContract.ts`)も追随させる | — |
| 新規資産 12 件 | TSK-332 の 10 件(墓標・改訂、P1〜P4、`p5-b3a`、`p5-b3b`、`d1-mixed-batch`、`b3b-after-gap`)と、TSK-330 から引き継いだ 2 件(`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence`)。復元系 10 件は U-R1 への繰り延べとして母集合に記録する(R-11) | 3 件をスパイクで試作 |

- **正本 10-3 を改訂する(R-10)**: 比較単位が `scenarioId × caseId × 注入対象 × 観測点 × expected の全フィールド` になり、現行の「`scenarioId × 観測点 × expected の全フィールド`」(SP:1716)と食い違う(計画レビュー 2 周目)。TSK-332 のカードにあった制約「正本を改訂しない」は、人間の裁定 R-10 で外した
- **P3 に加わる期待フィールド**と、**トランザクション外の 3 注入点**の被覆・繰り延べを、契約検査の exact-set で照合する(SP:1713、`docs/features/sync-server-apply/design.md:226`)

## 8. 未解決(計画レビューで確認する論点)

| ID | 論点 | 本書の案 |
| --- | --- | --- |
| Q-2 | NFR-018: サーバー側の D5 分類・処理段階の Python 実装が、frontend の TS 実装に対するコピー実装に当たるか | 当たらない(計画レビュー 1 周目の判定。要件の対象列挙に同期がなく、TS 側は正本の写しでトランザクション処理はサーバーの責務と明記) |
| Q-3 | O1 の直列化の方式 | `(tenant_id, game_id)` の試合行を `SELECT ... FOR UPDATE` で取る。advisory lock は RLS の外にあるので避ける |
| Q-4 | 内容同一性の判定((B)17) | 入力原本の正規化 JSON の全フィールドで比較し、導出した拒否理由は含めない(スパイクの判断)。`source_fingerprint` の算出規則にする |
| Q-5 | 改訂版と通常版の区別(TSK-373) | U-S1 では列を足さない |
| Q-6 | `confirmed_watermark` と `applied_prefix` のどちらが D3 か | `confirmed_watermark` を D3 とする(スパイクもこれで動いた)。`applied_prefix` の意味を計画レビューで確定する |
| Q-7 | RG1 の所有者 | `RecordingRightsPort` に含める。U-S1 が保証するのは同期経路の停止まで。全変更経路の停止は復元の単位 |
| Q-8 | (d) 資産の比較単位が正本 10-3 と食い違うか | **裁定済み(R-10)**: 食い違う。正本を v0.6 に改訂する(v0.5 は #81 の先約 — 2026-10-09 裁定) |
| Q-9 | TSK-330 の繰り延べ 12 ID の送り先 | **裁定済み(R-11)**: 復元系 10 件は U-R1。`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence` は U-S1 |
| Q-10 | I5 の配信先 | `InvalidationSinkPort` で受け、配信と再試行は U-S1 が持つ。配信先の本物は未定 |
