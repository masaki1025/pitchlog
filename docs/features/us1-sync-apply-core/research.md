---
feature: us1-sync-apply-core
type: research
date: 2026-10-08
---

# 調査メモ: U-S1 同期適用核(TSK-391)

略号:

- REQ = `docs/requirements/requirements-pitchlog-2026-07-22.md`(v2.9)
- SP = `docs/design/sync-protocol.md`(v0.4 approved 2026-09-24)
- DM = `docs/design/data-model.md`
- SPLIT = `docs/features/product-impl-unit-split/plan.md`(TSK-363。2026-09-13 承認)
- SPLIT-D = 同 `design.md`

起点は develop `1fdf1eec`。調査は spec-checker・decision-tracer・Explore の 3 本で行った。決定的な主張は原典で確認し、その箇所に「(原典確認)」と記した。

## 問い

1. FR-012 と同期正本は、サーバー側の「適用核」に何を課しているか。どこまでがサーバーの責務か
2. 過去の同期まわりの feature が何を作り、何を後続へ送ったか。U-S1 はそのどれを引き受けるのか
3. 適用核を書くために、コード・DB・機構の何が揃っていて、何が詰まっているか

## 結論(要約)

- **担当の重複**: サーバー側の適用実装は、正本の上では **TSK-330** が受け取り先になっている。関連する wire 形式は TSK-331、故障系 (d) のシナリオ資産は TSK-332 の担当で、3 本とも Notion で未着手。U-S1 との線引きを書いた文書はない(B-2)。**計画の前に人間の裁定が要る**
- **適用核の中身は、表のうえでは揃っている**: 9 表、制約、不変トリガ、D3 の後退禁止トリガ、RLS はある。一方で適用する製品コードは 0 行で、D2 の採番を直列化する仕組み(O1・O2)もない(C-1)
- **機構の側で 3 つ詰まる**(C-2):
  - ① テナント越境検査の TB002 が、`backend/src` の変更行で `idempotenc*` / `tombstone` / `generation` などの語を禁じている
  - ② リポジトリ基底の `_TenantTransaction.run` は Select しか実行できない。書き込みの登録形式は tenant-isolation のコア
  - ③ core-areas.json の追加窓口には、236 と UM01 の 2 本がすでに乗っている
- **依存が逆向きになっている**(B-3):
  - 段階⑤の V12・D4 判定は記録権(U-R1)が所有するが、U-R1 は U-S1 に依存している
  - T4(状態遷移)とサーバー再計算は状況計算(U-X1)に依存し、U-X1 は凍結中
  - 適用核を閉じきるには、判定と状態遷移を注入境界として受け取る形が要る(推論)
- **カード名と DoD のずれ**(B-4):
  - 「連番と採番の不可分性」の強制点はクライアント側で、α ですでに実装済み
  - DoD の「contracts/ のゴールデンベクタとの一致」には対象が存在しない。同期の故障系テストの置き場は、正本が `tests/fixtures/sync-protocol-failures/` と定めている

## 詳細と典拠

### A. 要件と正本がサーバー側の適用核に課すこと

#### A-1. FR-012(REQ:295-315)のうちサーバーの責務

| 受入基準 | 典拠 |
| --- | --- |
| 重複到達しても二重適用しない。連番に欠落があれば、それ以降を適用しない(prefix コミット) | REQ:302 |
| べき等キーの記録・イベント保存・prefix 更新・状態遷移を、単一の DB トランザクションで確定する | REQ:303 |
| サーバーが入力順に再計算・検証した結果を確定記録とし、差異は補正して通知する | REQ:309 |
| 内容起因の拒否で後続を止める。再開は「同一連番の改訂版」か「墓標」のどちらか。prefix は墓標を越えて前進する。記録権による拒否は別カテゴリとする | REQ:310 |
| 現世代の記録権を持たない端末のイベントは適用を拒否する | REQ:328 |

キュー、350 件の警告、単一タブの書き手、採番の不可分性(REQ:299, 304, 311-314)はクライアントの責務で、強制点もクライアントにある(SP:1401, 1420)。

#### A-2. 正本の規定(サーバー側)

