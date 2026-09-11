# N4 — 削除系統の割り当て

<!-- scripts/generate_orm_acceptance_sheets.py により生成。判定欄と理由欄だけを人間が記入する。 -->

## 対象・範囲・方法

- 対象: data-model.md 11-1 節の削除 4 系統表が挙げる業務オブジェクト
- 範囲: 同表の直接対象と manifest の lifecycle.deletion。その他の物理表は直接割当なし候補として分離する。
- 方法: 4 系統表を表順・対象順に抽出する。続けて manifest 全表を正本節順に直接割当なしの確認候補として並べ、人間が対象を切り分ける。

## 判定区分と適格条件

| 区分 | 適格条件 |
| --- | --- |
| `一致` | 正本側と対応する manifest / 実装側を両方特定できる。片方しか特定できない行は一致にできない。 |
| `差分` | 欠落・余剰・内容不一致のいずれか。未解消のまま完了にできない。 |
| `対象外` | 当該 N の対象・範囲外にある生成候補だけ。対象内の欠落には使えず、理由と典拠（ファイル:節）が必須。 |

完了条件は、未判定 0・未解消の `差分` 0・不適格な `対象外` 0。

## 差分時の是正遷移

`差分` が出たら番号付きの是正ステップを追加する。是正ステップは `core-areas.json` 登録ステップ（現ステップ 29）より前へ挿入し、登録ステップを後ろへ繰り下げる。是正後にシートを再生成し、全行を再度判定する。

## 11-1 節の直接割当

| 対象 | 正本側 | 実装側 | 判定 | 理由と典拠 |
| --- | --- | --- | --- | --- |
| 11-1 対象 01: 試合のみ | data-model.md §11-1 — 軸1=ゴミ箱 | manifest lifecycle.deletion=ゴミ箱 の候補: games |  |  |
| 11-1 対象 02: 選手 | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows, medical_notes |  |  |
| 11-1 対象 03: プレイ行 | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows, medical_notes |  |  |
| 11-1 対象 04: 対戦相手チームレコード | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows, medical_notes |  |  |
| 11-1 対象 05: プレイ 0 件の試合(ゴミ箱を経ず即時) | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows, medical_notes |  |  |
| 11-1 対象 06: テナント(データ全保全) | data-model.md §11-1 — 軸1=無効化 | manifest lifecycle.deletion=無効化 の候補: tenants, rule_sets, game_type_rule_defaults, system_vocabularies, admin_vocabularies, tenant_vocabularies, tenant_auth_subjects, tenant_credentials, admin_credentials, admin_sessions, tenant_tokens |  |  |
| 11-1 対象 07: 語彙(削除不可・無効化のみ) | data-model.md §11-1 — 軸1=無効化 | manifest lifecycle.deletion=無効化 の候補: tenants, rule_sets, game_type_rule_defaults, system_vocabularies, admin_vocabularies, tenant_vocabularies, tenant_auth_subjects, tenant_credentials, admin_credentials, admin_sessions, tenant_tokens |  |  |
| 11-1 対象 08: グループの終了(不可逆) | data-model.md §11-1 — 軸1=終了・離脱 | manifest lifecycle.deletion=終了・離脱 の候補: analysis_groups, group_memberships, group_invitations |  |  |
| 11-1 対象 09: 参加の離脱 | data-model.md §11-1 — 軸1=終了・離脱 | manifest lifecycle.deletion=終了・離脱 の候補: analysis_groups, group_memberships, group_invitations |  |  |

## 正本に直接割当なしの確認候補

