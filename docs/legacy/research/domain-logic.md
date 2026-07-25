# 調査レポート: domain-logic

## 要約

domain/配下12モジュールはすべてStreamlit非依存の純粋関数群であり、st.session_stateへの参照はゼロ（grep検証済み）。ただし中核のgame_state.py（update_list）とscoreboard.pyは「88列フラットリスト+config.IDX」「16要素スコアリスト」というレガシーデータ形式に強く結合しており、FastAPIバックエンドならconfig.pyごと持ち込めばそのまま動くが、構造化モデル（Pydantic/TypeScript）へ移すには変換層または移植が必要。runner_advancement/game_end_rules/scoring_rules/out_statuses/batting_results等8モジュールはデータ形式にも依存しない純粋ロジックで「そのまま再利用可」。テストは標準ライブラリunittestでドメイン直撃が約102本あり、素のPython 3.14で95本のパスを実機確認した（カバレッジ計測設定はなし、game_end_rulesの専用テストは欠落し間接テストのみ）。TypeScriptフロントへ載せる場合は全モジュール移植（書き直し）になるが、全関数が純粋なため既存テストをテストベクタとして機械的に移植可能。

---

# Tsukuba PSS domain/ 層 解剖レポート（新アーキテクチャ再利用性判定）

## 0. 結論サマリ

- **Streamlit依存: 全12モジュールでゼロ**。`import streamlit` / `st.session_state` はdomain/配下に一切存在しない（grep検証済み）。docstringにも "Pure game-state transitions" と明記され、意図的にUI層から分離されている。
- **真の結合はデータ形式**: 中核の `game_state.py` は「1プレイ=88列のフラットPythonリスト + `config.IDX`（列名→添字の定数オブジェクト）」に全面依存。`scoreboard.py` は「16要素リスト（12イニング+H/E/K/BB、未消化回は空文字`""`）」に依存。ここが再利用判定の分水嶺。
- **Pythonバックエンド（FastAPI）なら**: `domain/` + `config.py`（88列定義部分のみ）を丸ごと持ち込めば**無改修で動く**。外部依存は `pitching_innings.py` のpandasのみ。
- **TypeScriptフロントなら**: 全モジュール移植（=書き直し）だが、全関数が純粋・決定的なので既存ユニットテスト（約100本）をテストベクタ化して等価移植できる。

## 1. 全体アーキテクチャ内での位置づけ

```
app/pages/game_input.py (Streamlit UI, 2539行)
  ├─ domain.runner_advancement.suggest_runner_states  … 確定前の走者状況サジェスト
  ├─ domain.scoring_rules.collect_scoring_warnings    … 非ブロッキング警告
  ├─ domain.input_validation.validate_play_confirmation … 確定可否判定
  ├─ domain.scoreboard.apply_scoreboard_event         … スコアボード更新（±1で取消も）
  └─ domain.game_state.update_list                    … 次プレイの基底状態を導出
services/play_editing.py・play_replay.py
  └─ update_list を再利用して「過去プレイ編集→下流全行再計算」「全行リプレイ整合性検証」
```

データモデルは**イベントソーシングではなくスナップショット型**：1球=1行（88列）に試合状態全体（得点・カウント・走者・打順・両チームのラインナップスナップショット・スコアボード）を毎回埋め込む。88列の定義は `C:\develop\baseball_system\config.py` の `COLUMN_NAMES` / `IDX`。

## 2. モジュール別の責務と主要シグネチャ

### 2.1 game_state.py（425行）— 状態遷移の中核
| 関数 | 入力 | 出力 |
|---|---|---|
| `update_list(row, top_poses, top_names, top_nums, top_lrs, bottom_poses, bottom_names, bottom_nums, bottom_lrs, top_score, bottom_score)` | row: 88列list（確定済みプレイ）、各lineup list、score list | 次プレイの基底となる**新しい88列list** |
| `apply_manual_state_change(current_data, *, inning, half, top_runs, bottom_runs, strikes, balls, outs, batting_order, runner1_order, runner2_order, runner3_order, top_names, bottom_names)` | 88列list + 手動編集値（文字列可、内部でint強制） | 修正済み88列list（コピー、非破壊）。不正値はValueError |
| `apply_tiebreak_state(current_data, *, inning, half, top_runs, bottom_runs, batting_order, top_names, bottom_names, base_pattern="一二塁", outs=0)` | base_pattern ∈ {一二塁, 二塁のみ, 満塁} | タイブレーク開始状態の88列list。走者は打順から逆算配置 |
| `check_missing_positions(poses)` | 守備位置list | 不足ポジション番号のset（2〜9） |