- **処理段階の順序**は入れ替えられない(SP:685-697)。③認可 → ③-a RG1 → ④D5 → ⑤記録権 V12 → ⑥D1 → ⑦内容 → ⑧コミット直前の再検証
- **D5(べき等キー)**
  - 照合キーは `(テナント, D5)`。他テナントの同じ D5 は重複として扱わない(SP:245, 386-397)
  - 衝突したときの扱いは SP:399-406。DI1〜DI5 は SP:419-427、P3 用の I1〜I4 は SP:431-436
- **D1・D3**
  - D1 のスコープは (試合, D4)(SP:246, 254)。1 要求は単一の (試合, D4) に限る(SP:677)
  - D3 の規則 R0〜R5 は SP:655-660。欠落の後ろは保存しない。後退しない
  - キューに載るイベントについて、サーバーが順序値を採番することは禁止されている(SP:299)
- **墓標と改訂**
  - 送信時に V12 を照合する。成立すれば旧版を置換するか、その D1 を消費する(SP:852-855)
  - 墓標で前進する(R3)。改訂で水位を戻さない(R4)(SP:658-659, 664)
- **原子境界**(SP:1213-1264)
  - P1 = T1・T2・T3・T4・T6、P2 = P1 + T5、P3 = T1・T2・T4・T6・T7、P4 = T8、P5 = T9
  - 単位は「連続して適用できた範囲」で、イベント単位に束ねてよい(SP:1248-1249)。応答は確定の後に返す(SP:1250)
- **経路の割り当て**(SP:1285-1298): 毎球入力・交代・TB 開始・終了宣言・状態補正は P2。undo・その場登録・墓標は P1。修正系は P3
- **再送**: 保存済みの結果を再掲する。引き継ぎ後も、現在の V12 で B4 に上書きしない(SP:1063-1070)
- **ACK**: A1〜A5(SP:922-926)。必須要素は前進後の D3(SP:987)
- **クラッシュ注入点**をテストから指定できる実装にする(SP:1686, 2100 の U-8)
- **実装計画へ送られている物理方式**(SP:1571-1584): (B)17 D5 の長さと内容同一性の判定、(B)18 バッチ単位とトランザクションのまとめ方、(B)21 再計算の粒度

#### A-3. 効く NFR と横断要求

- NFR-019(d) 同期プロトコルの故障系テスト: 墓標・改訂の適用、サーバー適用の原子性(クラッシュ注入)(REQ:933)
- NFR-010 テナント分離(REQ:848)。同期経路では③認可を④D5 の照合より前に置く(SP:697)。存在の非開示は SP:883-896
- 物理削除しない(REQ:161)。墓標は行の削除ではなくイベントの追加(SP:902)
- Won't: 同時入力のマージをしない(REQ:98)。利用者 ID を持たない(SP:297)
- サーバーはステートレス(REQ:1016)

### B. 決定の経緯と担当

#### B-1. 過去の同期 feature

| feature(タスク・承認日) | 作ったもの | 後続へ送ったもの |
| --- | --- | --- |
| sync-protocol-design(TSK-259・08-28) | 候補案。論点を (A) 意味 16 件と (B) 物理 10 件に分けた | 正本化 |
| sync-protocol-canonical(TSK-265・08-29) | SP v0.1 | U-1 → TSK-267 |
| sync-event-contract(TSK-280・09-05) | frontend のイベント契約 | DI1・DI5・I1・B3a → 後続 γ |
| sync-queue-lifecycle(09-05) | frontend のキュー、K5、(d) 資産 4 本 | 墓標・改訂の**適用**、サーバー適用の原子性 → γ |
| sync-ack-contract(09-05) | ACK の消費側(frontend) | A1・A2 の原子的確定ほか → γ |
| sync-server-apply(TSK-321・γ・09-07) | **frontend の検証資産だけ**(processingStages.ts・RG1・D5 分類の修正)。DoD は「backend を 1 行も変更していない」(`docs/features/sync-server-apply/plan.md:175`) | 下の B-2 |
| sync-queue-transition-defects(TSK-329・09-24) | SP v0.4 | 通知 → TSK-441、サーバー実装 → TSK-330 |

