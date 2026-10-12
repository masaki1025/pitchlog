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