| 対象 | 正本側 | 実装側 | 判定 | 理由と典拠 |
| --- | --- | --- | --- | --- |
| 正本に直接割当なし候補: games | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-1, 11-1, 12-3 | manifest games.lifecycle.deletion=ゴミ箱 |  |  |
| 正本に直接割当なし候補: play_rows | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-2, 12-1, 12-3 | manifest play_rows.lifecycle.deletion=非表示 |  |  |
| 正本に直接割当なし候補: play_runners | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-2, 12-3 | manifest play_runners.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: event_slots | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 12-3 | manifest event_slots.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: operation_events | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 5-4, 12-3 | manifest operation_events.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: recording_generations | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 6-1, 12-3 | manifest recording_generations.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: temporary_player_id_mappings | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 12-3 | manifest temporary_player_id_mappings.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: idempotency_ledger | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-4, 12-3 | manifest idempotency_ledger.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: rejected_event_originals | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-4 | manifest rejected_event_originals.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: participation_intervals | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-2, 7-3, 12-3 | manifest participation_intervals.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: evacuated_event_originals | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-4, 12-3 | manifest evacuated_event_originals.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: game_type_rule_defaults | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-5, 10-5 | manifest game_type_rule_defaults.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: rule_sets | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-5, 10-5 | manifest rule_sets.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: tournament_rule_assignments | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-5, 10-5 | manifest tournament_rule_assignments.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: team_records | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-1, 11-1, 12-3 | manifest team_records.lifecycle.deletion=非表示 |  |  |
| 正本に直接割当なし候補: players | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-2, 11-1, 12-3 | manifest players.lifecycle.deletion=非表示 |  |  |
| 正本に直接割当なし候補: game_lineups | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-3, 7-4, 12-3 | manifest game_lineups.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: lineup_memories | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-4, 12-3 | manifest lineup_memories.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: migrated_final_lineups | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-4, 12-3 | manifest migrated_final_lineups.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: tenants | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-1, 11-1, 12-3 | manifest tenants.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: tenant_auth_subjects | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2 | manifest tenant_auth_subjects.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: tenant_credentials | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2 | manifest tenant_credentials.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: admin_credentials | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2-A | manifest admin_credentials.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: admin_sessions | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2-A, 8-3 | manifest admin_sessions.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: tenant_tokens | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-3 | manifest tenant_tokens.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: admin_operation_logs | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-4 | manifest admin_operation_logs.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: medical_note_versions | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-5, 10-1 | manifest medical_note_versions.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: player_merge_events | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-5 | manifest player_merge_events.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: player_move_records | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-5 | manifest player_move_records.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: rate_limit_counters | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-6 | manifest rate_limit_counters.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: group_memberships | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-1, 9-4 | manifest group_memberships.lifecycle.deletion=終了・離脱 |  |  |
| 正本に直接割当なし候補: sharing_grants | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-2, 9-4-B | manifest sharing_grants.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: group_invitations | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-3 | manifest group_invitations.lifecycle.deletion=終了・離脱 |  |  |
| 正本に直接割当なし候補: analysis_groups | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-4-A, 9-4-B | manifest analysis_groups.lifecycle.deletion=終了・離脱 |  |  |
| 正本に直接割当なし候補: medical_notes | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-1, 11-1, 12-3 | manifest medical_notes.lifecycle.deletion=非表示 |  |  |
| 正本に直接割当なし候補: pdf_export_records | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-2 | manifest pdf_export_records.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: admin_vocabularies | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-3, 11-1 | manifest admin_vocabularies.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: system_vocabularies | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-3, 11-1 | manifest system_vocabularies.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: tenant_vocabularies | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-3, 11-1 | manifest tenant_vocabularies.lifecycle.deletion=無効化 |  |  |
| 正本に直接割当なし候補: system_settings | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-4, 11-2 | manifest system_settings.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: migration_quarantine | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6, 12-3 | manifest migration_quarantine.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: migration_resolution_reports | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6 | manifest migration_resolution_reports.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: migration_runs | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6, 12-3 | manifest migration_runs.lifecycle.deletion=対象外 |  |  |
| 正本に直接割当なし候補: migration_warning_reports | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6, 12-3 | manifest migration_warning_reports.lifecycle.deletion=親に従う |  |  |
| 正本に直接割当なし候補: invalidation_intents | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §11-2 | manifest invalidation_intents.lifecycle.deletion=対象外 |  |  |