#### B-2. サーバー側の実装を受け取っているタスク(原典確認: `docs/features/sync-server-apply/plan.md:60-66`)

| 内容 | 受け取り先 | Notion(2026-10-08) |
| --- | --- | --- |
| 全シナリオの runner、`backend/` 実装、8 章の適用実装 | TSK-330(後続 γ') | 未着手 |
| DI5・B3a(P5 + T9)・T9・T7・I5・I6 | TSK-330 | 同上 |
| wire 形式・プロパティ名・JSON / API スキーマ | TSK-331 | 未着手 |
| (d) 故障系の契約の再設計とシナリオ資産 10 件 | TSK-332 | 未着手 |

- TSK-330 の開始条件は TSK-342 の完了に差し替えられている(`docs/worklog/2026-09-08-data-model-handoff-revision.md:223-236`)。TSK-342 は完了済み
- frontend の `canonOracle.spec.ts:685-688` は、射程外の理由の文字列「TSK-330」を機械で検査している
- SPLIT は TSK-330 を「未着手の製品実装系」として挙げているだけで(`docs/features/product-impl-unit-split/research.md:242`)、**U-S1 との重なりを整理した記述はない**

#### B-3. 依存の向き

- V12・D4 の判定、フェンス、復旧世代の照合は記録権だけが持つ。同期は結果を B4・B9 に写すだけ(SP:1415, 1426)
  - ところが単位の依存は U-T1 → U-S1 → U-R1(TSK-392。未着手)になっている(SPLIT:205-206)。推奨順に拘束力はない(SPLIT:379)
- RG1(復元調整のゲート)は段階③-a に入るが、9-2 に所有者が書かれていない(SP:690, 1422)
- T4(状態遷移)とサーバー再計算(REQ:309)は状況計算に依存する。状況計算を主所有する U-X1 は凍結中(SPLIT:234, 396)
- undo の適用(P1・FR-006)は U-X1 の主所有。P3(修正系)は、受理を持つ U-G2 との帰属が不明(SPLIT:215)
- FR-012 は単位分割の分担表に行がない(SPLIT-D:86-92)

#### B-4. カード名・DoD と正本のずれ

- **連番と採番の不可分性**: DM C10 は「採番の原子性は端末側の責務。DB で連続性を強制しない。サーバーは欠落を検知して B2 を返す側」としている(原典確認: DM:803-812)。9-2 でも強制点はクライアント(SP:1401)。端末側は sync-queue-lifecycle で実装済み
- **contracts/ との一致**:
  - contracts/ に同期のゴールデンベクタはない。contracts/ に置けるのは NFR-019(a) の対象計算ベクタと参照データだけ(`contracts/README.md:3, 9-12`)
  - (d) テストの置き場は `tests/fixtures/sync-protocol-failures/`(SP:1712)。いまある 4 本はすべてクライアント側のシナリオ
- **重複帰属**: 6.3 の文言は「記録権世代・連番を扱うコードは記録権と重複帰属し得る」(`docs/development/dev-harness-design-2026-08-07.md:394, 396`)。重複帰属は core-guard の判定を変えず、宣言としてだけ働く(`docs/development/harness-evaluation.md:2513-2535`)
- **conftest の差分 0 行**: 由来は SPLIT:465, 482。`backend/*conftest.py` は tenant-isolation に登録されている

### C. コードと機構の実体(develop)

#### C-1. あるもの・ないもの

| 項目 | 状態 | 典拠 |
| --- | --- | --- |
| 表 | `operation_events`・`event_slots`・`idempotency_ledger`・`rejected_event_originals`・`invalidation_intents`・`temporary_player_id_mappings`・`recording_generations`・`evacuated_event_originals` の ORM・制約・不変トリガ | `backend/src/pitchlog/db/sync_protocol/models.py:61-532`、`db/recording_rights/models.py:40-241`、migrations 0005・0007・0008・0025 |
| 墓標と改訂 | 独立した表ではない。`operation_events.is_tombstone` と `replaced_at`(部分一意の `replaced_at IS NULL`)で表す | models.py:148-151, 222-231 |
| 原子書き込み | 「台帳行と原本行の原子書き込みの責務はアプリ層にある」と明記されている | models.py:13-14 |
| D3 | `confirmed_watermark` に後退禁止トリガがある。別に `applied_prefix` 列もあり、意味は不明(DM:1173, 1176 は両者を別行に置く) | migration 0008:129-131 |
| D2 の直列化(O1・O2) | **ない**(採番表・SEQUENCE・advisory lock・FOR UPDATE は 0 件) | Explore の grep |
| 適用コード・同期 API | **ない**。ルータは meta(`/health`・`/version`)だけ | `backend/src/pitchlog/api/app.py:8` |
| RLS | 9 表すべて `tenant_owned`。`pitchlog_app` は SELECT・INSERT・UPDATE | `contracts/authz/product/` |
| 書き込み用 capability | ID はある(`CAP:operation_events:insert/update` など) | `contracts/authz/product/capability-catalog.json` |
| frontend の受け口 | ackEnvelope・p3Result・rejectionReason・boundaryResults。通信層はない | `frontend/src/lib/sync/ackEnvelope.ts:2, 10-20` |

#### C-2. 機構の詰まり

1. **TB002**(原典確認: `contracts/tenant_boundary/base-allowlist.json:8102-8113`)
   - 条件 2 は、`backend/src` の変更行で `idempotenc*`・`seq_no`・`sequence_no`・`tombstone`・`revision_no`・`generation` を禁じている。パスによる除外はない
   - 由来は「単位を混ぜない」規律(SPLIT:264-270)。U-A1 でも同じ衝突が記録されている(`docs/worklog/2026-09-24-ua1-team-auth.md:33`)
   - 同期の核そのものである U-S1 は、この規則と正面から衝突する
2. **リポジトリ基底は Select しか実行できない**(原典確認: `backend/src/pitchlog/repositories/transaction.py:109-113`)
   - 束縛される引数は `tenant_id` だけ(base.py:194-198)。operation registry は空
   - 書き込みの登録形式を足すと、リポジトリ契約の資産・生成モジュール・迂回検査の allowlist を改訂することになる。これは tenant-isolation のコア
3. **core-areas.json の窓口**
   - `AREA_PATH_ADDITIONS` は回転式で、宣言コミットと JSON 変更コミットを分ける(`scripts/core_guard.py:24-57`。前例は `9b10137e` → `1c98cc06`)
   - 469 master の実測では、いま 236 と UM01 の 2 本が乗っている(worklog の 2026-10-08)
   - 新しいパスの当たり方:
     - `backend/src/pitchlog/sync/`・`api/routers/sync.py`・`backend/tests/test_sync_apply.py` はどの領域にも当たらない
     - `backend/src/pitchlog/db/sync_protocol/<sub>/` は sync-protocol に当たる
     - `backend/tests/db/` は全 5 領域に当たる
   - UM01 の `backend/tests/test_*_boundary.py` はテストだけを覆う
4. **入口を開くと 12-4 ゲートが掛かる**
   - 同期のエンドポイントを開けば、同じ PR で `contracts/authz/http-route-matrix.json` に route_id を付ける必要がある。これは tenant-isolation のコア(SPLIT:292-305, 431, 513)
   - route-registry で FR-012 は `out_of_registry` 扱い(`contracts/authz/route-registry.json:811-834`)。wire は TSK-331 の担当

#### C-3. DB テストの書き方(conftest を変えない前例)

- `backend/tests/db/test_tenant_transaction_scope.py:177-291, 712-716` が前例。自動 fixture をモジュール内で上書きし、使い捨て DB にアプリロールを作り、registry を monkeypatch している
- `backend/tests/db/test_product_authz_tenant_owned.py:40-74` は 2 テナント分の行を投入して越境を検査している
- fixture 群: `backend/tests/db_fixtures.py`(`disposable_postgres_cluster`・`provisioned_product_catalog`)

## 未解決・申し送り

人間の裁定が要るもの(/plan の前提):

- **R-1 TSK-330・331・332 との線引き**。次の 3 案がある
  - ① U-S1 が TSK-330 を吸収する(TSK-330 は取り下げるか U-S1 へ統合する)
  - ② U-S1 は適用核のサービス層だけを持ち、runner と (d) の資産は TSK-330・332 に残す
  - ③ U-S1 を TSK-330 と読み替える(カードを統合する)
  - どれでも `canonOracle.spec.ts:685-688` の「TSK-330」文字列の扱いが要る
- **R-2 依存の逆向き**: 記録権の判定(V12・D4・RG1)と状態遷移(T4・再計算)を、U-S1 では注入境界(ポート)で受け取り、実装は U-R1・U-X1 に任せる案(推論)。この場合、FR-012 は U-S1 では「部分充足」になる
- **R-3 入口を開くか**: U-S1 ではサービス層と DB テストまでにして、HTTP 入口は開かない(wire は TSK-331)。こうすれば 12-4 ゲートと route_id(tenant-isolation のコア)を避けられる(推論)
- **R-4 TB002 との衝突**: 同期語彙の禁止を U-S1 の置き場所だけ外すのか、シンボル単位の裁定で通すのか。どちらも tenant-isolation のコアに触れる
- **R-5 書き込みの登録形式**: リポジトリ基底を Select 以外に広げる変更を U-S1 で行うのか、別単位として切り出すのか(U-T1 側の拡張)
  - 追記(2026-10-08 実測): UM01(U-M1・PR #95 draft)が、`transaction.py` の Select 限定を外し、`_prepare_operation` と `_materialize_execution_result` へ一般化している(`feature/um1-player-roster-opponent` の `origin/develop...HEAD` 差分。repository_contract.py と repository-contract.json も改訂)。**U-S1 は #95 のマージ後にこれを再利用するのが最短**(推論)。その場合、U-S1 の実装は #95 のマージを待つ
- **R-6 core-areas.json**: 窓口が空くのを待つのか(469 master が順番を調整)、既存の glob に収まる置き場所(`db/sync_protocol/<sub>/` など)を選ぶのか。重複帰属の明示に JSON の変更が要るかも決める
- **R-7 NFR-018**: D5 分類と処理段階は frontend に TS で既にある。サーバー側で Python で書くことが、コピー実装に当たるか。NFR-018 の対象列挙には同期が含まれない(REQ:892)が、sync-server-apply では TS での再実装を P0 と判断した(`docs/features/sync-server-apply/design.md:268`)
- **R-8 D2 の直列化方式**(O1・O2): 方式((B)18)を U-S1 で決めるか。新しい表を作るなら、45 表の固定(`backend/tests/db_fixtures.py:526-532`)と RLS 分類も改訂する

申し送り:

- カードの DoD「contracts/ のゴールデンベクタとの一致」は対象が存在しない。`tests/fixtures/sync-protocol-failures/`(SP:1712)への読み替えを、カードの修正として人間へ上げる
- `applied_prefix` の意味(TSK-372 へ送付済み)を計画の前に確認する
- 射程外のまま残るもの: U-1・U-2・RR-1(TSK-267。未着手)、通知(TSK-441)

## 裁定(2026-10-08・人間)

- R-1: **U-S1 が TSK-330 を全部吸収する**(runner・P3 の T7・I5・I6 を含む)。TSK-330 は取り下げか統合として扱う。`canonOracle.spec.ts:685-688` の「TSK-330」文字列も追随させる
- R-2: 記録権の判定(V12・D4・RG1)と状態遷移(T4・再計算)は、**注入境界で受ける**。本物は U-R1・U-X1 が差し込む。FR-012 は U-S1 では部分充足とする
- R-5: **UM01 の #95 の上に積む**(起点を feature/um1-player-roster-opponent にする)
- R-3: **HTTP 入口は U-S1 では開かない**。サービス層は入口から直接呼べる形で作る。入口は TSK-331 で形式が決まった後に、小さな PR で開く。人間の判断基準は「製品コードが早く develop に入る方」

- R-9: **U-S1 が TSK-332(NFR-019(d) の資産契約の再設計とシナリオ資産)も吸収する**(2026-10-08・人間。スパイクで資産の実際の形が見えたため)。繰り延べ 12 ID の送り先は R-11 で裁定した

- R-10: **正本 sync-protocol.md 10-3 の比較単位を改訂する(v0.5)**〔2026-10-09 追記: v0.5 は #81(TSK-236)が 2026-09-28 に approved で使用済み。山田正輝の裁定で **v0.6** へ改める〕。U-S1 の PR に確定ゲートを含める(2026-10-08・人間。計画レビュー 2 周目で、資産の比較単位が正本と食い違うと判定されたため)
- R-11: **TSK-330 の繰り延べ 12 ID のうち、復元ライフサイクルの 10 件は U-R1(TSK-392)へ送る**。`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence` は U-S1 で作る(2026-10-08・人間)
- R-12: **ポートの別スレッドへの書き込みの預け入れは、アプリの層で最大限に防ぎ、残りは記録する**。DB のトリガ案は採らず、投影の表の持ち主 U-X1 へ申し送る。I6 の端末側の検証は U-S1 で閉じる(Vitest 側の runner)(2026-10-08・人間。計画レビュー 3 周目)
## スパイクの結果(2026-10-08・feature/us1-sync-spike)

人間の裁定でスパイクを打った(書き手は Codex。計画書は `feature/us1-sync-spike` の `docs/features/us1-sync-spike/plan.md`。敵対レビュー 3 周で承認)。起点は UM01 #95 の `3e19b295`。ステップ 3 本のコミットは `34aab643`・`cafc9b48`・`fa9975e9`。**DB テスト 20 件 green**(Codex の sandbox は Docker を使えないため、Claude が使い捨てクラスタで実行した)。ブランチは push していない。

| 問い | 答え |
| --- | --- |
| S-1 注入点 | **成り立つ**。1 イベント = 1 トランザクションで、名前付き注入点 7 個(開始前・T1/T2/T3/T4/T6 の後・コミット後かつ結果組み立て前)を置ける。コミット前に止めれば全部未確定、コミット後なら全部確定を、別接続から観測できた。T9 の内部(台帳行と拒否原本行の間)でも同じ |
| S-2 ポートとトランザクション | **同じハンドルを渡せばポートの書き込みもロールバックされる。ただし、ポートが独自に `tenant_transaction_scope` を開いて書くことは拒否できない**(外側がロールバックしても投影行が残った)。署名でハンドルを必須にしても防げない。U-S1 では別の拘束(例: 適用中は新しいスコープを開けない仕組み、またはポートに書き込み token の生成だけを許し、実行は適用核が行う形)が要る |
| S-3 #95 の登録形式 | 下表 |
| S-4 TSK-332 の契約の争点 | 下の「S-4」 |
| S-5 D5 の同時到達 | **成り立つ**。両方が「未使用」と分類した後に止め、先着を確定させてから後着を再開すると、後着はトランザクション内の再照合で B3b(内容が異なる場合)になった。READ COMMITTED で先着の確定が見える。再照合から INSERT までの窓は、台帳の一意制約が最後の防壁(この窓そのものは試験していない) |

### S-3: 書き込みの全文の登録可否

| 文 | 構築時検査 | 実行 |
| --- | --- | --- |
| T1 台帳 INSERT / T2 スロット INSERT / T2 イベント INSERT / T4 投影 INSERT | 通過 | `handle.run` で通過 |
| P5 の 5 文(試合の所属照合・D5 照合・T9 台帳 INSERT・拒否原本 INSERT) | 通過 | `handle.run` で通過(既存行の照合を除く) |
| T3 `recording_generations` の D3 UPDATE | **拒否**(`AttributeError: id` — `id` 列がない) | 直接 session |
| T2 `event_slots` の版 UPDATE | **拒否**(複合キー条件の式が未許可) | 直接 session |
| 台帳の既存行の照合(`result` の JSONB を読む) | 通過 | **拒否**(`_TenantOperationError`: 結果に `dict` を実体化できない) |
| UPDATE 全般(`operation_events.replaced_at`・`players.name`) | 通過 | **CompileError**(下記) |

- **#95 自体の疑い**: UM01 の `PlayerUpdateToken` を `_prepare_operation` に通すと、パラメータのキーは `id`・`tenant_id`・`value_name` になる。これを PostgreSQL 方言でコンパイルすると `CompileError: bindparam() name 'tenant_id' is reserved for automatic usage in the VALUES or SET clause` になる(Claude がコンパイル段階で再現。実 DB での実行は未確認)。#95 の UPDATE の試験は偽 session で行われていて、実際のコンパイルを通らない。**UM01 へ報告済み**(2026-10-08)。UM01 が確認し、SQLite でも再現した(PlayerUpdateToken・TeamRecordUpdateToken の両方。INSERT・SELECT は落ちない)。#95 に「ステップ 5 是正」として直す: UPDATE の WHERE の bind 名を列名と重ならない名前へ替え、base.py の UPDATE 検査を追随させる。**U-S1 の UPDATE は、是正後の bind 名に合わせる**。**是正済み**(2026-10-08。`origin/feature/um1-player-roster-opponent` の先頭 `18f0e4ff`、本体 `67c4495b`): UPDATE の WHERE は `テナント列 = :where_tenant_id` と `id 列 = :where_id`(team_records の `kind` は `:where_kind`)。旧名は検査で拒否される。SELECT・INSERT の bind 名は変わらない
- **台帳の `result` は NOT NULL で、変更を禁止するトリガがある**。そのため T1(D5 の記録)と T6(確定結果)を時間的に分けて書けない。T1 の時点で確定結果まで書く形になる(SP 8-1 の T1・T6 の区別は、書き込みの順序ではなく内容の区別として読む必要がある)

### S-4: TSK-332 の契約の争点

| 争点 | 結果 |
| --- | --- |
| `tElementCommitment` の exact-key record | **形を変える必要があった**。資産側の `{mode}` だけでは比較できない。経路ごとの T ID の集合、T の内部の保存単位(T2 = スロット・イベント、T9 = 台帳・原本)、「書き込みなし」(墓標の T4)と「状態変化なし」(改訂の T3)の表現が要る。T1 と T6 は同じ台帳行を証拠にするので、DB からは独立した確定を証明できない |
| 複数 case と `caseId` | **成り立った**。観測点を case の中に置き、比較単位に `caseId` と注入対象を含めると、孤立した観測点と重複を拒否できた |
| P5 の判別共用体 | **成り立った**。B3a は未使用 D5 + 拒否原本、B3b は先着原本 + 同じ D5・異なる内容の後着を必須にし、欠落を拒否できた |
| 到達しない注入点 | **成り立った**。`expectedReachability: "unreached"` と hook の呼び出し 0 回を、実際の DB 経路で確かめた |

- 正本 10-3 との差: 単一の `faultInjection`・`expected` を、安定した `caseId` を持つ `cases` に変える必要があった(構造変更のため `schemaVersion: 2`)。比較単位は `scenarioId × caseId × 注入対象 × 観測点 × 全期待フィールド`
- 共通の期待フィールド 10 個を観測点ごとに必ず揃えても、省略理由を持つフィールド(例: 写像を実装していない経路の `temporaryIdMapping`)は、DB で検証した値と同じ重みでは扱えない

### U-S1 の計画への帰結(Claude の判断)

1. **ステップ 2(リポジトリ基底の拡張)は必要**。D3 の UPDATE・スロットの版 UPDATE・JSONB の結果の実体化の 3 点が、#95 の形では表せない。さらに #95 の UPDATE の CompileError が直るまでは、UPDATE 全般が `handle.run` を通らない可能性がある
2. **ポートの拘束(S-2)を設計し直す**。型だけでは防げないので、別スコープを開けない仕組みを設計に入れる
3. **D5 の再照合(S-5)は、イベントのトランザクション内で行えば成り立つ**。計画レビュー 1 周目の P1-4 への答えになる
4. **T1 と T6 は同じ書き込みで確定する**形を前提にする
5. **TSK-332 の契約は、スパイクの資産の形(`cases`・T の内部単位・`no-write` / `no-change`)を出発点にすれば紙の設計より収束しやすい**(推論)。runner の吸収範囲(R-1)はこの結果を踏まえて人間が決める
