# TSK-394 計画レビューと承認準備（2026-10-13）

- 対象: `docs/features/um2-lineup-memory/plan.md`（2026-10-13 に利用者承認済み）
- コア領域の独立レビュー: `codex_run.py review adversarial` 1 回目は P0 2 件、P1/P2 0 件。`FOR UPDATE` の operation 検査拒否と JSONB 可変結果の境界拒否を採用し、ステップ 2・影響ファイル・負例テストへ反映した。
- 2 回目は反映差分と影響節を確認し、可決・P0/P1/P2 すべて 0 件。指摘反映を伴う周は 1 回のため、計画書の `計画レビュー周回: 1` を維持した。
- 2 回目後の差分: 利用者が伝えた PO 了承に従い、紅白戦は両側の試合スタメンを保持し、チームの直近記憶を後攻側で更新する規則へ変更した。U-G1 が試合スタメン確定、U-M2 が内部保存 operation を担当し、原則同一トランザクションで接続する案と U-G1 担当の確認項目を明記した。外部保存 API、製品コード、正本は変更していない。
- 2 回目後の差分は独立レビュー未実施。設計書 6.3 の基本枠 2 回を使ったため、承認者が採否記録と最終差分を確認する。追加レビューが必要なら同節の PO 裁定を記録する。
- 当初の計画承認ブロッカー: 現 Notion 接続先で TSK-394 カードを取得できず、正式 DoD・担当状態・依存を照合できなかった。後述の TSK-363 実装単位条件が提示されたため、共通条件は照合済みとし、TSK-394 固有の追加 DoD・担当状態だけを残余として人間の承認判断に示す。U-G1 の側識別保存表現・守備位置値域・要素 DTO・scope 呼び出し箇所は接続時に担当確認する。

## TSK-363 の実装単位条件との照合

- 利用者が U-M2 の正式な実装単位カード条件を提示。TSK-363 の承認済み計画と照合し、帯 2・主所有 FR-016・依存 U-M1・着手可を本計画へ反映した。TSK-394 固有の追加 DoD・担当状態は引き続き未確認と区別する。
- TSK-363 の起票時カードは機械判定「非コア」、意味判定「コア（fail-closed）」だが、同計画の承認後の是正は新規 GET の `route_id` がコア資産へ入る葉 6 本を機械判定でもコア確定とする。本計画は現行のコア扱い、敵対レビュー＋人間逐行確認を維持し、降格しない。
- 経路表を追加し、GET 1 本・内部保存 operation・U-G1 所有の試合確定を分離した。一覧と削除の操作は U-M2 に無いため、ページング・論理削除の操作別 DoD は非適用。物理削除禁止、全機能のテナント分離、自動エスケープは適用する。
- NFR-019 の GET 越境テストを U-M2 の同一 PR へ置き、製品外から直接実行する計画、`backend/tests/conftest.py` 差分 0 行、pytest / Ruff / ty green を DoD に追加した。
- 計画レビューの独立レビュー 2 回という記録は維持。今回の追記差分は人間の計画承認時に確認する。6.3 の人間逐行確認は**実装 PR のコード差分が対象**であり、未承認・コード差分 0 行の現時点では未実施。PR で確認者本人が実施記録を残す。

## 人間の計画承認

- 2026-10-13、本会話の利用者が計画を「承認」と明示した。対象は TSK-363 の共通 DoD、紅白戦の後攻側記憶、U-G1 接続案、TSK-394 固有の追加 DoD・担当状態が未確認である残余、および独立レビュー 2 回目後の追記差分を示した現行計画。計画書 frontmatter を `承認: 済(2026-10-13・利用者)` へ更新した。
- この承認は実装 PR の人間逐行確認を代替しない。逐行確認はコード差分ができた時点で別途実施する。

## 実装ステップ 1 の準備結果

- 取得 GET の経路識別子を、既存の `record_and_aggregate` 規則に従い `ROUTE:RECORD:lineup_memories:read` と固定した。外部保存 API は 0 本のまま。
- 内部保存 operation が使う単一表は `team_records`（対象行のロック読み取り）、`lineup_memories`（read / insert / update）、`players`（対象 ID の読み取り）とした。`games`・`game_lineups` の保存は U-G1 の所有である。
- 変更順は内部 operation とテナント境界資産をステップ 2、GET・route registry / matrix・派生 lock・独立 exact-set・入口テストをステップ 3 とした。設計書 7.7 の受理とコア領域 PR のレビューは別途必要。
- ステップ 1 完了時点で製品コード・契約資産は未変更。Claude を使用できないため、利用者が Codex による代替作業を明示承認した。以降のステップ検証・コミットも Codex が担当し、1 ステップ 1 コミットを維持する。

