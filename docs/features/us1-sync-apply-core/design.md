---
feature: us1-sync-apply-core
type: design
date: 2026-10-08
---

# 詳細設計: U-S1 同期適用核(TSK-391)

本書は [plan.md](plan.md) 4 節から参照する詳細設計である。意味規則の正本は `docs/design/sync-protocol.md`(以下 SP。v0.4)、物理写像の正本は `docs/design/data-model.md`(以下 DM)5-4 節。**本書は正本の規則を再定義しない**。正本の節を、どのモジュールのどの関数が実装するかを対応づける。調査の典拠は [research.md](research.md) にある。

## 1. 置き場とモジュール構成

新しいコードは `backend/src/pitchlog/sync/` に置く。`backend/src/pitchlog/db/` には 1 ファイルも足さない(`docs/features/product-impl-unit-split/plan.md:467`)。同期表への SQL は `backend/src/pitchlog/repositories/sync_apply.py` に、UM01(#95)の operation 登録形式で置く。

| モジュール | 責務 | 正本 |
| --- | --- | --- |
| `sync/model.py` | 要求・イベント・A5・境界結果(B1〜B14)・ACK の結果オブジェクトの型 | SP 6-2・6-3・7-1 |
| `sync/ports.py` | 注入境界 3 種の Protocol(2 節) | SP 9-2(判定の所有者) |
| `sync/idempotency.py` | ④ D5 の内部分類(DI1〜DI5・I1〜I4)と内容同一性の判定 | SP 4-5・6-2 |
| `sync/prefix_path.py` | P1・P2 の適用。⑥ D3+1 からの走査・墓標/改訂・A5 の合成・B2・B3 | SP 6-1・6-2・6-3・8-1 |
| `sync/ordering.py` | T5(O1 の直列化・O2 の局所再採番・O4 の同値停止) | SP 5-5・8-1、DM 5-4 の T5 |
| `sync/rejection.py` | P5 / T9(B3a)と P4 / T8(B4・退避) | SP 8-1・9-2、DM 5-4 の M10 |
| `sync/change_path.py` | P3(③-b 復旧世代、B8〜B14、T7・I5、I6 の `accepted_at`) | SP 6-2 の P3 表・6-3 の P3 独立境界結果 |
| `sync/gate.py` | ③-a RG1 と ⑧ のコミット直前再検証 | SP 6-2・6-3 の RG1 |
| `sync/apply.py` | 公開入口。1 要求 = 単一の (試合, D4) を受け、段階③〜⑧の順序で上記を呼ぶ | SP 6-2「段階の順序は入れ替えられない」 |
| `sync/crash_points.py` | クラッシュ注入点の名前付き定義(テストからだけ有効化) | SP 10-2・11-4 U-8、DM 5-4 の M20 |

**HTTP 入口は作らない**(裁定 R-3)。`sync/apply.py` の公開関数は、後で入口から直接呼べる形(認証・認可済みの `TenantContext` と要求オブジェクトを受け、結果オブジェクトを返す)にする。wire 形式への写像は TSK-331 の後の入口 PR が持つ。

## 2. 注入境界(裁定 R-2)

判定の所有者が U-S1 ではないものを Protocol で受ける。本物の実装は所有単位が差し込む。U-S1 のテストは合成実装を使う。

| ポート | 何を返すか | 所有単位 | 呼ぶ段階 |
| --- | --- | --- | --- |
| `RecordingRightsPort` | V12 が現 D4 + 現復旧世代 + 保持端末へ結合された証明か(VF1〜VF6)、要求作成時の復旧世代が現復旧世代と一致するか、復元調整中か(RG1) | U-R1(TSK-392)。RG1 の所有者は SP 9-2 に記載がない(research B-3) | ③-a・③-b・⑤・⑧ |
| `ProjectionPort` | T4 の投影更新(DM 5-4「サーバー側の T4 は投影の更新」)と、サーバー再計算の起点 | U-X1(凍結中) | T4 |
| `ContentValidationPort` | ⑦ / P3 ⑥ の内容検証の可否と理由 | U-X1・U-G2 | ⑦・P3 ⑥ |

- ポートは同じトランザクション(`_tenant_transaction`)の中で呼ばれる。ポートが独自にトランザクションを開くことは許さない(DM 5-4 の M20-1「同一トランザクションで書ける配置」)
- 合成実装は `backend/tests/` 側にだけ置く。製品コードには既定実装を置かない(未接続のまま本番経路が通ることを防ぐ。fail-closed)

## 3. トランザクションの単位

- SP 8-1「単位は 1 要求ではなく連続して適用できた範囲」「T 要素は 1 イベントごとに束ねてよい」。U-S1 は **1 イベント = 1 トランザクション**を採る((B)18 のまとめ方の選択。性能の都合で後から連続範囲へまとめても意味規則は変わらない)
- 理由: クラッシュ注入点を「イベント k の T 要素 i と i+1 の間」として一意に定義でき、(d) の観測点が単純になる(DM 5-4 の M20-4)
- 1 要求の処理の流れ: ③認可(`TenantContext` 束縛済み)→ ③-a RG1 → ④ D5 の全件分類(読み取りだけ)→ D1 昇順にイベントごとのトランザクションで ⑤〜⑧ を適用 → 最初の B2・B3・B4 で停止 → 以降を未処理にして ACK を合成する
- **ACK は確定の後に組み立てる**(SP 8-1)。各イベントのトランザクションがコミットしてから、その A5 を確定扱いにする

## 4. リポジトリ基底の拡張(tenant-isolation のコア)

UM01 の登録形式(`repositories/operation_registration.py`・`base.py`)を前提にする。2026-10-08 時点の実測で、適用核の要件を満たさない点が 2 つある。

1. **UPDATE は `id = :id` 条件を必須にしている**(`base.py` の `_validate_prepared_statement`)。ところが T3 の対象 `recording_generations`、T7 の対象 `event_slots`、I5 の対象 `invalidation_intents` には `id` 列がない(`contracts/db/schema-manifest.json` の実測)。→ **複合主キーによる行識別**を UPDATE 条件として登録できる形へ広げる
2. **行ロック(`FOR UPDATE`)を表す手段がない**。O1 は「D2 の採番・再採番を `(tenant_id, 試合)` 単位で直列化する」(DM 5-4 の T5)。→ **登録文に行ロックを宣言できる形**を足す。方式(試合行の `SELECT ... FOR UPDATE` か `pg_advisory_xact_lock` か)は 7 節 Q-3

この拡張は repository-contract の資産、生成モジュール、迂回検査の allowlist の改訂を伴い、凍結基準の履歴追記の対象になる(research C-2)。

## 5. TB002(条件 2)との衝突の解き方

- 条件 2 は「同期セマンティクスを扱わない」を `backend/src` の変更行の識別子で検査する(`contracts/tenant_boundary/base-allowlist.json:8102-8113`)。同期表の ORM 名(`IdempotencyLedger`・`is_tombstone`・`generation` 列)を参照するだけで当たるので、**命名で避けることはできない**(U-A1 は命名回避を選んだが、それは同期以外の単位だったから)
- 既存の `condition_2_adjudications` は「同期の世代ではない」と裁定したシンボルの例外で(例: `TracedGeneration`)、**同期そのものを通す用途ではない**
- **案**: 条件 2 に「同期核の所有パス」の宣言を足し、`backend/src/pitchlog/sync/**` と `backend/src/pitchlog/repositories/sync_apply.py` では条件 2 を適用しない。ほかの条件(1・3・4・5)は免除しない。所有パスの宣言は sync-protocol のコア paths と一致することを検査で拘束する(片方だけ広げられない)
- 負例: 所有パスの外(例: `repositories/roster.py`)に同期語彙を書くと、従来どおり TB002 で落ちること

## 6. 墓標・改訂・一時 ID 写像の表現

- 墓標と改訂は独立した表ではない。`operation_events.is_tombstone` と `replaced_at`(有効スロットの部分一意 `replaced_at IS NULL`)で表す(research C-1)
- 改訂: 旧版の `replaced_at` を設定し、同じ D1 の新しい版を挿入する(新しい D5)。D3 は戻さない(R4)
- 墓標: 同じ D1 の墓標版で置換し、D3 を前進させる(R3)
- **未決**: 「改訂版を名指す列が無く、通常版と区別できない」は表現できないセルとして TSK-373 へ引き渡されている(`backend/src/pitchlog/db/sync_protocol/event_kinds.py:185-190`)。U-S1 は列を足さない(db/ を触らない)。区別が必要な検査は TSK-373 の解決を待つ(7 節 Q-5)
- C1〜C4: その場登録(P1)では `temporary_player_id_mappings` を T6 として同じトランザクションで保存し、再送ではそれを再掲する。選手行そのものの作成は U-M1 の operation を呼ぶ(コピーしない)

## 7. 未解決(計画レビューで確認する論点)

| ID | 論点 | 本書の案 |
| --- | --- | --- |
| Q-1 | TSK-330 の「全シナリオの runner」は、TSK-332 の (d) 資産契約の再設計に依存する。TSK-332 は U-S1 に吸収されていない | runner は TSK-332 の資産が揃ってから同じ射程で作る。U-S1 は pytest で書いたクラッシュ注入テストまで。runner を U-S1 に含めるなら TSK-332 の吸収も要る — **人間の確認が必要** |
| Q-2 | NFR-018: D5 分類と処理段階は frontend の TS に既にある(`frontend/src/lib/sync/idempotencyCollision.ts`・`processingStages.ts`)。サーバーで Python で書くとコピー実装に当たるか | 当たらないとする案。NFR-018 の対象列挙に同期は無い(REQ:892)。サーバーは適用の権限者で、frontend 側は正本の写しを検査する oracle にとどまる。ただし sync-server-apply は TS での再実装を P0 と判断した経緯がある(`docs/features/sync-server-apply/design.md:268`)ので、**計画レビューの論点に明示する** |
| Q-3 | O1 の直列化の方式 | `(tenant_id, game_id)` の試合行を `SELECT ... FOR UPDATE` で取る案。advisory lock は RLS の外にあるので避ける |
| Q-4 | 内容同一性の判定((B)17) | 正規化した JSON の全フィールド比較。`idempotency_ledger.source_fingerprint` があるので、その算出規則を決めて比較に使う |
| Q-5 | 改訂版と通常版の区別(TSK-373) | U-S1 では列を足さない。区別を要する検査は保留と明記する |
| Q-6 | `confirmed_watermark` と `applied_prefix` のどちらが D3 か(DM:1173, 1176・SP 9-3) | SP 9-3「確定水位 = D3」と後退禁止トリガから、`confirmed_watermark` を D3 とする案。`applied_prefix` の意味を計画レビューで確定する |
| Q-7 | RG1 の所有者が SP 9-2 に書かれていない | `RecordingRightsPort` に含める(復元・記録権側の判定として扱う) |
