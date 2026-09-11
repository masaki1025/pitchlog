# N1 — 表の全数性

<!-- scripts/generate_orm_acceptance_sheets.py により生成。判定欄と理由欄だけを人間が記入する。 -->

## 対象・範囲・方法

- 対象: data-model.md の 5〜12 章の全見出し
- 範囲: 表を定義している記述の全数。表を定義しない見出しも対象外候補として残す。
- 方法: 見出しを文書順に機械抽出し、manifest の source_sections から表候補を並べて人間が判定する。

## 判定区分と適格条件

| 区分 | 適格条件 |
| --- | --- |
| `一致` | 正本側と対応する manifest / 実装側を両方特定できる。片方しか特定できない行は一致にできない。 |
| `差分` | 欠落・余剰・内容不一致のいずれか。未解消のまま完了にできない。 |
| `対象外` | 当該 N の対象・範囲外にある生成候補だけ。対象内の欠落には使えず、理由と典拠（ファイル:節）が必須。 |

完了条件は、未判定 0・未解消の `差分` 0・不適格な `対象外` 0。

## 差分時の是正遷移

`差分` が出たら番号付きの是正ステップを追加する。是正ステップは `core-areas.json` 登録ステップ（現ステップ 29）より前へ挿入し、登録ステップを後ろへ繰り下げる。是正後にシートを再生成し、全行を再度判定する。

## 突合行（正本の文書順）