## 実装ステップ 2 の途中経過と凍結基準の受理

- 専用ブランチ `feature/um2-lineup-memory` のステップ 1 は `afc629bb` でコミット済み。ステップ 2 は製品コード・テスト・凍結契約の差分を作成したが、**未コミット**。
- `lineup_memory.py` に self チーム行ロック、対象 ID の現役選手確認、直近 1 件の初回挿入・更新、同一 scope での読取照合を追加。JSONB の入れ子を不変結果へ閉じ、通常 `FOR UPDATE` を対象 self チーム 1 行の登録形だけに限定した。
- 検証: スタメン記憶の実 PostgreSQL テスト 4 件、U-M1 の既存 HTTP 境界テスト 34 件、関連の単体・契約テスト 156 件、Ruff・ty が成功。全体 pytest は未実施。`backend/tests/conftest.py` は無変更。
- **7.7 受理**: `contracts/tenant_boundary/repository-contract.json` に revision 15 を用意した。受理履歴の authority は `contracts/tenant_boundary/base-allowlist.json`（`history_authority: true`）であり、PR #78〜#114 による repository 契約 revision 14 までの受理記録がある。repository 契約側の PR #72 `PENDING_ACCEPTANCE` は既存記録として無変更で残す。revision 15 候補を同じ資産の履歴へ重複追記した誤りは、新規分だけ除去した。正式台帳の末尾へ PR #121 の v2 記録を 1 件追記し、`scripts/check_tenant_boundary_bypass.py` は green。
- U-G1 の先攻/後攻の保存表現と守備位置 DTO は、接続時に担当確認する未確定契約のまま。今回の内部 operation は守備位置の値域を独自定義せず、確定済み要素の値を JSON として保存する。

## revision 15 凍結基準の受理内容

- 開発規約 7.7 の受理単位は同一検査についての 1 回のレビュー受理。`scripts/frozen_history.py` は authority 台帳に新規 v2 record を 1 件だけ追記し、PR 受理時には `acceptance_id` を GitHub event の `masaki1025/pitchlog#<当該PR番号>` と照合する。非authorityの repository 契約には履歴を追記しない。既存履歴・snapshot は変更しない。
- 直前の識別値は repository 契約 `contract_revision:14`、直後は `contract_revision:15`。他資産の識別値は据え置く。PR #114 の台帳末尾にある旧射影 SHA-256 は `9c318851f37cdf756d6da3b2a824ec3e74d377dce8fab7ff8cf8cabb17ace52c`。候補の新射影 SHA-256 は `cf9ad90b4a10340de0323e0a1664debfb10bfe728581054dbb92370b6d86dfda`。候補資産の `source_digest` は `1144a030711658449b7293eb919814a83a6af1fa4f9a6bdea75490287272e5ad`。
- 契約差分は `CAP:lineup_memories:{read,insert,update}` の 3 件、`_SelfTeamLockToken`・`LineupMemoryReadToken`・`_LineupMemoryInsertToken`・`_LineupMemoryUpdateToken` の 4 型、結果の `mappingproxy[str, T]` 文法、および revision 番号。対象 self チーム行だけのロック規則と JSONB の深い不変化に対応する。残余リスクは、lock 受理条件・結果型の拡張が認可境界を広げないこと、および最終 PR 差分と snapshot が一致することのコア領域レビュー確認。
- PR 番号・承認者・承認日が確定した後、authority 台帳へ `record_schema_version: 2` の 1 件を追加した。新旧全資産の識別値、宣言、movement policy、外部実装・資産の content-addressed snapshot、実差分の aspect、変更事実・理由を `frozen_history.py` の実遷移と一致させ、新規 snapshot のみを追記した。
- 台帳記録なしに検査を green にすることは 7.7-2 の fail-closed と矛盾する。受理記録を追記して検査を通す正規経路を採り、PR 番号・承認者・承認日を仮置きしていない。

## revision 15 の承認後の経過

- 2026-10-13、本会話の利用者が上記 revision 15 の受理案を「shounin」と明示承認し、承認者名を「yamada」と回答した。既存の承認者表記に合わせ、正式台帳の `approved_by` を「山田正輝」、`approved_on` を同日とした。
- 専用ブランチのステップ 1 コミットだけを push し、draft PR #121 を作成した。正式受理 ID は `masaki1025/pitchlog#121`。ステップ 2 の製品差分はローカルで未コミットのまま保持する。
- revision 15 の凍結射影を内容アドレス `cf9ad90b4a10340de0323e0a1664debfb10bfe728581054dbb92370b6d86dfda` の新規 snapshot に保存し、正式台帳へ PR #121 の v2 記録を 1 件追記した。旧 snapshot・旧履歴は無変更。`scripts/check_tenant_boundary_bypass.py` は green。
- `tests/fixtures/frozen-archive-cases/manifest.json` の比較 corpus digest は、契約資産の追加に追随して再計算した。比較ケースや検査器は変更していない。凍結 archive の該当11ケース、内部 operation と認可境界の156件、実 DB の4件、ルートと backend の Ruff・ty が green。`backend/tests/conftest.py` 差分は 0 行。