依存: `config.IDX`、`domain.game_end_rules`、`domain.out_statuses`。**pandasすら不要の純Python**。

### 2.2 runner_advancement.py（246行）— 進塁サジェスト
| 関数 | 入力 | 出力 |
|---|---|---|
| `suggest_runner_states(batting_result: str, *, runner1, runner2, runner3, secondary_result="0", strategy="0", strategy_detail="0", strategy_result="0", pickoff_kind="0", pickoff_detail="0", current_*_status="継続", outs=None)` | 打撃結果ラベル＋走者の有無（`"0"/0/""/None`=不在）＋作戦・牽制情報 | `RunnerStateSuggestion` frozen dataclass（batter_status, runner1〜3_status, warning: str\|None, play_type, batted_ball_type） |
| `has_runner(value) -> bool` | Any | bool |

**確定前サジェスト専用**（UIで上書き可能な提案値）。データ形式に一切依存しない完全な純粋関数。四球のフォース進塁のみ進む判定、犠飛は三走のみ、盗塁成功はリード走者、Wスチール、牽制死、振り逃げ成立条件（一塁走者あり&2死未満は警告）等をカバー。

### 2.3 scoreboard.py（85行）— スコアボードカウンタ
| 関数 | 入力 | 出力 |
|---|---|---|
| `apply_scoreboard_event(*, top_score: list, bottom_score: list, top_runs, bottom_runs, half, inning, batter_status, runner1〜3_status, batting_result, error_player, direction=1)` | 16要素スコアリスト×2（**in-place破壊的変更**）、状況ラベル | `(top_runs, bottom_runs, runs_scored_on_play)` のtuple |
| `count_scoring_runners(batter_status, r1, r2, r3) -> int` | 4状況ラベル | `"本進"` の数 |

得点=「本進」の個数。direction=-1でプレイ取消の逆演算。index 12〜15がH/E/K/BBカウンタ、延長は12回スロット（index 11）に折り畳み。

### 2.4 scoring_rules.py（138行）— 非ブロッキング警告
| 関数 | 出力 |
|---|---|
| `collect_scoring_warnings(*, inning, half, outs_before, top_runs, bottom_runs, batting_result, batter_status, runner1〜3_status) -> list[ScoringWarning]` | `ScoringWarning(code, message)` frozen dataclassのリスト |
| `warn_force_third_out_score(...)` / `warn_walkoff_extra_runs(...)` | ScoringWarning \| None |

第3アウトがフォース/打者アウト時の得点無効（規則のタイムプレー）、サヨナラ時の余剰得点の2種。**警告のみで強制しない**設計（記録優先のiScore方式）。

### 2.5 game_end_rules.py（50行）— 試合終了判定
| 関数 | 出力 |
|---|---|
| `should_finish_game(*, kind, inning, half, top_runs, bottom_runs, half_ended: bool) -> bool` | 9回未満はFalse／裏で後攻リード=即終了（サヨナラ）／表終了時に後攻リード=裏不要／裏終了時に非同点=終了／オープン戦(`kind`に"オープン戦"含む)は同点でも規定回で終了 |
| `is_open_game(kind) -> bool` | 引き分け許容試合か |

定数: `GAME_CONTINUES="試合継続"`, `GAME_FINISHED="試合終了"`。

### 2.6 out_statuses.py（4行）— アウト定義の単一情報源
```python
RUNNER_OUT_STATUSES = frozenset({"封殺", "投手牽制死", "捕手牽制死", "盗塁死", "走塁死"})
BATTER_OUT_STATUSES = frozenset({"アウト"}) | RUNNER_OUT_STATUSES
```
game_state / scoring_rules / pitching_innings / batting_results が共有。

### 2.7 batting_results.py（43行）— 結果値の語彙と正規化
`HIT_RESULTS` / `STRIKEOUT_RESULT_ALIASES`（表記ゆれ正規化辞書: 見逃し三振→見三振等）/ `WALK_RESULTS` / `SACRIFICE_RESULTS` / `AT_BAT_EXCLUDED_RESULTS` / `OBA_DENOM_EXTRA_RESULTS` 等のfrozenset群＋`normalize_strikeout_result(result) -> str`、`is_strikeout_result(result) -> bool`。成績計算3実装（charts/batting, charts/pitching, analytics）の定義統一用。

