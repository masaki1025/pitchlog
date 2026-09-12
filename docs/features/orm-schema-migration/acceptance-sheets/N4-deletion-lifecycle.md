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
| 11-1 対象 01: 試合のみ | data-model.md §11-1 — 軸1=ゴミ箱 | manifest lifecycle.deletion=ゴミ箱 の候補: games | 一致 | 正本 軸1=ゴミ箱。`games`.lifecycle.deletion=ゴミ箱、状態列 `trashed_at` |
| 11-1 対象 02: 選手 | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows | 一致 | 正本 軸1=非表示。`players`.lifecycle.deletion=非表示、状態列 `hidden_at` |
| 11-1 対象 03: プレイ行 | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows | 一致 | 正本 軸1=非表示。`play_rows`.lifecycle.deletion=非表示、状態列 `hidden_at` |
| 11-1 対象 04: 対戦相手チームレコード | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows | 一致 | 正本 軸1=非表示。`team_records`.lifecycle.deletion=非表示、状態列 `hidden_at` |
| 11-1 対象 05: プレイ 0 件の試合(ゴミ箱を経ず即時) | data-model.md §11-1 — 軸1=非表示 | manifest lifecycle.deletion=非表示 の候補: team_records, players, play_rows | 一致 | 正本 軸1=非表示。§5-1 状態欄(:692)が試合に「ゴミ箱 / 非表示」の両状態を定め、`games` は `status` CHECK に 'hidden'・`hidden_at` 列を持つ。軸 1 は design.md 3-5 節により表単位で主系統(ゴミ箱)を持ち、行単位の非表示経路は状態列で表す data-model.md:5-1,11-1 |
| 11-1 対象 06: テナント(データ全保全) | data-model.md §11-1 — 軸1=無効化 | manifest lifecycle.deletion=無効化 の候補: tenants, system_vocabularies, admin_vocabularies, tenant_vocabularies | 一致 | 正本 軸1=無効化。`tenants`.lifecycle.deletion=無効化、状態列 `enabled`/`disabled_at` |
| 11-1 対象 07: 語彙(削除不可・無効化のみ) | data-model.md §11-1 — 軸1=無効化 | manifest lifecycle.deletion=無効化 の候補: tenants, system_vocabularies, admin_vocabularies, tenant_vocabularies | 一致 | 正本 軸1=無効化。`system_vocabularies`/`admin_vocabularies`/`tenant_vocabularies` の 3 表すべて lifecycle.deletion=無効化、状態列 `disabled` |
| 11-1 対象 08: グループの終了(不可逆) | data-model.md §11-1 — 軸1=終了・離脱 | manifest lifecycle.deletion=終了・離脱 の候補: analysis_groups, group_memberships, group_invitations | 一致 | 正本 軸1=終了・離脱。`analysis_groups`.lifecycle.deletion=終了・離脱、状態列 `status`/`terminated_at`/`termination_reason` |
| 11-1 対象 09: 参加の離脱 | data-model.md §11-1 — 軸1=終了・離脱 | manifest lifecycle.deletion=終了・離脱 の候補: analysis_groups, group_memberships, group_invitations | 一致 | 正本 軸1=終了・離脱。`group_memberships`.lifecycle.deletion=終了・離脱、状態列 `left_at` |

## 正本に直接割当なしの確認候補