## PR #121 の CI で検出した追加の凍結基準移動

- ステップ 2 コミット `83a3d50b` を draft PR へ push した後、PR の `tenant-boundary-bypass` が `lineup_memory.py` の `sqlalchemy.select` 2 件、`insert` 1 件、`update` 1 件を TB005 で拒否した。コミット前の検査は新規ファイルを Git の検査対象として読めず、green を誤認した。`core-guard` は人間逐行確認の必須チェックがまだないため red で、これはステップ 4 の確認待ち。
- 最小の是正案は、4 つの SQL 構築関数を既存 roster と同じ方式の単一 `_build_lineup_memory_statement(kind: str)` にまとめ、`allowed_symbols` にこの 1 シンボルだけを登録すること。許可 API は `SQLA_SELECT`・`SQLA_INSERT`・`SQLA_UPDATE`、署名は `_build_lineup_memory_statement(kind: str) -> Union[Select, Insert, Update]`、正例 fixture は `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/lineup_memory.py`。実行 API や他シンボルは許可しない。
- この追加は `base-allowlist.json` の凍結射影を動かすため、同資産の `contract_revision:26→27` と PR #121 の**未マージ** v2 記録の after 側の識別値・宣言・snapshot を更新する必要がある。比較元の PR #114 記録、他の既存受理履歴、repository 契約側の PR #72 記録、PR #121 記録の before 側は変えない。base 資産の新射影 SHA-256 は `3fc6dd9696245f5279970a35c3dc9d0f5c1453dd808668aca1ba9ef2c48297e4`。正例 fixture が Git の corpus に入った後の比較 corpus digest は `1ac0f2d12ae701e8bd30956f8ed995ca367315da1e0818d86dc7021389969e57`。
- 正式な受理単位は PR #121 の最終状態 1 件。2026-10-13、山田正輝氏は本会話で revision 26→27、単一シンボルの `SQLA_SELECT`・`SQLA_INSERT`・`SQLA_UPDATE`、PR #121 の未マージ記録の after 側、snapshot と movement_fact・reason の整合更新をプロダクトオーナーとして明示承認した。これを受けて正式台帳の同 PR の after 側を更新した。別の受理記録は追加せず、旧履歴・before 側・既存シンボルの許可は保持した。
- 独立 Codex 敵対レビューは、単一シンボルの最小許可と凍結履歴の差分を確認した。追加許可の過大化を検知する負例、および未知 kind の拒否テストを追加した。一方、既存の内部 token を保存 helper を経由せず実行した場合に self チーム・現役選手検証を迂回できるという P0 を指摘した。これは今回の追加凍結契約改訂の承認範囲外の製品実装修正を要するため、別途報告して判断を待つ。レビューの「revision 27 の承認根拠なし」という指摘は、今回の PO 明示承認をレビューへ渡していなかったためであり、本記録で根拠を同期した。

## ステップ 2 の直接 token P0 追補

- 利用者は P0 修正を指示し、追加の認可契約・計画範囲が必要なら人間承認を求めた。現行 GET API はまだ存在せず、外部入口はステップ 3 の所有。現在の `save_lineup_memory()` は self ロックと `PlayerReadToken` による現役確認を行うが、`tenant_transaction_scope.run()` と `TenantRepositoryBase.execute()` は登録済み token を直接受け、`_prepare_read/insert/update()` はそれらの条件を検査しない。
- 実 DB の再現テストを `backend/tests/db/test_lineup_memory.py` に未コミットで追加した。`scope.run()` の直接 INSERT による同一テナントの opponent チームへの保存、直接 UPDATE による非現役選手への差し替え、直接 READ による opponent 記憶の取得、および `TenantRepositoryBase.execute()` の直接 INSERT による欠損選手の保存の 4 経路が、現行製品コードで期待どおり red。テストは製品コード変更前の証跡として保持する。
- 最小修正案は、登録済み U-M2 token の実行前検証を同一トランザクション内で両実行器から呼ぶこと。既存の self チームロックと選手 ID 限定 read を使い、UPDATE 文の対象 team ID と移行由来行の条件も固定する。`OperationRegistration` と `transaction.py` が承認済み計画の明示 path に無かったため、計画を `in-review` に戻し、追補の敵対レビュー・人間承認まで製品コードは変更しない。既存の凍結台帳は変更しない。
- 追補計画の独立敵対レビュー 1 回目は P0=0、P1=1。P1 は有効な自チーム選手の payload で相手チーム記憶 ID または移行由来行を直接 UPDATE する負例がステップ 2 の合格条件・テスト計画に無いこと。両箇所を明記し、実 DB の再現テストを追加した。現行実装では相手チーム記憶・移行由来行への UPDATE がそれぞれ 1 行成功するため、両負例は red。凍結契約は token 型集合・公開署名・SQLA 許可 API を維持すれば追加改訂不要との暫定判断で、実装後の検査結果を最終判定に用いる。
- 追補計画の独立敵対レビュー 2 回目は P0/P1/P2 すべて 0 件で可決。UPDATE 対象行の合格条件と DB 負例が対応し、両実行器の同一トランザクション内 preflight は実装可能と確認された。レビュー担当はファイルを編集していない。追補は計画書の明示 path と認可実行境界を広げるため、人間の追補承認まで製品コードは変更しない。