### 2.8 pitching_innings.py（50行）— 投球回換算
- `count_pitcher_outs(df: pd.DataFrame) -> int` … **唯一pandas依存**。打者状況・一〜三走状況列からアウト数集計
- `outs_to_display_innings(outs) -> float`（4アウト→1.1表記）/ `outs_to_rate_innings(outs) -> float`（→1.333）/ `outs_to_fraction_label(outs) -> str`（→「1⅓」）は純粋

### 2.9 input_validation.py（139行）— 確定前バリデーション
`validate_play_confirmation(*, start_time, current_game_id, batting_result, error_player, play_type, stance, course_x, course_y, pitch_type, result_category, batted_ball_x, batted_ball_y, fielder, batted_ball_type, secondary_result="0") -> ValidationIssue | None`（最初の違反1件を返す）、`can_record_play(issue) -> bool`、`validation_guidance(issue) -> ValidationGuidance | None`。申告敬遠・ピッチクロック違反単独行は投球詳細を免除するなどの分岐あり。純粋だが「クリック座標」「開始時刻ボタン」等**現UIの入力手順に意味的に結合**。

### 2.10 pitch_speed.py（27行）
`compose_pitch_speed(tens_digit, ones_digit, *, force_hundreds=False) -> int` … 2桁入力→球速復元（01-64→101-164、65-99→そのまま、00→0）。現テンキーUI固有のクイック入力仕様。

### 2.11 player_side.py（33行）
`normalize_player_side(value, *, default="右") -> str`、`default_plate_side(player_side, pitcher_side=None) -> str`（両打ちは投手の逆をプリフィル）。純粋。

### 2.12 team_theme.py（86行）
チームカラーパレット定義（6種）と `get_palette` / `header_background_for_team`（CSS linear-gradient文字列生成）。**ドメインロジックではなくUIテーマ**。特定チーム名（七十七銀行等）がハードコード。

## 3. 状態遷移の中核連鎖（1球確定時の処理フロー）

実際の呼び出し順（`app/pages/game_input.py` L1154〜L1668 で確認）:

1. **サジェスト**: `suggest_runner_states(打撃結果, 走者有無, 作戦, 牽制…)` → 打者/一走/二走/三走の状況ラベル案。UI上で人間が上書き可能。
2. **警告**: `collect_scoring_warnings(...)` → フォース第3アウト得点・サヨナラ余剰得点をst.warning表示（ブロックしない）。
3. **バリデーション**: `validate_play_confirmation(...)` → NGなら保存中止。
4. **行構築・永続化**: 88列行を構築し `record_confirmed_play`（services層、DB+メモリ）。
5. **スコアボード反映**: `apply_scoreboard_event(direction=1)` → チーム得点（本進カウント）、イニング別得点、H/E/K/BBカウンタを更新。プレイ削除時はdirection=-1で逆演算。
6. **次状態導出**: `update_list(確定行, lineup各種, score各種)` が次プレイの基底行を生成。内部ロジック:
   - **得点**: 行の4状況ラベル中の「本進」数を攻撃側得点に加算（※手順5と独立に再計算する二重管理。両者の一致が暗黙の前提）
   - **アウト**: 打者状況∈`BATTER_OUT_STATUSES`＋各走者状況∈`RUNNER_OUT_STATUSES` を加算
   - **3アウト時**: イニング切替（表→同回裏／裏→次回表）、走者・カウント全クリア、次打順は`先攻打順`/`後攻打順`（チーム別の独立トラッキング）から継承、「打席継続」のまま終わった場合は同打者から再開するよう打順を1戻す、未消化イニングのスコア枠を`""`→`0`確定
   - **3アウト未満**: 打席完了なら打順+1（9→1循環）、走者再配置＝状況ラベル→塁のマッピング（出塁→一塁、二進→二塁、三進→三塁、本進→消滅、継続→現在塁、アウト系→消滅）。**衝突検出なしの後勝ち上書き**
   - **S/B**: 見逃し/空振り→S+1、ファール→S<2のみ+1、ボール or ピッチクロック違反→B+1、打席完了/チェンジで0リセット、`S=min(S,2)` `B=min(B,3)` でクランプ（B=4での四球自動変換は**ない**）
   - **試合終了**: `should_finish_game(...)` がTrueなら走者クリアし `試合継続="試合終了"` をマーク
   - 次プレイ用に投手・捕手・打者の氏名/番号/左右をlineupスナップショットから引き直し、入力系カラムを全て初期値に戻した88列を返す