| 対象 | 正本側 | 実装側 | 判定 | 理由と典拠 |
| --- | --- | --- | --- | --- |
| 見出し 001: 5. 試合・毎球データ・操作イベント(ブロック 1 ①) | data-model.md §5 | manifest tables: games, event_slots, operation_events, play_rows, play_runners, temporary_player_id_mappings, idempotency_ledger, rejected_event_originals, recording_generations |  |  |
| 見出し 002: 5-1. 試合(FR-001・4.0-1) | data-model.md §5-1 | manifest tables: games |  |  |
| 見出し 003: 5-2. 毎球データ = プレイ行(投影。FR-002 / 003 / 004) | data-model.md §5-2 | manifest tables: play_rows, play_runners |  |  |
| 見出し 004: 5-3. 操作イベント(正本。FR-012・3 章用語) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 005: 識別子と一意性の物理写像(M01〜M04・M07・M08・M17・WAIT-03) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 006: 一意範囲・連続性・適用水位・楽観ロックの物理写像(C09〜C12・C14・WAIT-01) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 007: 参加区分と D2 の有無(全 12 種 — M02 の NULL 性の根拠) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 008: D2 の局所再採番と一意性の両立(O2 の構造側 — 確定ゲート 2 周目 P1-3) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 009: 同位置が観測されたときの扱い(O4 の構造側) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 010: イベントスロット(M07 の参照先 — V10 の FK を成立させる実体) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 011: D2 の数値型(WAIT-03) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 012: D2 に不変前提の索引を張らない(M03 — 索引原則へ) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 013: 変更イベント(参加区分 #10〜#12)— 確定済み記録の訂正の正本(C06・M06) | data-model.md §5-3 | manifest tables: event_slots, operation_events, temporary_player_id_mappings, recording_generations |  |  |
| 見出し 014: 5-4. 原子境界と結果保持(M05・M09・M10・M15・M18・M20・WAIT-06・WAIT-08) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 015: P1〜P5 と T1〜T9 の対応(M05) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 016: D5 台帳は全経路唯一の一意性の所在(C09 の物理的な帰結) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 017: 拒否原本を受理済み行と混ぜない(M10) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 018: 保存済み結果の再掲(M18) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 019: 世代・引き継ぎ・フェンスの永続化(M15) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 020: クラッシュ注入点が定義できる配置(WAIT-06 = 同 11-4 の U-8 構造側 / M20) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 021: 9-2 境界表 17 行の写像先(WAIT-08 の全数対応) | data-model.md §5-4 | manifest tables: operation_events, idempotency_ledger, rejected_event_originals |  |  |
| 見出し 022: 5-5. 本節の禁止事項照合 | data-model.md §5-5 | manifest tables: 該当候補なし |  |  |
| 見出し 023: 6. 記録権・交代・状態補正・退避・適用規則スナップショット(ブロック 1 ②) | data-model.md §6 | manifest tables: participation_intervals, rule_sets, game_type_rule_defaults, tournament_rule_assignments, evacuated_event_originals, recording_generations |  |  |
| 見出し 024: 6-1. 記録権は「世代」を行として持つ(FR-013) | data-model.md §6-1 | manifest tables: recording_generations |  |  |
| 見出し 025: 6-2. 交代はイベントとして永続化し、投影として「出場区間」を持つ(FR-011) | data-model.md §6-2 | manifest tables: participation_intervals |  |  |
| 見出し 026: 6-3. 状態補正は差分を持つイベント(FR-040・Should) | data-model.md §6-3 | manifest tables: 該当候補なし |  |  |
| 見出し 027: 6-4. 退避イベントは原本を残し、取り込みは新規行として採番する(FR-013・FR-035) | data-model.md §6-4 | manifest tables: evacuated_event_originals |  |  |
| 見出し 028: 退避と復元の構造側(C07・C15・M11〜M13・WAIT-02・WAIT-04) | data-model.md §6-4 | manifest tables: evacuated_event_originals |  |  |
| 見出し 029: 6-5. 規則セットと適用規則スナップショット(FR-014・付録F) | data-model.md §6-5 | manifest tables: rule_sets, game_type_rule_defaults, tournament_rule_assignments |  |  |
| 見出し 030: 6-6. 本節の禁止事項照合 | data-model.md §6-6 | manifest tables: 該当候補なし |  |  |
| 見出し 031: 7. チーム・選手・在籍区分・スタメン・対戦相手チーム(ブロック 2 / 論点 5・8) | data-model.md §7 | manifest tables: team_records, players, lineup_memories, game_lineups, participation_intervals, migrated_final_lineups |  |  |
| 見出し 032: 7-1. 「チーム」を 2 つの表に分ける(論点 5) | data-model.md §7-1 | manifest tables: team_records |  |  |
| 見出し 033: 7-2. 選手(FR-015) | data-model.md §7-2 | manifest tables: players |  |  |
| 見出し 034: 7-3. 背番号の当時値は「試合参加時点のスナップショット」で持つ(論点 8) | data-model.md §7-3 | manifest tables: game_lineups, participation_intervals |  |  |
| 見出し 035: 7-4. スタメン(FR-016・FR-001) | data-model.md §7-4 | manifest tables: lineup_memories, game_lineups, migrated_final_lineups |  |  |
| 見出し 036: 7-5. 本節の禁止事項照合 | data-model.md §7-5 | manifest tables: 該当候補なし |  |  |
| 見出し 037: 8. テナント・認証・トークン・操作ログ・統合の巻き戻し(ブロック 7) | data-model.md §8 | manifest tables: tenants, medical_note_versions, tenant_auth_subjects, tenant_credentials, admin_credentials, admin_sessions, tenant_tokens, admin_operation_logs, player_merge_events, player_move_records, rate_limit_counters |  |  |
| 見出し 038: 8-1. テナント(FR-035) | data-model.md §8-1 | manifest tables: tenants |  |  |
| 見出し 039: 8-2. 認証情報(NFR-011) | data-model.md §8-2 | manifest tables: tenant_auth_subjects, tenant_credentials |  |  |
| 見出し 040: 8-2-A. システム管理者の資格情報はテナントと別系統にする(敵対レビュー P1-5 の是正) | data-model.md §8-2-A | manifest tables: admin_credentials, admin_sessions |  |  |
| 見出し 041: 8-2-B. 管理者から業務データへ到達する経路を論理モデルとして定める(敵対レビュー P1-4 の是正) | data-model.md §8-2-B | manifest tables: 該当候補なし |  |  |
| 見出し 042: 8-3. トークン・セッション(NFR-011・FR-036) | data-model.md §8-3 | manifest tables: admin_sessions, tenant_tokens |  |  |
| 見出し 043: 8-4. 管理者操作ログ(必須範囲は破壊的操作 = Must / 全操作の網羅は Should) | data-model.md §8-4 | manifest tables: admin_operation_logs |  |  |
| 見出し 044: 8-5. 選手統合の巻き戻し情報(FR-035) | data-model.md §8-5 | manifest tables: medical_note_versions, player_merge_events, player_move_records |  |  |
| 見出し 045: 8-6. レート制限カウンタ(FR-033・7.1) | data-model.md §8-6 | manifest tables: rate_limit_counters |  |  |
| 見出し 046: 8-7. 本節の禁止事項照合 | data-model.md §8-7 | manifest tables: 該当候補なし |  |  |
| 見出し 047: 9. 共同分析グループ・参加・付与・招待(ブロック 4 / 論点 6) | data-model.md §9 | manifest tables: analysis_groups, group_memberships, sharing_grants, group_invitations |  |  |
| 見出し 048: 9-1. 参加は履歴として複数行持ち、active な行を 1 件に絞る(論点 6) | data-model.md §9-1 | manifest tables: group_memberships |  |  |
| 見出し 049: 9-2. 付与は「参加」に紐づける | data-model.md §9-2 | manifest tables: sharing_grants |  |  |
| 見出し 050: 9-3. 招待(FR-041) | data-model.md §9-3 | manifest tables: group_invitations |  |  |
| 見出し 051: 9-4. 不変条件: 実効 admin が 1 名以上 | data-model.md §9-4 | manifest tables: group_memberships |  |  |
| 見出し 052: 9-4-B. グループの生成は初期 admin と同一トランザクションで行う(3 周目 P1-3 の是正) | data-model.md §9-4-B | manifest tables: analysis_groups, sharing_grants |  |  |
| 見出し 053: 9-4-A. 唯一の admin の無効化はグループを不可逆終了させる(敵対レビュー P1-4 の是正) | data-model.md §9-4-A | manifest tables: analysis_groups |  |  |
| 見出し 054: 9-5. 共有集計の出力に関する制約(データモデルに掛かるもの) | data-model.md §9-5 | manifest tables: 該当候補なし |  |  |
| 見出し 055: 9-6. 本節の禁止事項照合 | data-model.md §9-6 | manifest tables: 該当候補なし |  |  |
| 見出し 056: 10. カルテ・PDF 出力実績・語彙マスタ・設定値・規則セット・隔離領域・移行レポート(ブロック 5・8) | data-model.md §10 | manifest tables: rule_sets, game_type_rule_defaults, tournament_rule_assignments, medical_notes, medical_note_versions, pdf_export_records, system_vocabularies, admin_vocabularies, tenant_vocabularies, system_settings, migration_quarantine, migration_runs, migration_resolution_reports, migration_warning_reports |  |  |
| 見出し 057: 10-1. カルテ所見と変更履歴(FR-028) | data-model.md §10-1 | manifest tables: medical_notes, medical_note_versions |  |  |
| 見出し 058: 10-2. PDF 出力実績(FR-029) | data-model.md §10-2 | manifest tables: pdf_export_records |  |  |
| 見出し 059: 10-3. 語彙マスタ(4.0-3・FR-037) | data-model.md §10-3 | manifest tables: system_vocabularies, admin_vocabularies, tenant_vocabularies |  |  |
| 見出し 060: 10-4. システム設定値(FR-037・付録C) | data-model.md §10-4 | manifest tables: system_settings |  |  |
| 見出し 061: 10-5. 規則セット(FR-014・付録F) | data-model.md §10-5 | manifest tables: rule_sets, game_type_rule_defaults, tournament_rule_assignments |  |  |
| 見出し 062: 10-6. 隔離領域と移行レポート(FR-038) | data-model.md §10-6 | manifest tables: migration_quarantine, migration_runs, migration_resolution_reports, migration_warning_reports |  |  |
| 見出し 063: 10-7. 本節の禁止事項照合 | data-model.md §10-7 | manifest tables: 該当候補なし |  |  |
| 見出し 064: 11. 削除の 4 系統とキャッシュ無効化契約・索引設計の原則(論点 7・10) | data-model.md §11 | manifest tables: tenants, team_records, players, games, medical_notes, system_vocabularies, admin_vocabularies, tenant_vocabularies, system_settings, invalidation_intents |  |  |
| 見出し 065: 11-1. 削除は統一せず 4 系統を別のライフサイクルとして持つ(論点 7) | data-model.md §11-1 | manifest tables: tenants, team_records, players, games, medical_notes, system_vocabularies, admin_vocabularies, tenant_vocabularies |  |  |
| 見出し 066: 11-2. キャッシュ無効化契約(論点 10 — 事前集計の採否によらず無条件) | data-model.md §11-2 | manifest tables: system_settings, invalidation_intents |  |  |
| 見出し 067: 無効化の波及先(本書の定義はここだけ — 1-1 節の定義の所在表) | data-model.md §11-2 | manifest tables: system_settings, invalidation_intents |  |  |
| 見出し 068: 無効化の発火条件は同期プロトコル設計が正(B01・WAIT-07) | data-model.md §11-2 | manifest tables: system_settings, invalidation_intents |  |  |
| 見出し 069: 物理的な無効化先(B02) | data-model.md §11-2 | manifest tables: system_settings, invalidation_intents |  |  |
| 見出し 070: 無効化意図の永続化(B03・B04) | data-model.md §11-2 | manifest tables: system_settings, invalidation_intents |  |  |
| 見出し 071: 事前集計を持たない場合の契約(B05) | data-model.md §11-2 | manifest tables: system_settings, invalidation_intents |  |  |
| 見出し 072: 11-3. 索引設計の原則(論点 20 は具体形を (B) へ送るため、原則のみ) | data-model.md §11-3 | manifest tables: 該当候補なし |  |  |
| 見出し 073: 11-4. 本節の禁止事項照合 | data-model.md §11-4 | manifest tables: 該当候補なし |  |  |
| 見出し 074: 12. 88 列の行き先・サイドカー境界・マイグレーション方針・FR 全数対応表(論点 11) | data-model.md §12 | manifest tables: tenants, team_records, players, games, lineup_memories, game_lineups, participation_intervals, event_slots, operation_events, play_rows, play_runners, temporary_player_id_mappings, idempotency_ledger, evacuated_event_originals, recording_generations, medical_notes, migration_quarantine, migrated_final_lineups, migration_runs, migration_warning_reports |  |  |
| 見出し 075: 12-1. 88 列 → 新スキーマの行き先(全 88 列) | data-model.md §12-1 | manifest tables: play_rows |  |  |
| 見出し 076: 12-2. サイドカーの境界(FR-031・付録D-3) | data-model.md §12-2 | manifest tables: 該当候補なし |  |  |
| 見出し 077: 12-3. 移行が要求する構造 | data-model.md §12-3 | manifest tables: tenants, team_records, players, games, lineup_memories, game_lineups, participation_intervals, event_slots, operation_events, play_rows, play_runners, temporary_player_id_mappings, idempotency_ledger, evacuated_event_originals, recording_generations, medical_notes, migration_quarantine, migrated_final_lineups, migration_runs, migration_warning_reports |  |  |
| 見出し 078: 移行バッチの退役(本書の定義はここだけ — 1-1 節の定義の所在表) | data-model.md §12-3 | manifest tables: tenants, team_records, players, games, lineup_memories, game_lineups, participation_intervals, event_slots, operation_events, play_rows, play_runners, temporary_player_id_mappings, idempotency_ledger, evacuated_event_originals, recording_generations, medical_notes, migration_quarantine, migrated_final_lineups, migration_runs, migration_warning_reports |  |  |
| 見出し 079: 移行元の最終オーダーの保全先(裁定 A-1 — 2026-09-08・山田正輝) | data-model.md §12-3 | manifest tables: tenants, team_records, players, games, lineup_memories, game_lineups, participation_intervals, event_slots, operation_events, play_rows, play_runners, temporary_player_id_mappings, idempotency_ledger, evacuated_event_originals, recording_generations, medical_notes, migration_quarantine, migrated_final_lineups, migration_runs, migration_warning_reports |  |  |
| 見出し 080: 12-4. マイグレーション方針(方針 — 依存追加・models・migration の実装は TSK-343) | data-model.md §12-4 | manifest tables: 該当候補なし |  |  |
| 見出し 081: 本スキーマの初回 migration は non-serving である | data-model.md §12-4 | manifest tables: 該当候補なし |  |  |
| 見出し 082: 越境テスト再実行ゲート | data-model.md §12-4 | manifest tables: 該当候補なし |  |  |
| 見出し 083: 12-5. FR-001〜042 の全数対応(取りこぼし 0 件) | data-model.md §12-5 | manifest tables: 該当候補なし |  |  |
| 見出し 084: 12-6. 要件由来の写像・裁定の記録・申し送り | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 085: 要件に明示がなく、裁定で決めた事項(RQ-01〜RQ-09) | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 086: NFR-018 の境界(裁定 A-4 = RQ-09 の判定と理由) | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 087: 論点表に無いが決めた事項 | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 088: 要件書 6.1 の表を超えている実体(改訂は提案しない) | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 089: 同期プロトコル設計が判定を送った禁止事項(SP-01〜SP-06) | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 090: 残余リスク(本書が塞がないもの) | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 091: 次のタスクへの申し送り | data-model.md §12-6 | manifest tables: 該当候補なし |  |  |
| 見出し 092: 12-7. 起草時の敵対レビューで収束しなかった 3 領域(受け取り先を明示する) | data-model.md §12-7 | manifest tables: 該当候補なし |  |  |
| 見出し 093: (1) 認可機構の物理構成 — 受け取り先: 実機確定タスク(実機検証を伴う) | data-model.md §12-7 | manifest tables: 該当候補なし |  |  |
| 見出し 094: (2) イベントの順序 — 解消済み(受け取り先: 同期プロトコル設計 — v0.3 で approved) | data-model.md §12-7 | manifest tables: 該当候補なし |  |  |
| 見出し 095: (3) 移行のファンアウト — 受け取り先: 移行仕様タスク | data-model.md §12-7 | manifest tables: 該当候補なし |  |  |
| 見出し 096: 12-8. 射程宣言(設計書 7.3-7) | data-model.md §12-8 | manifest tables: 該当候補なし |  |  |
| 見出し 097: 本書で確定する範囲 | data-model.md §12-8 | manifest tables: 該当候補なし |  |  |
| 見出し 098: 実装時に確定する範囲(受け取り先を明示する) | data-model.md §12-8 | manifest tables: 該当候補なし |  |  |
| 見出し 099: 本版で閉じきらなかったもの(確定ゲートの打ち切りに伴う申し送り) | data-model.md §12-8 | manifest tables: 該当候補なし |  |  |
| 見出し 100: 本宣言が確定しないことの明示 | data-model.md §12-8 | manifest tables: 該当候補なし |  |  |