- 利用者が 2026-10-13 に P0 追補計画を明示承認した。直接 token と両実行器の検証、対象 UPDATE の team・移行由来条件に限定して製品修正を開始した。
- 製品差分の独立敵対レビュー 1 回目は P0=2、P1=1。JSON 数値の UUID が照合後に数値のまま保存される経路と、選手行をロックしないため在籍変更が照合と保存の間へ割り込める経路が P0。直接 UPDATE の欠損・別チーム、公開実行器の相手 READ/UPDATE 負例不足が P1。JSON 正規化と負例は承認済み範囲で修正し、該当 DB テスト 12 件・Ruff・ty が green。競合 P0 は選手行の厳密な `FOR UPDATE` 許可と凍結 token 型集合の改訂が必要なため、計画へ追加案を記し、認可資産と台帳は人間承認まで変更しない。
- 競合 P0 の追加計画レビュー 1 回目は P0=2、P1=2。選手 ID 順ロックと U-M1 一括在籍変更の入力順 UPDATE のデッドロック、凍結 archive の corpus digest 追随漏れが P0。固定 active bind と拒否形の明文化、二方向の実 DB 同期テストが P1。U-M1 のロック取得順だけを同じ UUID 昇順へ揃え、応答順は維持する限定差分、frozen-archive manifest の digest 1 値、認可形と競合試験を計画へ反映した。U-M1 の専用 worktree は現行 worktree 一覧にない。これらの追加変更はまだ人間未承認。
- 競合 P0 の追加計画レビュー 2 回目は差分可決、P0/P1/P2 すべて 0 件。初回 4 指摘の反映を確認した。製品・認可資産・正式台帳への追加差分は、人間が追加計画と凍結契約の改訂を承認するまで着手しない。
- 2026-10-13、利用者が競合 P0 追加計画を明示承認した。U-M1 専用 worktree は存在せず、GitHub の open PR は #121・#120・#119 のみで U-M1 担当の作業中 PR は無い。別担当の worktree には触れず、本 U-M2 worktree で一括在籍変更の選手行取得順だけを UUID 昇順へ固定し、応答配列は入力順に保った。
- 追加の現役選手行ロック token は tenant・選手 ID・チーム ID・固定 active・非表示でない行の `SELECT id FOR UPDATE` だけ。ロック変種・条件欠落を認可で拒否する。直接 token の実 DB 競合テストは、在籍変更／論理削除が先行する 2 件と保存が先行する 2 件、複数選手の ID 順 1 件を追加し、スタメン DB テスト計 17 件が green。U-M1 境界テスト 30 件、認可契約 145 件、凍結台帳 339 件、archive 29 件、Ruff・ty も green。
- 凍結契約は repository revision 15→16・新 token 型 1 件、生成済み契約定数の追随、PR #121 の単一未マージ記録の after 側・新識別値・subject・movement_fact・reason の更新のみ。before 側と比較元の受理済み prefix は保持した。base-allowlist revision 27・既存許可シンボルは不変。未マージ revision 15 の旧 snapshot は最終受理状態から参照されなくなるため除去し、revision 16 の内容アドレス snapshot だけを追加した。frozen-archive manifest は corpus digest 1 値だけを追随した。`check_tenant_boundary_bypass.py` と archive case runner が green。

## 製品コードの独立レビューと最終 P0 反映

