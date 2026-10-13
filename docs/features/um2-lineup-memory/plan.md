---
feature: um2-lineup-memory
status: active
承認: 済（2026-10-13・追加の競合 P0 計画も利用者承認）
重さ分類: コア領域
worktree: /tmp/pitchlog-um2-lineup-memory-step4
notion: https://app.notion.com/p/3da93b75e687813d95faef7fdc65722a
branch: feature/um2-lineup-memory-finalize
created: 2026-10-13
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: U-M2 前回スタメンの記憶・復元（TSK-394）

> **計画承認済み（2026-10-13・本会話の利用者）。** [TSK-363 の承認済み実装単位計画](../product-impl-unit-split/plan.md)に従う。[TSK-394 の正式カード](https://app.notion.com/p/3da93b75e687813d95faef7fdc65722a)はステップ 2 統合後に取得でき、共通 DoD 以外の追加条件はなかった。担当者はカードの既存プロパティを維持する。

> **ステップ 3 の後続 PR 範囲（2026-10-13）**: PR #121 は `develop` にマージ済み（統合点 `edbef663c44b1585e325be859fd1f511951ea09c`）。本後続ブランチ `feature/um2-lineup-memory-get` はその時点の最新 `origin/develop` を基点とする専用 worktree で、上表のステップ 3 の GET・DTO・経路登録・派生資産・外部入口テストだけを扱う。U-G1 の試合作成・スタメン確定とステップ 4 は含めない。PR 作成・push は当初保留し、後述の入力固定に必要な Draft PR 番号取得だけを追加承認された。TSK-394 全体は部分充足のままとする。新しい凍結基準の改訂は PR #121 の承認を流用せず、7.7 の新しい受理単位で審査する。

> **PR #124 の入力固定コミット例外（同日・利用者承認）**: 上記の PR 作成・push 停止は計画・作業ログだけの準備コミットと Draft PR 作成に限って解除され、番号 `masaki1025/pitchlog#124` を取得した。認可 oracle は経路入力 8 資産の作業ツリーと `oracle_commit` が指すコミットの blob を照合するため、ステップ 3 の単一コミット前に変更される registry・matrix と各派生 lock の **4 ファイルだけ**をローカル中間コミットへ固定することを規約 6.1 の本 PR 限定例外として承認された。このコミットは入力の識別点であり、ステップ 3 完了を意味しない。製品コード・検査器・oracle seal・正式受理履歴を混ぜず、単独では push しない。別途人間確認を受けた再封印・正式受理履歴とステップ 3 実装の検査・コミット後に、同じ Draft PR へまとめて push する。

> **ステップ 4 の後続作業（2026-10-13）**: PR #124 は最新 HEAD `7fe7ecf6` で CI 12 件すべて通過し、人間逐行確認後に `2a4568285be8a3d412822f4a9e239d11321eb5da` として `develop` へ統合済み。本ステップはこの統合点を基点とする専用 worktree で、品質結果と U-G1 / U-F8 への接続記録だけを追随する。両単位の所有する試合作成・画面実装は含めず、FR-016 は実際の接続まで部分充足とする。

> **計画レビュー 1 周目（2026-10-13、`codex_run.py review adversarial`）**: P0 2 件（`FOR UPDATE` を operation 検査が拒否 / JSONB の可変値を結果境界が拒否）、P1・P2 は 0 件。両方を 4 節のステップ 2 に反映した。
>
> **計画レビュー 2 周目（同日、差分・影響節）**: 可決、P0/P1/P2 すべて 0 件。`計画レビュー周回` は指摘反映を伴う周のみ数えるため 1 のまま。その後の PO 対話で紅白戦の記憶規則は了承された（本計画の「DH と紅白戦」）。TSK-394 固有カードの照合は未了。
>
> **2 周目後の差分（2026-10-13）**: 利用者から伝えられた PO 了承を反映し、U-G1 への接続案・確認事項を明記した。既存の独立レビューはこの差分を再審査していないため、人間の計画承認時に本差分を確認する（設計書 6.3 のレビュー回数上限）。

> **P0 追補承認済み（2026-10-13・本会話の利用者）**: ステップ 2 の登録済み token から self・現役検証を迂回できることが実 DB で再現した。追補計画の独立敵対レビューは 2 回実施し、最終 P0/P1/P2 は 0 件。認可実行境界を含む追補範囲の人間承認を得た。

> **P0 追補の実装レビューで見つかった追加契約（承認済み）**: 独立レビューは P0 2 件・P1 1 件。保存 JSON の識別値と照合値の不一致、および不足した直接 UPDATE / 公開実行器の負例は承認済み追補内で是正した。選手照合後の在籍変更競合には、次段落の追加計画と人間承認に従って対処した。

> **競合 P0 追加計画承認済み（2026-10-13・本会話の利用者）**: 追加計画の独立レビュー 2 回目は P0/P1/P2 すべて 0 件。利用者は選手 1 行の限定ロック、U-M1 一括更新の取得順、repository revision 15→16、PR #121 の単一未マージ受理記録と archive digest の追随を承認した。人間の逐行確認・マージ承認とは別である。

## 1. 背景・目的

`../../requirements/requirements-pitchlog-2026-07-22.md` の FR-016 は、チーム選択時に直近の確定スタメンを打順・守備位置・選手 ID で復元し、非現役枠を自動採用せず差し替えを示すことを要求する。記憶はチームにつき直近 1 件。旧 FR-001 の復元基準も継承する。U-M2 は `../product-impl-unit-split/plan.md` の帯 2 に属し、U-M1 に依存する。

| DoD の根拠 | 確認できた内容 | 状態 |
| --- | --- | --- |
| 要件書 FR-016・旧 FR-001 | ID ベースの直近スタメン復元、非現役枠の差し替え、チームごとに 1 件 | 正本で確認済み |
| 要件書 FR-001・設計書 7-4 | 通常 9 人、DH 制は投手別枠を含む 10 人、確定時の背番号スナップショット | 正本で確認済み |
| 設計書 7-1・7-4 | 紅白戦では先攻・後攻が同じチームレコードを参照し、記憶キーはチームレコード単位 | 正本で確認済み |
| TSK-363 の承認済み実装単位計画・U-M2 カード条件 | 帯 2、主所有 FR-016、依存 U-M1、着手可、コアレビュー、共通 DoD | **確認済み**。本書の経路表・DoD・テスト計画へ反映 |
| TSK-394 固有のカード | 追加 DoD・担当状態 | **確認済み**。既存共通 DoD 以外の追加条件なし。カードの担当者プロパティは維持 |

ステップ 1 着手時の `origin/develop`（`212379b5`）には U-M1 の選手読み取り・在籍変更と、`lineup_memories` / `game_lineups` の ORM があった。ステップ 2 の保存・読み取り operation は PR #121 で統合済み。ステップ 3 はその統合点 `edbef663` を基点に、取得 GET を追加する。U-G1 の試合作成・確定処理と U-M2 保存 operation の呼び出し接続は未実装で、U-G1 側の所有とする。

## 2. スコープ

### やること

- U-G1 が試合開始時に確定した自チームの先発オーダーを、同一 DB トランザクションでチーム別直近 1 件として記憶する内部 operation。外部公開の保存 API は作らない。U-G1 側の呼び出し実装は同単位の所有とする。
- チーム選択用の取得・復元 GET API。保存内容の選手 ID、打順、守備位置、DH 制の投手別枠を保全する。表示名・背番号は選手の現在値を使い、確定時の背番号は U-G1 が `game_lineups` に焼き込む。
- 非現役・論理削除・欠損・別チームの選手を自動採用せず、差し替えが必要な枠を返す。復元可能な枠だけを採用できる形にする。
- テナント境界、同時保存、実 DB、自動テスト。既存の U-M1 operation / transaction / 認証 / 認可契約を再利用する。

### やらないこと

- 試合作成と試合ライフサイクル本体（U-G1）。U-M2 の内部保存 operation を呼ぶのは U-G1 の試合開始処理だけとする。
- 外部公開の保存・更新 API。FR-016 はチーム選択時の自動復元を求め、任意の保存操作を求めない。保存の唯一の契機は FR-001 のスタメン確定である。
- 試合準備画面（U-F8）、選手・在籍変更（U-M1）の機能追加、同期・記録権・移行、複数パターン記憶。競合 P0 を閉じるための既存 U-M1 一括在籍変更における行取得順の固定だけは、下記の追加承認後に限定して行う。
- TSK-541・538・470・238・391・479 が所有するファイルや経路の変更。重複が判明したら当該ステップを止め、計画の射程を再審査する。

## 3. 影響する正本

| 正本 | 予定 | ゲート |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md`、`docs/design/data-model.md`、ADR | 反映なし。FR-016 と 7-4 の既決事項に従う | — |
| `contracts/authz/route-registry.json`、`http-route-matrix.json` と派生 lock / oracle、`contracts/tenant_boundary/*` | 取得 GET 1 本の route ID と、内部 read / insert / update operation を既定の登録・凍結受理手順で追加する。保存用の HTTP 行は増やさない | コア領域 PR レビュー、凍結資産は 7.7 |
| `backend/src/pitchlog/authz/capability_registration.py` / `backend/src/pitchlog/repositories/{base,tokens}.py` と該当テスト | **レビュー P0 2 件の実行可能性是正**。単一表・テナント束縛・対象 ID 限定のロック読み取りだけを許可し、JSONB 結果を深い不変値として閉じる。一般の任意 SQL や可変結果は引き続き拒否 | コア領域 PR レビュー |
| `backend/src/pitchlog/repositories/{operation_registration,transaction,base,lineup_memory}.py` と該当テスト | **P0 追補（承認済み）**。登録済み U-M2 read / insert / update token の実行直前に、同一トランザクションで self チームと書き込み payload の選手所属・現役性を検証する。UPDATE は対象記憶の team ID と移行由来不可も SQL で限定する | 計画追補の敵対レビュー 2 回・人間承認済み。コア領域 PR レビュー |
| `backend/src/pitchlog/authz/capability_registration.py`、`backend/src/pitchlog/repositories/lineup_memory.py`、`backend/src/pitchlog/api/routers/players.py` と該当テスト | **競合 P0 修正（承認済み）**。厳密な現役選手 1 行 `FOR UPDATE` と、在籍一括更新の行取得順を選手 ID 順へ統一する。レスポンス順序は入力順を維持する。U-G1 にチーム行→選手 ID 順の取得順を申し送る | 追加計画の敵対レビュー 2 回・人間承認済み。コア領域 PR レビュー |
| `contracts/tenant_boundary/repository-contract.json`、`contracts/tenant_boundary/base-allowlist.json`、対応 snapshot、`backend/src/pitchlog/repositories/repository_contract.py` と該当契約テスト、`tests/fixtures/frozen-archive-cases/manifest.json` | **競合 P0 修正（承認済み）**。repository revision 15→16 で U-M2 専用 token 型 1 件を追加し、生成済み契約定数と完全一致させる。PR #121 の単一未マージ受理記録の最終状態を更新。base-allowlist revision 27・既存シンボル許可・既存受理済み履歴は維持。比較 corpus の digest 1 値だけを再算出する | 7.7 の受理単位・snapshot・digest・manifest 検査後、コア領域 PR レビュー |
| `.claude/core-areas.json` | 既存の登録 path に収まるかをステップ 1 で検査。新 path が必要なら 6.3-⑤ のレビュー対象として同 PR に含める | コア領域 PR レビュー |

## 4. 実装方針

**コア領域。** TSK-363 の起票時カード条件は U-M2 を機械判定「非コア」・意味判定「コア（fail-closed）」とした。同計画の**承認後の是正**（「(i) は機械判定で閉じた」）は、入口の `route_id` を `contracts/authz/http-route-matrix.json` に追加する葉 6 本を**機械判定でもコア確定**とする。本 U-M2 も取得 GET を開くため、後者を現行判定として扱う。意味判定もコアのまま維持し、敵対レビューと人間の逐行確認を適用する。非コアへの降格を本計画で行わない。テナント内の選手・チーム・記憶への DB 到達と新規 API は、設計書 6.3 のテナント分離境界および `.claude/core-areas.json` の登録対象。`lineup_memories` の JSON は選手 ID・打順・守備位置の単一契約として DTO で固定し、名前や背番号を識別キーにしない。保存は確定時だけとし、読み取りによって記憶を更新しない。

### U-M2 の経路表（TSK-363 の必須項目）

| 入口・操作 | 所有 | 識別・到達 | 越境テスト |
| --- | --- | --- | --- |
| `GET /team-records/{team_record_id}/lineup-memory` | U-M2 | 外部 HTTP 入口 1 本。`ROUTE:RECORD:lineup_memories:read`（既存の `record_and_aggregate` の資源×操作規則）。認証済みテナント内の self チーム 1 件に限定 | U-M2 の同一 PR で外部から直接叩き、他テナント・相手チーム・対象不在が 404、記憶内容が越境しないことを検査 |
| スタメン記憶の内部保存 operation | U-M2 が提供、U-G1 が呼ぶ | HTTP 入口ではない。同一 `tenant_transaction_scope` と `TenantContext` を使い、対象 self チーム 1 件に限定 | U-M2 の DB テストで別テナント・別チームへの書き込みを拒否。U-G1 の入口テストでも呼び出し経路を検証 |
| スタメン確定・`game_lineups` 保存 | U-G1 | 試合作成の入口と保存表現は U-G1 が所有 | U-G1 の入口テストで検証 |

U-M2 は**一覧入口と削除操作を追加しない**。GET は `team_record_id` で 1 件を読むため、TSK-363 の「一覧はページング」は対象となる一覧がなく非適用。スタメン記憶は active 1 行を更新し、削除せず保全するため「削除は論理削除」は削除操作がなく非適用。ただし物理削除禁止は横断 DoD として適用する。

**ステップ 1 で固定する登録順。** 取得 GET の `route_id` は `contracts/authz/product/capability-catalog.json` の `lineup_memories:read` と既存の `ROUTE:RECORD:<資源>:<操作>` 規則に合わせる。内部保存は HTTP 経路を増やさず、`team_records` の対象行ロックを伴う read、`lineup_memories` の read / insert / update、`players` の ID 限定 read を登録済みの単一表 operation として使う。U-G1 の `games` / `game_lineups` 保存は本単位に登録しない。ステップ 2 で内部 operation とテナント境界の凍結資産を整え、ステップ 3 で GET 実装と同じ変更単位に `route-registry.json`・`http-route-matrix.json`・派生 lock・独立した exact-set 期待値・外部入口テストを追加する。凍結資産の受理は設計書 7.7 に従い、人間確認を飛ばさない。既存の他経路行・test owner を変更しない。

**FR-016 とコア 5 領域の当てはめ。** テナント分離は対象（GET・内部保存の認可と越境防止）。同期プロトコル、状況計算、記録権、データ移行は本 U-M2 の変更対象外。打順・守備位置は確定オーダーの識別値を保存・復元するが、試合中の状況計算・イベント遷移は行わない。移行由来の記憶を読み取り補助へ出さない判定は行うが、旧データの変換・移行は行わない。判定に迷う変更が生じた場合は設計書 6.3 に従いコア側で審査する。

**照合結果。** 既存の `tenant_transaction_scope` は複数の登録済み operation を同一トランザクションで実行できる(`backend/src/pitchlog/repositories/transaction.py`)。`GameLineup` と `LineupMemory` の表もある(`backend/src/pitchlog/db/game_state/models.py`)。`games.away_team_record_id` / `home_team_record_id` は先攻/後攻を表し、紅白戦では同じチームレコードを指せる（`data-model.md` 5-1・7-1）。ただし **U-G1 の確定処理・呼び出し契約・スタメン用の守備位置識別値と DTO はまだ存在しない**。`game_lineups` には `game_id` と `team_record_id` があるが先攻/後攻の識別列が無く、`entries_with_uniform_number_snapshot` JSON の確定済み要素スキーマも無い。紅白戦の両側が同じチームレコードを指す場合、既存列だけでは 2 件のスナップショットの側を判別できない。既存の「守備位置番号 1-9」は移行元プレイ行の原本事実（`data-model.md` 12 節）であり、スタメン用 DTO の値域と同一とみなさない。

**接続契約案と責務。** U-G1 が試合作成・先攻/後攻それぞれのスタメン確定・`game_lineups` の保存を管理する。U-M2 は確定済みの自チームオーダーを受ける内部保存 operation と取得・復元 GET を提供する。保存 operation は呼び出し元の `tenant_transaction_scope` を使い、スタメン確定と記憶更新を原則として同一トランザクションに置く。U-G1 側には、①先攻/後攻を区別できる試合スタメンの保存表現、②確定オーダー要素の DTO と守備位置の型・値域、③同一 scope と `TenantContext` を U-M2 operation へ渡す呼び出し箇所、④紅白戦では後攻側を記憶更新に渡すことを申し送る。①〜③の具体的な実装契約は U-G1 担当の確認待ちであり、本計画は未承認の識別列・値体系・外部 API を確定しない。

### 保存と U-G1 の呼び出し契約

FR-001 はスタメン確定と試合開始を一つの操作として扱い、`data-model.md` 7-4 は `game_lineups` を確定時の先発スナップショットとする。**U-G1 への提案契約**: 試合作成の**同一 `tenant_transaction_scope`** で、チーム・選手・打順・守備位置を検証し、先攻・後攻それぞれの `game_lineups` を書いた後、コミット前に U-M2 の内部保存 operation を呼ぶ。渡すものは同じ `TenantContext` に束縛された scope、self の `team_record_id`、記憶する側の確定済み先発オーダーの ID / 打順 / 守備位置の値。U-M2 は自己の `tenant_transaction_scope` を開かず、`kind='self'` のチームに限り `lineup_memories` の active 行を更新・初回は挿入する。いずれかが失敗すれば試合作成・両側スナップショット・記憶をまとめてロールバックする。保存 API は作らない。**このトランザクション接続は U-M2 からの契約案であり、U-G1 担当が接続時に確認する。**

**同時確定の順序。** U-G1 は記憶の読み書きより先に対象の self チームレコード行を `SELECT FOR UPDATE` でロックする。同一チームの確定はこの行で直列化し、後にロックを得て**正常にコミットした確定**のオーダーが直近 1 件となる。失敗・ロールバック・取得 GET は記憶を変えない。物理削除や履歴行の追加はしない。既存の部分一意索引 `uq_lineup_memories_active` が active 1 件を補強する。**現行の capability 検査は `FOR UPDATE` を明示拒否する**(`backend/src/pitchlog/authz/capability_registration.py:941`)ため、U-M2 のステップ 2 で対象表 1 つ・テナントと ID の必須 bind・`FOR UPDATE` 以外の lock 変種を拒否する狭い登録規則と負例を加える。これは本 operation の実行に必要な製品認可境界の変更であり、一般的なハーネス拡張はしない。

**P0 追補（承認済み）。** `save_lineup_memory()` だけが self チーム・現役選手を検証する実装では、同じ registry の `LineupMemoryReadToken` と非公開 insert / update token を `scope.run()` へ直接渡すと検証を迂回できる。`TenantRepositoryBase.execute()` も同じ登録 token を受け付ける。`OperationRegistration` に U-M2 用の実行前検証を追加し、両実行器が**同一テナント・同一トランザクション内、対象 SQL の実行前**に呼ぶ。検証は `_SelfTeamLockToken` と、次段落で承認された現役選手 1 行ロックを使う。保存 SQL の束縛値を先に確定し、その同じ値から選手 ID・チーム ID を照合する。束縛する UUID は元 token の参照から独立した値へ固定し、照合後に元 token の内部値を変えても未照合の ID へ SQL を向けられないようにする。UPDATE token に対象 `team_record_id` を含め、UPDATE 文もその ID と `migration_preserved_only=false` に限定する。未知・不正 JSON、重複選手 ID は拒否し、helper と直接 token が同じ検証関数を使う。GET 側で直接 read token を使う場合も self 検証を通す。既存の capability ID、SQLA 許可 API、テナント束縛、受理済み履歴は広げない。新 token 型に対応する凍結改訂は次段落の承認範囲に従う。

**追加の競合 P0 修正（承認済み）。** 書き込み preflight の通常 `PlayerReadToken` は他トランザクションによる在籍変更を待たせない。U-M2 専用の非公開 `_ActiveLineupPlayerLockToken` を 1 種追加し、既存の `_build_lineup_memory_statement` 内で `players` の tenant ID・選手 ID・チーム ID・固定 bind `roster_status_key='active'`・`hidden_at IS NULL` をすべて条件にした 1 行 `SELECT id FOR UPDATE` を作る。書き込み preflight は self チーム行の後、各選手行を UUID の昇順でロックし、同じトランザクションの INSERT / UPDATE 完了まで保持する。ロック中の在籍変更・論理削除はコミットまで待機し、先に変更が確定していれば行が返らず保存を拒否する。読み取り preflight は従来どおり self チーム確認のみ。`capability_registration.py` はこの完全一致形の `CAP:players:read` ロックだけを許可し、任意の表・条件不足・ロック変種を拒否する。`SELECT id`・通常の `FOR UPDATE` のみ許可し、条件欠落・別表・`NOWAIT` / `SKIP LOCKED` / `FOR SHARE` 等の変種は拒否する。U-M1 の一括在籍変更は同じ UUID 昇順で行ロックを取り、返却配列は入力順のまま保つ。U-G1 はチーム行→選手 UUID 昇順の順で取得し、先に選手行をロックしない。新しい SQLA 構築シンボルと外部 API は増やさない。追加 token 型のため `repository-contract.json` の revision 15→16 と `base-allowlist.json` の受理履歴への PR #121 未マージ記録更新が必要。既存受理済み履歴は変更せず、base-allowlist 本体の revision 27 と既存シンボル許可は維持する。`contracts/tenant_boundary` ツリーを入力とする frozen-archive manifest の `corpus_inputs.digest` 1 値だけを再算出し、他の pin・ケースは変更しない。7.7 の具体的な snapshot / digest / movement_fact は変更後に検査器の指示どおり算出し、正式台帳反映前に差分を確認する。

### 復元 GET と DTO

`GET /team-records/{team_record_id}/lineup-memory` だけを U-M2 の外部入口とし、既存の認証・テナント文脈を通す。対象は当該テナントの `kind='self'` かつ非表示でないチームレコードのみ。対象不在・他テナント・相手チームレコードは 404。記憶がなければ 204。移行由来で `migration_preserved_only=true` の記憶を入力補助へ出さない。

200 応答は `entries` の配列を保存時の順で返す。各枠は `batting_order`（通常枠 1〜9、DH 投手別枠は `null`）、`fielding_position`（確定スナップショットと同じ識別値）、`player_id`（採用可能な現役選手の UUID、それ以外は `null`）、`name`・`uniform_number`（採用可能な選手の**現在値**、それ以外は `null`）、`replacement_required`（真偽値）を持つ。非現役（`other`・`ob`）、論理削除済み、欠損、チーム不一致は、元の打順・守備位置だけを保ち `replacement_required=true` とする。理由の区分や過去の名前・背番号は返さない。選手照合はテナント・チーム・記憶中の ID に限定した SQL で行い、全名簿を読み込まない。空き枠は UI が差し替えるまで確定に使えない。

U-M2 は U-G1 が確定したオーダーの構造をコピーして保全する。守備位置の値域、9 名・DH 10 人目の検証は U-G1 の単一実装を利用し、U-M2 にコピー実装を作らない（NFR-018）。**守備位置識別値は現時点で照合先となる U-G1 DTO が無く、確定不能。** 上記の応答 DTO は欄の形と採用可否の意味を定める提案であり、`fielding_position` の型・値域と JSON 要素スキーマは U-G1 の契約ができた時点で一致させる。U-M2 で別の番号体系を定義しない。保存時は元のオーダーの要素数・順序・値を崩さず、復元時は各選手 ID の現在の採用可否だけを判定する。

**記憶の読み取り境界。** `lineup_memories.lineup` は JSONB 配列だが、現行 `scope.run()` は `list` / `dict` を拒否する(`backend/src/pitchlog/repositories/base.py:280`)。ステップ 2 で JSON の配列とオブジェクトを再帰的に不変な値へ変換してから結果を返す閉じた規則を追加する。取り出した値は記憶の DTO で型を検証して扱い、未対応の可変型・遅延型は拒否し続ける。可変な DB ドライバ値を scope 外へ漏らさない負例を置く。

### DH と紅白戦

`data-model.md` 7-4 に従い、通常は打順 9 枠、DH 制はその 9 枠に投手別枠 1 件を加えた**一つの記憶**とする。DH の有無で別パターンを保存しない。`data-model.md` 7-1 に従い、新規運用の記憶は self チームレコード 1 件に限定する。紅白戦は先攻・後攻が同一チームレコードを指すため記憶キーも 1 件である。**PO 対話で了承された本計画の規則（2026-10-13 の利用者報告）**: 紅白戦では先攻・後攻それぞれの試合スタメンを保持し、チーム単位の直近 1 件の記憶は**後攻側**の確定オーダーで更新する。FR-001・FR-016・7-1・7-4 は両側からの選択規則を定めていないため、既存正本の既決事項とは区別する。側を判別する具体的な保存表現は U-G1 担当が確認する。

### 承認と接続に必要な確認

1. **カード照合済み**: TSK-363 の U-M2 共通条件を反映済み。ステップ 2 統合後に TSK-394 カードを取得し、固有の追加 DoD がないことを確認した。カードの担当者プロパティは維持する。
2. **U-G1 接続時の担当確認**: 側識別を含む試合スタメンの保存表現、`fielding_position` の型・値域と要素 DTO、同一 scope で内部 operation を呼ぶ箇所を U-G1 担当と突合する。U-G1 の実装完了は本計画の作成・審査の前提にしない。確認まで未承認の保存表現や値体系を製品契約として扱わない。

### 実装ステップ（コミット単位 — 設計書 6.1）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | TSK-363 の共通 DoD・既決の紅白戦規則・U-G1 への申し送りを実装項目へ反映し、取得 GET の route ID と単一表 operation / 凍結資産の変更順を固定する。TSK-394 固有の追加条件が提示された場合は着手前に照合する | FR-016 と確認済み DoD から DTO・保存契機・テストへの対応が追える。保存 HTTP 入口が 0 本で、U-G1 担当の確認項目が未確定の契約と区別して列挙されている |
| 2 | 自チーム記憶の読み取り・内部保存 operation と必要な認可・テナント契約を追加する。対象 self チーム 1 行だけの `FOR UPDATE` を capability 検査へ明示登録し、JSONB 読み取り値の深い不変化を結果境界へ追加する。P0 追補の承認後、直接 token も実行直前に同じ不変条件を満たすよう是正する | 実 DB でチーム別直近 1 件、初回の同時 insert と更新の直列化、ロールバック、別テナント拒否、物理削除なしが green。`FOR UPDATE` は self チーム行と追加承認後の現役選手行の完全一致形だけを許可し、他表・tenant/ID bind 欠落・他 lock 変種を拒否、JSONB の入れ子の可変値を外へ漏らさず未知型を拒否する負例 green。直接 token による相手チーム read / insert、非現役・削除済み・欠損・別チームの選手 insert / update を拒否。**有効な自チーム選手 payload でも、相手チーム記憶 ID と `migration_preserved_only=true` 行を直接 UPDATE して変更できない** DB 負例を置く。凍結資産の受理記録が規約どおり。追加承認後は、在籍 UPDATE / 論理削除が先に確定したときの保存拒否と、保存側が先に選手行ロックを得たときの変更待機を実 DB の同期テストで確認する。直接 INSERT / UPDATE と公開実行器を含め、相互取得順でデッドロックしない。frozen-archive manifest の corpus digest を追随し、比較ケース・既存 pin を維持する |
| 3 | 取得・復元 GET と DTO を追加し、`ROUTE:RECORD:lineup_memories:read` を既存の登録・凍結受理手順でアプリへ登録する | 外部からの GET 直接テストで現役のみ自動採用。OB・その他・削除済み・欠損・別チームは差し替え。改名・背番号変更後も ID が保たれ、保存用 HTTP 経路は存在しない。route registry / matrix / 派生 lock / 独立 exact-set が一致し、7.7 の受理記録がある |
| 4 | 関連テストと品質ゲート、U-G1/U-F8 への接続記録を完了する | backend の該当 pytest、DB テスト、Ruff、ty、越境・認可・契約検査が green。U-G1 が記憶を更新する契約と U-F8 の復元表示契約が追跡可能 |

### ステップ 4 の品質結果と接続記録

PR #124 の最終 HEAD `7fe7ecf6` に対する [CI run 38410295986](https://github.com/masaki1025/pitchlog/actions/runs/38410295986) は、backend・harness・core-guard・tenant-boundary-bypass を含む 12 ジョブすべて成功した。harness の全 pytest は 28,934 件通過。ステップ 3 のローカル実 DB 保存・GET・関連 API / 境界は 94 件、認可・凍結履歴は 25,838 件、archive は 65 件通過した。Ruff・ty・backend format・oracle・派生資産・凍結不変条件も通過し、`backend/tests/conftest.py` の差分は 0 行。ステップ 4 は製品コードと認可資産を変更しない。

| 接続先 | U-M2 が提供済みの契約 | 接続先の所有・確認待ち |
| --- | --- | --- |
| U-G1 試合スタメン確定 | `save_lineup_memory(scope, team_record_id, lineup)`。`lineup` は `tuple[Mapping[str, object], ...]` で選手 ID・打順・守備位置を保全する。確定と同じ `tenant_transaction_scope` 内で呼び、失敗時は試合スタメンと記憶を一緒にロールバックする。記憶は自チーム直近 1 件。書き込み側は self チーム行の後に選手 ID 昇順で現役行をロックする | U-G1 が先攻・後攻それぞれの `game_lineups` を確定してからコミット前に呼ぶ。紅白戦の記憶更新には後攻側を渡す。側識別の保存表現、守備位置の型・値域、要素 DTO と実際の呼び出し箇所は U-G1 担当が確定・検証する。U-M2 はここを実装済みと扱わない |
| U-F8 試合準備・復元表示 | `GET /team-records/{team_record_id}/lineup-memory`。200 は保存順の `entries` を返し、各枠に `batting_order`、`fielding_position`、採用可能な現役選手の `player_id` / 現在の `name` / `uniform_number`、`replacement_required` を含む。非現役・削除済み・欠損・別チームは選手値を `null` とし差し替え必須。記憶なし・移行専用は 204、対象不在・他テナント・相手チームは 404。保存用 HTTP API はない | U-F8 の作業中計画は記録画面の独立部品に限り、API 接続・スタメン準備画面を含まない。後続の U-F8 担当が 204 と差し替え枠の表示、復元候補の採用操作を接続・検証する。U-M2 は画面を実装済みと扱わない |

U-G1 の確定 DTO が現れるまで、U-M2 側で守備位置の番号体系や 9 / DH 10 枠の判定を追加しない。U-F8 にも候補の採用を自動確定させず、`replacement_required=true` の枠は差し替えまで確定に使わないよう申し送る。この表は実装済み入口と担当側の未実装接続を区別する記録であり、未確認の担当合意を主張しない。

## 5. DoD（受け入れ基準）

- [x] TSK-363 の U-M2 実装単位条件（帯 2・FR-016・U-M1 依存・着手可・コア経路）を照合した。TSK-394 の正式カードを取得し、追加 DoD がないことを確認した。
- [x] 取得不能時の残余を示した計画への人間承認と、その後の正式カード照合を記録した。
- [x] 紅白戦の直近 1 件は後攻側で更新する PO 判断を本計画に反映した。
- [ ] U-G1 担当と、先攻・後攻を区別する保存表現、`fielding_position` の型・値域、要素 DTO、および同一 scope の呼び出し契約を接続前に突合した。
- [ ] 同一チームの前回確定スタメンを選手 ID・打順・守備位置で復元でき、改名・背番号変更に追従する。
- [ ] チームごとに直近 1 件だけを記憶し、別テナント・別チームの選手を採用しない。
- [ ] 非現役・削除済み・欠損の枠を自動採用せず、差し替えが必要と分かる。
- [ ] DH 投手別枠・通常 9 人の既存契約と、紅白戦について本計画で了承された規則に一致する。
- [ ] U-G1 の確定処理との接続点が明記され、実装済み範囲の保存・取得・復元が実 DB で動作する。
- [ ] 該当品質ゲートとコア領域のレビュー・凍結資産手順を通過する。
- [ ] ロック読み取りと JSONB 結果の実行可能性是正が限定的で、既存の fail-closed な負例を維持する。
- [ ] 経路表の GET 入口について NFR-019 の越境テストを同一 PR に置き、外部から直接実行する。内部保存 operation のテナント境界も DB テストで確認する。
- [ ] `backend/tests/conftest.py` の差分を 0 行に保つ。
- [ ] 一覧と削除は本 U-M2 に存在しないため、ページングと論理削除の操作別 DoD は非適用と記録する。物理削除は禁止し、全機能でテナント分離と利用者入力の自動エスケープを維持する。
- [ ] コア領域の実装 PR に敵対レビューと人間の逐行確認記録を付け、pytest / Ruff / ty を green にする。

## 6. テスト計画

| 種別 | 対象 | 検証内容 |
| --- | --- | --- |
| 単体・契約 | DTO と U-G1 から受ける先発オーダー | 通常 9 枠 / DH 10 枠の順序・打順・守備位置・選手 ID が保存と復元で欠落・変換されないこと。構造の妥当性判定は U-G1 の契約テストへ委ね、U-M2 に同じ判定を複製しない |
| DB | 記憶 repository | 保存・再保存・最新 1 件・同時実行・ロールバック・テナント分離。直接 read / insert / update token と `TenantRepositoryBase.execute()` の迂回負例を置き、非現役・削除済み・欠損・別チーム選手を拒否する。**UPDATE は有効な自チーム選手 payload でも相手チーム記憶 ID と `migration_preserved_only=true` 行を変更しない**。在籍変更・論理削除との順序を Event 同期の実 DB テストで両方向検証し、直接 token と公開実行器にも適用する。紅白戦の両側保存と後攻側による記憶更新は U-G1 接続テストで検証 |
| 認可・結果境界 | 単一表ロック token / JSONB 結果 | 厳密な self チーム行と追加承認後の現役選手行だけの lock を許可し、他表・条件欠落・bind 欠落・他 lock 変種を拒否。入れ子の JSON 配列・オブジェクトは深い不変値になり、未知可変型は拒否 |
| API / 越境 | 取得・復元 GET | NFR-019 に従い、同一 PR のテストから製品外の GET 入口を直接叩く。実 DB 経由、認証/認可、別テナント、欠損、論理削除、在籍 3 区分、改名・背番号変更。保存用 HTTP 経路が無いこと |
| 回帰 | U-M1 と関連契約 | 選手の更新・在籍変更、authz route、tenant boundary、既存 DB テスト |

実装ステップごとに該当テストを実行し、最後に `backend/` の `uv run ruff format --check`、`uv run ruff check .`、`uv run ty check`、`uv run pytest` と必要なルート契約検査を実行する。`backend/tests/conftest.py` の差分 0 行、物理削除 0 件、利用者入力の全出力経路での自動エスケープを PR 差分で確認する。人間の逐行確認は製品コードの PR 差分ができた段階で実施・記録する。