7. **編集・リプレイ**（services層がupdate_listを再利用）:
   - `services/play_editing.py::recalculate_play_rows_from_edit` … 編集行以降を`update_list`で順次再導出し、各行の「アクション列」（打撃結果・コース等33列）は保存値を保持、「状態列」（得点・カウント・走者・打順）のみ再計算
   - `services/play_replay.py::validate_replay_consistency` … 全行を先頭からリプレイして保存済み状態列と照合し不一致を報告（回/表裏/得点/S/B/アウト/打順/走者打順の11項目＋S≤2/B≤3/アウト≤2の上限チェック）

**状態のエンコーディング**: 走者=「打順番号(1-9, 0=不在)+氏名文字列+状況ラベル」のトリプレット×3塁。走者の同定が氏名文字列（player_id未連携）である点は新アーキテクチャでの要改善点。

## 4. Streamlit依存の検証結果

- `domain/` 全体で `streamlit` のimport・`st.` 参照は**0件**。
- 外部依存: `config.py`（IDX定数、game_state.pyのみ）と `pandas`（pitching_innings.pyのみ）。他10モジュールは標準ライブラリのみ。
- session_state操作は `services/play_editing.py` の `replace_last_play_in_session` / `replace_play_in_session_by_number` に隔離されており、しかも `session_state: Any` としてdict互換で受けるためテストからはプレーンdictで呼べる設計。
- `tests/test_import_contracts.py` がdomain 8モジュールのimport成立を契約テスト化している。

## 5. 再利用性の3分類

### A. そのまま再利用可（データ形式にも依存しない純粋ロジック）
| モジュール | 備考 |
|---|---|
| `out_statuses.py` | 定数のみ。語彙の単一情報源として最優先で移植 |
| `batting_results.py` | 定数+正規化関数。成績計算の語彙統一に必須 |
| `runner_advancement.py` | 進塁ルールの核。入出力ともプリミティブ+dataclass |
| `game_end_rules.py` | スカラ引数のみの純粋関数 |
| `scoring_rules.py` | out_statusesのみ依存の純粋関数 |
| `player_side.py` | 純粋 |
| `pitch_speed.py` | 純粋（ただし現テンキーUI固有仕様。新UIで不要なら捨てても良い） |

### B. 軽い改修で再利用可
| モジュール | 必要な改修 |
|---|---|
| `game_state.py` | **ロジックは完成度が高く枯れている**（テスト34本+リプレイ検証で防御済み）。Pythonバックエンドなら`config.py`の88列定義ごと持ち込めば無改修。ただし長期的には88列リスト+IDX添字→構造化GameStateモデル（Pydantic）への変換アダプタ、または段階的な内部書き換えを推奨。update_list内の生インデックスアクセスは約99箇所（既存監査docs/system_audit_20260612.md指摘） |
| `scoreboard.py` | 16要素リスト（12回折り畳み+H/E/K/BB混載、空文字センチネル）とin-place mutationが形式結合。ロジック自体は30分で構造化可能 |
| `input_validation.py` | ルール自体はAPI側の入力検証として再利用可。ただし`start_time`/`current_game_id`/クリック座標など現UIフロー前提の項目は新UIの入力手順に合わせて取捨選択 |
| `pitching_innings.py` | `count_pitcher_outs`のpandas依存を剥がす（イテラブル+状況ラベル抽出に書き換えれば5分）。outs_to_*3関数はそのまま可 |

### C. 書き直し（または移植先で再設計）が必要
| モジュール | 理由 |
|---|---|
| `team_theme.py` | ドメインではなくUIテーマ+チーム名ハードコード。新フロントではデザイントークン/DB管理として再実装が自然 |
| （TypeScriptフロントに載せる場合の全モジュール） | 言語境界のため全て移植。ただし全関数が純粋・決定的・標準ライブラリのみなので、既存テストをJSONテストベクタ化すれば機械的な等価移植が可能。特に`update_list`は88列リストのままでは移植しない方がよく、構造化モデルで書き直し+既存テストで等価性検証を推奨 |