- 製品コードの独立レビュー 2 回目（初回の反映差分＋影響箇所）は P0 1 件・P1 2 件。`bytearray` を直接 token に渡すと事前照合後に値を変更できる問題を、保存 token の JSON を exact `str` に限定して修正した。公開実行器と複数選手の競合試験も増やした。
- 6.3 の自動 P0 例外である 3 回目は P0 限定差分レビューとし、P0 1 件を検出した。`frozen` token でも `object.__setattr__` により照合後に `lineup_json` を別の `str` に差し替えられる。両実行器が同じ元 token から保存 SQL を後で組み立てるため、欠損選手を保存できた。指摘を採用した。
- 最終反映では、両実行器が保存 SQL の束縛値を事前に確定し、事前照合もその同じ束縛値から選手 ID とチーム ID を読む。照合後に元 token を改変しても保存値は変わらない。汎用 token 複製は既存 TB007 検査に抵触するため採用しなかった。直接 INSERT / UPDATE × scope / 公開実行器の 4 経路で照合後の元 token 改変を再現し、保存値が照合済み選手のままであることを実 DB で確認した。
- 競合試験の保存先行側は、SQL 事前準備の順序変更に合わせ、選手行の取得結果が実体化した直後に停止するよう同期点を変更した。在籍変更先行・保存先行の両方向、INSERT / UPDATE、scope / 公開実行器、在籍区分変更 / 論理削除を対象にした実 DB テストは通しで 36 件すべて成功。凍結境界検査、archive 比較 11 件、境界検査 339 件、U-M1 在籍変更境界 10 件、Ruff・ty・format 検査も green。`backend/tests/conftest.py` 差分 0 行。
- **レビュー上限**: 自動枠 3 回は使用済みで、3 回目にも P0 が残った。上記の最終反映は独立レビュー未実施。6.3 に従い、追加 1 回の範囲を「元 token 差し替え P0 の修正差分と両実行器・保存 preflight の影響箇所、P0/P1 判定」として PO 裁定待ち。追加レビューの承認を推定せず、PR #121 は Draft、ステップ 2 は未コミット・未完了、人間逐行確認も未実施とする。

## 6.3 の PO 追加レビュー裁定

- 2026-10-13、本会話の利用者が PO 裁定として**独立レビュー 1 回の追加**を明示承認した。対象は token 差し替え P0 の最終修正差分と、両実行器・保存前照合・SQL 束縛値確定の影響箇所。P0/P1 を判定し、照合値と実保存値の一致、直接 token 実行、照合後の変更による迂回を重点確認する。追加周回は自動で続けない。最終差分・検査結果はステップ 2 コミット・push 前に提示し、PR #121 は Draft、人間逐行確認は未実施のままとする。
- PO 裁定の追加レビュー 1 回を読み取り専用の独立 Codex セッションで実施し、**否決・P0 1 件 / P1 0 件**。元 token の `lineup_json` 文字列を照合後に差し替える前回 P0 は解消した。一方、SQL 束縛値は呼び出し元が保持する UUID と同一参照であり、`object.__setattr__(team_uuid, "int", ...)` により照合後に相手チーム ID へ変更できる。read / insert / update の準備値で再現された。指摘を**採用**し、U-M2 の対象 token 準備時に team ID と行 ID を独立した UUID 値へ固定する修正と、両実行器の read / insert / update について元 UUID の内部変更を再現する実 DB テスト 6 件を追加した。新しい認可契約シンボルや凍結履歴の変更はない。
- この PO 裁定で許可された追加レビューは実施済み。上記採用反映の再レビューを自動で開始しない。レビュー結果を P0 解消認定として扱わず、関連検査後の最終差分をステップ 2 コミット・push 前に人間へ提示する。
- 採用反映後、スタメン記憶の実 PostgreSQL テストは通しで **42 件すべて成功**。当該 6 件は read / insert / update × scope / 公開実行器で元 UUID の内部値をロック後に変更する。backend Ruff・ty・format check、tenant-boundary bypass check は green。認可資産と凍結台帳はこの最終反映では変更していない。独立レビュー応答の原本は `/tmp/um2-p0-code-review-po-extra-output.txt`。

## 6.3 の PO 追加 P0 限定差分レビュー裁定

- 2026-10-13、本会話の利用者が **P0 限定の独立差分レビュー 1 回**を新たに明示承認した。対象は UUID 独立化修正、両実行器の read / insert / update への影響、元 UUID の内部値変更を扱う実 DB 回帰テスト 6 経路。照合・ロック・SQL 実行が同じ確定値を使い、元 token / UUID への共有参照が残らず、新たな P0 を生んでいないことを判定する。確認済み全文は再レビューしない。自動の次周は行わない。
- レビュー前の差分固定値: `git diff --binary -- backend/src/pitchlog/repositories/{lineup_memory,base,transaction,operation_registration}.py backend/tests/db/test_lineup_memory.py | sha256sum` = `0291537b18884165afd94480355ccc06aff3861e82c7713385be4050655e474a`。この対象差分と追加6経路をレビューへ渡す。レビュー中に対象ファイルは変更しない。PR #121 は Draft、ステップ 2 は未コミット・未push、人間逐行確認は未実施。
- 裁定に基づく独立 Codex の P0 限定差分レビューは**可決・P0 0 件**。レビュー担当は指定 5 ファイルの差分 SHA-256 が固定値と一致することを確認した。READ / INSERT / UPDATE の準備時に作る UUID は元 token の UUID と別オブジェクトで、preflight は確定済みの同じ SQL 束縛値からチーム・選手ロックを構成し、両実行器はその値で SQL を実行する、と読み取り専用の再現で確認した。6 経路の DB テストはレビュー担当がコードを確認し、実行は担当者側の 42 件成功を根拠とする。指摘 0 件のため採否・追加反映は無し。レビュー原本は `/tmp/um2-p0-uuid-final-review-output.txt`。自動の次周は行わない。