| 対象 | 正本側 | 実装側 | 判定 | 理由と典拠 |
| --- | --- | --- | --- | --- |
| 正本に直接割当なし候補: games | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-1, 11-1, 12-3 | manifest games.lifecycle.deletion=ゴミ箱 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 01 試合のみ)。軸1=`ゴミ箱` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: play_rows | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-2, 12-1, 12-3 | manifest play_rows.lifecycle.deletion=非表示 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 03 プレイ行)。軸1=`非表示` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: play_runners | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-2, 12-3 | manifest play_runners.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `play_rows`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:5-2 |
| 正本に直接割当なし候補: event_slots | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 12-3 | manifest event_slots.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `games`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:5-3 |
| 正本に直接割当なし候補: operation_events | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 5-4, 12-3 | manifest operation_events.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:5-3 |
| 正本に直接割当なし候補: recording_generations | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 6-1, 12-3 | manifest recording_generations.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:5-3 |
| 正本に直接割当なし候補: temporary_player_id_mappings | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-3, 12-3 | manifest temporary_player_id_mappings.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:5-3 |
| 正本に直接割当なし候補: idempotency_ledger | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-4, 12-3 | manifest idempotency_ledger.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:5-4 |
| 正本に直接割当なし候補: rejected_event_originals | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §5-4 | manifest rejected_event_originals.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:5-4 |
| 正本に直接割当なし候補: participation_intervals | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-2, 7-3, 12-3 | manifest participation_intervals.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `games`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:6-2 |
| 正本に直接割当なし候補: evacuated_event_originals | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-4, 12-3 | manifest evacuated_event_originals.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:6-4 |
| 正本に直接割当なし候補: game_type_rule_defaults | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-5, 10-5 | manifest game_type_rule_defaults.lifecycle.deletion=対象外 | 一致 | 正本 §6-5・§10-5・FR-014 に削除・無効化の記述がなく、状態列も持たない。manifest `game_type_rule_defaults.lifecycle.deletion=対象外` と対応する data-model.md:6-5,10-5,11-1 |
| 正本に直接割当なし候補: rule_sets | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-5, 10-5 | manifest rule_sets.lifecycle.deletion=対象外 | 一致 | 正本 §6-5・§10-5・FR-014 に削除・無効化の記述がなく、状態列も持たない。manifest `rule_sets.lifecycle.deletion=対象外` と対応する data-model.md:6-5,10-5,11-1 |
| 正本に直接割当なし候補: tournament_rule_assignments | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §6-5, 10-5 | manifest tournament_rule_assignments.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `tenant_vocabularies`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:6-5 |
| 正本に直接割当なし候補: team_records | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-1, 11-1, 12-3 | manifest team_records.lifecycle.deletion=非表示 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 04 対戦相手チームレコード)。軸1=`非表示` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: players | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-2, 11-1, 12-3 | manifest players.lifecycle.deletion=非表示 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 02 選手)。軸1=`非表示` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: game_lineups | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-3, 7-4, 12-3 | manifest game_lineups.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `games`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:7-3 |
| 正本に直接割当なし候補: lineup_memories | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-4, 12-3 | manifest lineup_memories.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `team_records`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:7-4 |
| 正本に直接割当なし候補: migrated_final_lineups | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §7-4, 12-3 | manifest migrated_final_lineups.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `games`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:7-4 |
| 正本に直接割当なし候補: tenants | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-1, 11-1, 12-3 | manifest tenants.lifecycle.deletion=無効化 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 06 テナント)。軸1=`無効化` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: tenant_auth_subjects | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2 | manifest tenant_auth_subjects.lifecycle.deletion=親に従う | 一致 | 正本 §8-2 の認証主体はテナントに属し、自前の無効化状態を持たない。manifest は `親に従う` で、`tenant_id` から `tenants` への FK を持つ data-model.md:8-2,11-1 |
| 正本に直接割当なし候補: tenant_credentials | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2 | manifest tenant_credentials.lifecycle.deletion=親に従う | 一致 | 正本 §8-2 の `generation` はトークン失効機構であり削除状態ではない。manifest は `親に従う` で、認証主体を経由して `tenants` に閉じる data-model.md:8-2,11-1 |
| 正本に直接割当なし候補: admin_credentials | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2-A | manifest admin_credentials.lifecycle.deletion=対象外 | 一致 | 正本 §8-2-A は管理者をテナントと別系統に置き、自前の無効化状態も従属する削除親も定めない。manifest `admin_credentials.lifecycle.deletion=対象外` と対応する data-model.md:8-2-A,11-1 |
| 正本に直接割当なし候補: admin_sessions | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-2-A, 8-3 | manifest admin_sessions.lifecycle.deletion=対象外 | 一致 | 正本 §8-2-A は管理者セッションをテナントと別系統に置き、自前の削除状態を定めない。manifest `admin_sessions.lifecycle.deletion=対象外` と対応する data-model.md:8-2-A,11-1 |
| 正本に直接割当なし候補: tenant_tokens | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-3 | manifest tenant_tokens.lifecycle.deletion=親に従う | 一致 | 正本 §8-3 は全トークン行を UPDATE で失効させる案を却下し、検証時のテナント有効性確認を採る。manifest は `親に従う` で、`tenant_id` から `tenants` への FK を持つ data-model.md:8-1,8-3,11-1 |
| 正本に直接割当なし候補: admin_operation_logs | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-4 | manifest admin_operation_logs.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:8-4 |
| 正本に直接割当なし候補: medical_note_versions | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-5, 10-1 | manifest medical_note_versions.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `medical_notes`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:8-5 |
| 正本に直接割当なし候補: player_merge_events | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-5 | manifest player_merge_events.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:8-5 |
| 正本に直接割当なし候補: player_move_records | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-5 | manifest player_move_records.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `player_merge_events`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:8-5 |
| 正本に直接割当なし候補: rate_limit_counters | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §8-6 | manifest rate_limit_counters.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:8-6 |
| 正本に直接割当なし候補: group_memberships | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-1, 9-4 | manifest group_memberships.lifecycle.deletion=終了・離脱 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 09 参加の離脱)。軸1=`終了・離脱` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: sharing_grants | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-2, 9-4-B | manifest sharing_grants.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `group_memberships`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:9-2 |
| 正本に直接割当なし候補: group_invitations | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-3 | manifest group_invitations.lifecycle.deletion=終了・離脱 | 一致 | §11-1 終了・離脱行の認可効果欄「未消費の招待がすべて無効」+ §9-3(:1786)「終了時に招待の状態を一括で失効させる(または導出する)」— 正本がグループ終了で招待行の `status` を動かすと明記し、表は `status`(unconsumed/consumed/revoked)を持つ。`親に従う` も適格だが是正を要しない(PO 裁定 2026-09-12・山田正輝) data-model.md:9-3,11-1 |
| 正本に直接割当なし候補: analysis_groups | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §9-4-A, 9-4-B | manifest analysis_groups.lifecycle.deletion=終了・離脱 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 08 グループの終了)。軸1=`終了・離脱` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: medical_notes | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-1, 11-1, 12-3 | manifest medical_notes.lifecycle.deletion=親に従う | 一致 | 正本 §11-1 の非表示対象4種に所見はなく、§10-1 は選手に属する所見を定める。manifest は `親に従う` で `players` への複合 FK を持ち、自前の `hidden_at` を持たない data-model.md:10-1,11-1 |
| 正本に直接割当なし候補: pdf_export_records | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-2 | manifest pdf_export_records.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:10-2 |
| 正本に直接割当なし候補: admin_vocabularies | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-3, 11-1 | manifest admin_vocabularies.lifecycle.deletion=無効化 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 07 語彙)。軸1=`無効化` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: system_vocabularies | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-3, 11-1 | manifest system_vocabularies.lifecycle.deletion=無効化 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 07 語彙)。軸1=`無効化` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: tenant_vocabularies | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-3, 11-1 | manifest tenant_vocabularies.lifecycle.deletion=無効化 | 一致 | 11-1 節の 4 系統表に直接現れる(対象 07 語彙)。軸1=`無効化` が正本と一致 data-model.md:11-1 |
| 正本に直接割当なし候補: system_settings | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-4, 11-2 | manifest system_settings.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:10-4 |
| 正本に直接割当なし候補: migration_quarantine | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6, 12-3 | manifest migration_quarantine.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:10-6 |
| 正本に直接割当なし候補: migration_resolution_reports | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6 | manifest migration_resolution_reports.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `migration_runs`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:10-6 |
| 正本に直接割当なし候補: migration_runs | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6, 12-3 | manifest migration_runs.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:10-6 |
| 正本に直接割当なし候補: migration_warning_reports | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §10-6, 12-3 | manifest migration_warning_reports.lifecycle.deletion=親に従う | 一致 | 正本 11-1 節に直接割当が無く、manifest が `親に従う` を宣言している。親は `migration_runs`(主 FK 先)。design.md 3-4 節が `親に従う` を「親オブジェクトの系統に従う投影・付随表」と定義する。両側を特定できる data-model.md:10-6 |
| 正本に直接割当なし候補: invalidation_intents | data-model.md §11-1 の直接割当有無を人間確認; 個別典拠候補 §11-2 | manifest invalidation_intents.lifecycle.deletion=対象外 | 一致 | 正本 11-1 節に直接割当が無く、manifest が `対象外` を宣言している。業務オブジェクトの削除系統を持たない表であり、design.md 3-4 節の定義と一致する。定義節は data-model.md:11-2 |