## 6. テストの有無・カバレッジ感

- テスト基盤: **標準ライブラリunittest**（pytest設定・coverage設定・CI設定は見当たらない）。tests/配下37ファイル・計300テスト関数。
- ドメイン直撃のテスト（関数名ベースの本数）:
  - `test_update_list_behavior.py`: **34本**（カウント進行、走者押し出し、チェンジ、打席継続時の打順巻き戻し、延長のスコア枠折り畳み、サヨナラ即終了、9回表コールド、タイブレーク3パターン、手動状況変更の異常系まで）
  - `test_runner_advancement.py`: 23本（長打・四球フォース進塁・犠飛・併殺・盗塁成否・牽制死・振り逃げ成立4象限）
  - `test_input_validation.py`: 10本 / `test_scoreboard.py`: 7本（direction=-1の逆演算含む） / `test_scoring_rules.py`: 7本 / `test_pitching_innings.py`: 5本 / `test_pitch_speed.py`: 4本 / `test_player_side.py`: 3本 / `test_batting_result_definitions.py`: 7本 / `test_play_replay.py`: 2本
- **実行検証**: 素のPython 3.14（venvなし、streamlitなし）で95本パスを確認。`test_batting_result_definitions.py`のみcharts/analytics経由でstreamlitを要求し環境不足でスキップ相当（domainモジュール自体の問題ではない）。**ドメイン層が本当にUI非依存であることの実証**になっている。
- **穴**: `game_end_rules.py`に専用テストなし（update_list経由の間接テスト3本のみ。オープン戦引き分け・境界回数の直接テスト欠落）。`team_theme.py`はrepo経由テストのみ。カバレッジ計測がないため行カバレッジは不明だが、中核パスの分岐カバーは体感高い（サヨナラ・タイブレーク・延長・打席継続などエッジを踏んでいる）。

## 7. 新アーキテクチャ設計者への注意点（既知の制約・バグ）

リポジトリ内の監査文書 `docs/system_audit_20260612.md`（2026-06-12付、57件検証済み）と本調査での精読から:

1. **得点計算が二重管理**: `apply_scoreboard_event`（UI変数+スコアボード）と`update_list`（次状態行）が独立に「本進」を数える。新設計では得点導出を一箇所に統一すべき。
2. **不変条件ガード欠如**: update_listはS=3/B>3/同一塁走者重複/4アウトを検出しない（リプレイ検証で事後検出のみ）。B=4→四球の自動変換もない（ピッチクロック違反でのB加算時に必要になる）。
3. **サヨナラ余剰得点**: 警告のみでクランプしない（公認野球規則7.01(g)(3)と乖離）。
4. **スコア取消の情報喪失**: `_subtract_inning_runs`で0点になると`""`（未消化）に戻り「0点の回」と区別不能。
5. **試合形式の拡張性**: `should_finish_game`は9回制固定+「オープン戦」文字列マッチのみ。7回制・コールド・タイブレーク自動終了は未対応（タイブレークは開始状態設定のみ実装）。
6. **走者同定が氏名文字列**: player_id連携は計画のみ。同姓同名・代走で破綻し得るため新設計ではID参照必須。
7. **監査文書の推奨方向**（新設計と整合的）: 1球1行スナップショットは維持しつつ、走者状況の文字列ラベルを「(起点塁, 到達塁, is_out, 理由enum)」の構造化表現へ、打者を0塁起点走者として統一、判断（安打/失策）と事実（到達塁）の分離、イベント正本+状態導出（Retrosheet/MLB GUMBO型）。

**総合判定**: このdomain層は「Streamlitアプリの中に埋まった再利用不能なロジック」ではなく、**すでにUI分離済み・テスト防御済みのポータブルなルールエンジン**である。FastAPI化ではB分類の形式変換だけが実作業であり、野球ルールの再発明は不要。TypeScript化でも仕様書代わりに関数とテストをそのまま読める品質。最大の設計判断ポイントは「88列スナップショット形式を維持するか、構造化イベントモデルに刷新するか」であり、刷新する場合もupdate_list+リプレイ検証の既存挙動が正解データとして機能する。