## 人間逐行確認の連絡

- 2026-10-13、本会話の利用者から、提示済みのステップ 2 最終差分について「逐次チェックしたよ」との連絡を受けた。提示対象は `/tmp/tsk394-step2-final.diff`（追跡済みファイルの差分）と、新規内容アドレス snapshot `a8ab5536a83debe0f383811a0eb0a8441f4728d217b4b358275289abf1e16dae`。確認者自身の対象・範囲・方法を伴う PR 本文の実施記録行は現時点で空欄であり、規約 6.3 の証跡完了として代理記入しない。公開 PR HEAD はローカル最終差分より古く、ステップ 2 コミット・push は利用者の直前の明示指示に従って保留する。

## 最新 develop との照合

- 利用者の指摘を受け、2026-10-13 に `git fetch origin develop` と `git ls-remote origin refs/heads/develop` で最新リモート先端 `9114a5a6` を確認した。U-M2 ブランチ HEAD は `5d5ab477`、共通祖先は `212379b5` で、origin/develop に TSK-479 / PR #122 の 8 コミットが先行する。U-M2 側の既存 4 コミットと未コミット差分の変更パスには、develop 側 27 ファイルとの同一パス重複が無い。新規 migration 0030 と試合区分の認可・seed は U-M2 の所有範囲外。
- `scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` は最新先端を基準に green。develop の repository-contract は revision 14、base-allowlist は revision 26 のままで、PR #121 の既存 before 識別値と一致する。GitHub は PR #121 を `mergeable=true` / `mergeable_state=behind` / Draft と報告した。ローカル最終差分を最新 develop 上で再適用した実 DB・CI 検査は未実施であり、ブランチを rebase / merge していない。コミット・push 保留と、確認済み最終差分の固定を維持する。
- 利用者の再確認依頼後、`origin/develop` は PR #123（U-F13 公開ガイド入口）のマージで `928280e6` へ進んだ。前回先端 `9114a5a6` から 8 コミット・10 ファイル追加だが、全て U-F13 の docs / frontend に限定され、U-M2 の既存コミット・未コミット変更と同一パスの重なりは無い。リモート先端は `git ls-remote` でも `928280e6`、repository-contract は revision 14、base-allowlist は revision 26 のまま。最新 `origin/develop` 基準の tenant-boundary bypass check は green。GitHub の PR #121 は再計算後 `mergeable=true` / `behind` / Draft。ブランチの共通祖先は `212379b5` のままで、最新 develop 上の統合テスト・rebase / merge / commit / push は未実施。

## ステップ 2 の公開と最新 develop 統合の許可

- 2026-10-13、本会話の利用者がコミット前停止を限定解除し、レビュー済み最終差分と新規 snapshot のステップ 2 追補コミット、最新 `origin/develop` の **merge**、前後差分の確認、関連 DB・認可・凍結契約・archive・品質検査、Draft PR #121 への push と本文更新を明示許可した。rebase、先の GET 実装、Draft 解除、PR マージは許可されていない。PR の人間逐行確認欄は未チェックに保つ。

## ステップ 2 統合とステップ 3 の後続範囲

- PR #121 は `ba28cedc2fe1303a6639b690b4a573a2fccb438c` を head とし、CI 全 12 チェック通過後に `edbef663c44b1585e325be859fd1f511951ea09c` で `develop` へマージされた。TSK-394 全体はステップ 2 までの部分充足であり、GET とステップ 4 は未完了。
- 本会話の利用者は、最新 `origin/develop` 起点の後続ブランチ・専用 worktree で**ステップ 3 のみ**を実装し、合格時に別コミットを作ることを指示した。PR 作成・push・マージ、ステップ 4、U-G1 の試合作成・スタメン確定は対象外。基点 `edbef663c44b1585e325be859fd1f511951ea09c`、後続ブランチ `feature/um2-lineup-memory-get`、worktree `/tmp/pitchlog-um2-lineup-memory-step3`。
- 正式な Notion の TSK-394 カードを取得した。担当者プロパティは既存値を維持し、出所 TSK-363 の共通 DoD 以外の追加 DoD がないことを確認。Notion は `進行中` とし、ステップ 2 のマージ・CI・ステップ 3・4 の残余を記録済み。
- GET の経路 1 本は `route-registry.json` / `http-route-matrix.json` と派生 lock・独立 exact-set を動かす。`oracle-seal.lock.json` の入力と `frozen-baselines.json` の `oracle_input` にも影響するため、PR #121 の承認は流用しない。後者の `acceptance` は `unit=pull_request`、`acceptance_id_source=repository_and_pr_number`、`posterior_state=checkout_head` と宣言している。今回は PR 作成が禁止されているため、受理済み履歴を架空の番号で確定しない。変更の人間承認と受理手順を別途確認中。
- 凍結資産を変更しない範囲で、GET・DTO・静的ルータ登録と公開 HTTP の実 DB 試験を作成した。既存 `TeamRecordReadToken` は `kind='opponent'` 限定なので、GET の自チーム確認にはステップ 2 の `_SelfTeamLockToken` を再利用する。対象チームに記憶がなければ 204、他テナント・相手チーム・対象不在は 404。選手は記憶中の ID ごとに当該テナント・チーム・`active`・非表示でない行だけを読み、採用できない枠では元の打順・守備位置だけを残す。実 DB の保存・GET 試験 43 件、API・境界・在籍試験 51 件、Ruff・ty・format・docs-status が green。DB 制約 `uq_team_records_self` はテナントごと自チーム 1 件、`team_records_check` は自チームの非表示を禁止するため、その不可能な状態を試験で生成しない。
- 凍結変更の候補範囲は、論理経路 `ROUTE:RECORD:lineup_memories:read` 1 行、HTTP matrix の対応 1 行、両派生 lock、検査器の独立 exact-set と負例、oracle 入力・seal・関連 digest・7.7 の `oracle_input` 受理履歴。既存 6 行と既存の判定・test owner は保持する。必要なゲートは 6.3 のコア敵対レビューと人間逐行確認、7.7 の新規人間承認・PR 単位の受理 ID・再封印・履歴検査。後続 PR 番号を取得するまでは正式受理記録を確定しない。

## ステップ 3 の凍結改訂と Draft PR 番号の取得

- 2026-10-13、利用者は PR #121 とは別に、GET 経路 1 本と必要最小限の認可凍結資産・派生 lock・oracle・7.7 受理履歴の改訂を承認した。受理 ID のため、計画・作業ログのみの準備コミットの push と Draft PR 作成も承認した。準備コミットは GET 製品コード・テスト・凍結資産を含めず、ステップ 3 完了とは扱わない。PR 番号取得後、実際の前後識別値と検査結果で受理記録を作る。oracle の `human_review_required` は別途人間確認の対象を提示してから進める。
- 計画・作業ログだけの準備コミット `539386cb` を push して [Draft PR #124](https://github.com/masaki1025/pitchlog/pull/124) を作成した。正式受理 ID は `masaki1025/pitchlog#124`。この時点で GET の製品コードは未push、ステップ 3 は未完了。
- 経路 1 行ずつを registry と HTTP matrix に追加し、`--reseal-derived --skip-oracle` で各 lock を導出した。registry lock の件数は 237→238、matrix lock は 55→56。既存行は維持。認可テストは 23,517 件通過後、未再封印の `route-registry.json: oracle input blob が不一致` で期待どおり停止した。検査器は `oracle_commit` の指すコミット内の入力 8 資産 blob も照合するため、変更後の経路資産 4 点を含む中間コミットが必要。利用者は規約 6.1 のステップ単位コミットについて、PR #124 の入力固定用としてこの 4 資産だけの**ローカル中間コミット**を限定承認した。製品コード・検査器・seal・正式受理履歴は混ぜず、ステップ 3 完了や公開とは扱わず、push しない。再封印と正式受理履歴の更新は対象と前後差分を示してから別途人間確認を受ける。
- 入力 8 資産のうち変更する 4 資産の Git blob SHA-1 候補: `route-registry.json` `161091975b90d4b017df24a9ec4dd054701f5be9`→`b91ff23039dd8fb3d2b467e45e849ffa87a72925`、同 lock `fc47f9985f3f550f475611a5b0c1d96f41cfd2ab`→`ddaf95d0acdefaf63654c7e2c687c96f18e834f8`、`http-route-matrix.json` `335390c33e0428ac68b21b53336af6ab073e7a7b`→`219cdc350f8d0a59b0d8ba1d2698184c7c0cf27f`、同 lock `a8af783d35ce464bc907d6189bd7be9d1e38aacd`→`b96542f315cf1aed1db5db4f9a28374fe9a9a43e`。他の入力 4 資産と既存の受理履歴は変更しない。`record_and_aggregate` の独立 exact-set 7 件は green。
- 許可された 4 資産のみをローカル中間コミット `0364f07c219545df416aed2250f2b23a4535c8df` へ固定した。8 入力すべてで `git rev-parse HEAD:<path>` と作業ツリーの `git hash-object <path>` が一致。旧 oracle seal と比べて前項の 4 点だけが変わり、`requirement-claims.json` と lock、`auth-catalog.json` と lock の 4 点は blob 不変。中間コミットは未push、ステップ 3 完了ではない。
- **人間確認待ちの再封印・7.7 受理候補（正式資産は未変更）**: `oracle_commit` と 6 oracle 資産の同値を `cc949c690a7da6d7e719561f9fa02153e1857610`→`0364f07c219545df416aed2250f2b23a4535c8df`、seal の入力 4 blob と sealed 6 canonical digest を追随する。`failure-injection-points.json` の DDL blob 参照と `mcdc-map.json` の mutant map blob 参照も追随する。`frozen-baselines.json` の `oracle_input` 履歴には既存の #95 までを保持し、`acceptance_id=masaki1025/pitchlog#124`、prior=旧 commit、new=中間 commit、`changes=[]`、配置前後同一、`moved=false`、理由=GET 1 経路と派生 lock による入力 blob 変更、承認者・承認日=人間確認結果、の 1 件追記を提案する。候補の seal は検査器の `validate_oracle_seal` で入力 8 blob と 6 canonical digest の照合が green。再封印と正式台帳への追記は、人間確認まで実施しない。
- 2026-10-13、本会話の PO は `/tmp/um2-124-oracle-proposal/REVIEW.md` の候補に限定して、上記の oracle 再封印と PR #124 の 7.7 受理を明示承認した。承認者は本会話で既に識別された山田正輝氏、承認日は本承認発話の日付 2026-10-13 として扱い、提案時に仮置きした値を正式記録の根拠にしない。
- 正式反映前に実装者とは別の Codex CLI セッションで `review adversarial` を 1 回実施した（Claude CLI は以前の利用上限により使用不能、同一会話の利用者が Codex 代替を承認済み）。対象は中間コミットの 4 入力、`REVIEW.md` と提案コピー 10 資産、7.7 記録、GET の認可境界。結果は **P0 0 / P1 1 / P2 0**。P1 は「承認前の提案コピーに `approved_by` / `approved_at` が確定値として入っている」点。**採用**: 正式資産には承認前に反映せず、直前の PO 明示承認・会話中の氏名・当日日付を突合したうえでだけ記入する。指摘は提案値の真正性確認であり、実際の承認値は提案値と一致したため、技術的候補値と変更範囲は不変。レビューは 8 入力・6 canonical digest・2 参照 blob・既存履歴不変を確認し、GET の指定認可境界に追加 P0/P1 なしとした。最終 PR 全文レビューと人間逐行確認は別途必要。
- 承認後、候補コピー 10 資産を正式資産へ反映し、専用フラグ `--reseal-oracle` を実行した。反映後も候補とのバイト一致は 10/10。通常 `check_authz_catalog.py`、`check_frozen_baselines.py --invariants-only`、failure injection / MC/DC の参照検査が green。archive テスト 65 件、保存・GET・関連 API の実 DB/境界テスト 94 件、root と backend の Ruff・ty・format・docs-status が green。
- 認可・履歴テスト群は 25,697 件通過、2 件失敗。atomic claim 用 fixture が新しい製品 route exact-set を持たない点は、当該 atomic 試験内に限って経路集合照合を外す修正で解消し、単独再実行 green。製品 7 経路の独立 exact-set は維持。もう 1 件は `test_normal_validation_never_reseals_a_semantically_valid_drift` がコミット済み HEAD を clone するため、中間コミット時点の旧 checker・旧 seal と新経路入力の不一致で失敗する。ステップ 3 コミット後に再実行する。
- 2 回目の独立 Codex 敵対レビュー（1 回目の指摘反映差分と影響箇所）は **P0 0 / P1 1 / P2 0**。P1 は保存可能な JSON オブジェクト・配列の `fielding_position` が不変化されたまま DTO に渡され、GET が失敗する反例。**採用**: 既存の JSON 不変化境界を維持し、公開応答の直前に守備位置識別値の `Mapping` / `tuple` を再帰的に `dict` / `list` へ戻す。公開 HTTP 実 DB 試験にオブジェクトと配列を加え、GET 試験 1 件、backend Ruff・ty・format green。凍結候補値・受理記録・入力4資産は不変。6.3 の基本2回を使い切ったため追加周回は自動で行わず、最終修正差分の人間逐行確認を残す。
