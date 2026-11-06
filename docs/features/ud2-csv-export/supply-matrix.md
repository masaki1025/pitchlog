# 新PitchLog記録の有限供給matrix

基線は全行 `40ce2e312bc46435239f2a6d0ea0f1fb919a5de0`。本計画の実装ownerは**root Codex主担当（PO委任）**で統一し、過去の未在籍producerへ未回答の受諾依頼を投げて無期限待機しない。step1で以下の型/契約・現行D-1の宣言正本/生成targetと対応fixtureを固定し、step2でDB実供給へ結ぶ。純読取/形式準備は計算の方式ゲートと独立に進める。既供給型の所有は尊重し、意味変更を伴わない追加公開値の契約をこの計画で受理する。将来T5/T6の実装者は同じ正本の完成値を受け取る。CSV専用のコピー計算を増やさない。

**receiptは本表の予定に対する実装受理記録**であり、現時点の製品供給成功を意味しない。全88列はcandidate JSONのsupply_groupで本表へ対応する。未受理は実装対象が未完という意味であり、外部提供待ちという意味ではない。

共通版/キー: DB REPEATABLE READ + event/slot version digest。生成元`game_id/generation/d1/source_event_id`、D1-null変更はtarget pair。本体行orderはplay_number/id。保存NULLのみ空文字、未提供は非成功。sourceのJSON値と型をprojections sidecarへ保存し、CSVへは受理済完成文字列を写す。

## 88列の供給

| ID・列 | 実在sourceと不足 | 同計画の追加adapter/単一producer exactpath | 単位・NULL・fixture |
|---|---|---|---|
| G01:0–8,76 | `db/game_state/models.py::Game`のscheduled_at/section_label/game_type_key/tournament_key/補助label/plate_umpire/away,home_team_record_id/started_at。team/vocabの表示参照が必要 | `backend/src/pitchlog/repositories/play_export.py`の同版参照結合→`backend/src/pitchlog/exports/play_rows.py`の完成文字列写像。日付JSTと旧日付形式、Kindは旧キーへの意味推測でなく保存済試合区分/大会の受理済表記bindingをstep1 fixtureで固定 | scheduled_atはJST試合日。Seasonはsection_labelであり成績暦年ではない。NULL保持。fixture `game_labels_and_dates` |
| G02:9,26,28–31,39–41,44–58,60（座標42–43/50–51を除く） | `PlayRow`のlegacy_source_columns付き保存列。語彙参照keyは値名でない。55=error_fielder_position,60=comment | 同repositoryで保存語彙を同snapshot参照、`exports/play_rows.py`で受理済key/label対応のみ。打撃/球種labelの完成表示が既native artifactにある場合はそれを使い、無い場合はG04の単一投影へ表示bindingを追加 | INTEGER/TEXT/REALの旧列型とwriter型は分離。速度は完成十進文字列、0とNULL区別。fixture `stored_columns_and_vocabulary` |
| G03:42–43 | 新規保存の正準courseはaccepted payload `observations.course`の`unit=1/263,x,y`。DBのDoubleだけからkを丸め直さない。既`courseQuantization.ts`/`domainrt/course_quantization.py`は入力量子化で保存→画面operationは未公開 | 現行D-1によりT5と独立した`backend/domain/play-export-display.model.json`のcoordinate-transform宣言からPython/TS targetを生成し、`backend/src/pitchlog/exports/generated/coordinate_transform.py`を呼ぶ。参照先/方式と生成targetを専用manifestへ固定。T5共通hash/既v3保存を変えない。TS手書き→JS artifactという新D-2対象を追加しない | 正準k整数/263、x=kx,y=263−ky。例kx132/ky66→132/197。保存NULL→NULL、正準0は有効点。fixture `coordinate_transform_contract_v1`の正準保存→画面16case＋NULL/端点。入力方向/非正準量子化は別既targetのまま。新裁定不要 |
| G04:10–19,33–34,59,61–62,73–74,86–87 | `sync/{first_ball,ordinary_pitch}_payload.py`のcalculation.request/responseにT1前後・scoreboard差分、participants/観測あり。投手別累計球数・全イニング配列は未供給 | **G04-R**: `backend/src/pitchlog/exports/record_projection.py`は保存T1のfield抽出/受理済label/JSON形式だけで、状態の再計算/累積をしない。**G04-A**: rootが既確定primitiveのT5供給担当として`backend/domain/play-export.model.json`の有限reducer宣言→`backend/src/pitchlog/domaingen/backends/sql.py`の必要target生成→`backend/src/pitchlog/exports/generated/play_primitives.sql`→`backend/src/pitchlog/repositories/play_export_primitives.py`という唯一のDB入口を追加。34と各回scoreは下記型付き対象集合・WHERE/GROUP BY/windowでDB計算し、CSV/T5双方が同じ入口を読む。Python/JSで全event count/sum/reduceしない | G04-Rの文字列合成が宣言表示規則を要する部分は同D-1生成formatterへ。G04-Aの構造整数/完成JSON/版は型契約固定。fixture `record_projection_native_payload`と`db_pitch_count_and_inning_scores`（半回/交代/非投球/訂正/取消/再開/再終了/世代/500境界）。対象別独立期待値・一致/性質/変異検査とquery planをstep1/2で実施。未決OPS/登板/打者数やT5全体完成は要求しない |
| G05:20–25,36–38 | `PlayRunner` runner_id/base/status/status_source/responsible_pitcher_id、accepted payloadのbefore参照。打順・表示名は参照結合が必要 | `repositories/play_export.py`でページ内play_id一括結合、G04-R読取adapterが既state/保存走者順と履歴lineupを参照。`exports/play_rows.py`はその完成値をコピー | 正式before/afterタイミングを既native row契約へ固定。base1–3、番号/名前/状態。fixture `runner_identity_and_responsibility` |
| G06:27,32,35,63–71 | `PlayRow` batter/pitcher/catcher_id、`GameLineup.entries_with_uniform_number_snapshot`、`ParticipationInterval.uniform_number_snapshot`、Playerの表示識別。旧元字面の保存は新記録の前提でない。氏名snapshotがnative payloadに無い場合は現在名を履歴名と偽装できない | `repositories/play_export.py`の参照結合と`exports/play_rows.py`。新規記録時に履歴表示名が必要な不足は`backend/src/pitchlog/sync/play_export_identity.py`に唯一snapshot形成を追加し、`sync/first_ball_projection.py`/`sync/ordinary_pitch_projection.py`の既同TXへ記録用補助投影を接続。必要保存表`db/game_state/export_snapshots.py`/migration `*_play_export_snapshots.py`を本計画step1/2で追加（既payload wireの自由拡張はしない） | idは安定参照、背番号は文字列`007`を保持、NULLは元NULL。fixtures `identity_renamed_after_record`/`uniform_007`。氏名/利き腕/守備位置の原典上の時点を受理し、現在名と履歴名はsource_kindで分ける |
| G07:72 | accepted payloadに入力経路の業務識別があれば保存値。無い場合は既新規入力経路が一つでも値`0`を勝手に当てない | `sync/play_export_identity.py`の記録metadata snapshotへ既input経路識別を記録、`exports/play_rows.py`へ読み出す。step1の旧列72意味/新規入力経路対応を技術bindingとして主担当が受理 | 任意旧フラグを捏造せず、実sourceの識別を保持。fixture `input_origin` |
| G08:75,77 | Game.started_atはあるがOperationEventには記録時刻列がなく、既payloadもプレイ時刻を持たない。旧Tag機能はWon't、現在payloadのプレイ時刻完成文字列は要確認。TSK-214移行完了は新記録の前提にしない | 同`sync/play_export_identity.py`が実記録時点の業務timestampを保存（device時刻/受理時刻を混同しない）。既時刻のJST書式化は読取adapter、ドメイン表示式が必要な部分だけD-1生成formatterへ委譲する。廃止Tagの空欄契約は正本のWon't/NULLに従いstep1で技術形式を受理し、自動Tagを復活させない | source timestampのJST、elapsedの仕様は旧DLと廃止範囲で確定したものだけ。欠測を現在時刻で埋めない。fixture `timestamp_provenance_no_tag` |
| G09:78–85 | GameLineupとaccepted initial/ordinary roster、ParticipationIntervalの実保存区間。旧固定長をそのまま全新規名簿へ仮定できない | G04-R読取adapterへ既roster/区間を渡し、保存済完成値の旧互換表記とlossless roster JSONを供給、`repositories/play_export.py`で保存名簿を同版取得。足りない履歴はG06同TX snapshotで記録 | 旧非対称長をfixtureで固定、余剰/新概念はsidecarに保持し捨てない。fixture `roster_at_substitution_and_extra_slot` |
| G10:50–51 | `PlayRow.hit_x/hit_y`は正規化保存。コースquantize operationの適用対象と同一と仮定しない。`contracts/field-regions/*`と付録B-6のgeometryが実在 | G03のD-1宣言正本へ**既field geometryの型付き別計算**を追加し、生成targetを保存済打球観測完成値と結ぶ。既規範のgeometry/単位で対象別契約/fixtureを受理。B-7適用対象外の領域頂点をコースk263に量子化しない | unit/axis/geometry IDを受理済field契約に固定、NULL保持。fixture `field_coordinate_export_geometry`。規範で決まらない具体値があればその1値の不足だけrootへ戻し、コース式を推測転用しない |

G04/G06/G07/G08の不足は「既producer提供待ち」ではなく、この専用計画の追加実装範囲。既記録に保存されていない観測を遡って生成しない。新規記録のsnapshot形成を先に統合してから実1試合受入を行う。旧保存済の不完全試合を409にすることは認めるが、以後の新規実試合の完成をそれで代替しない。T5/T6全体・過去移行・Tag廃止の撤回は実装しない。

## 全9サイドカーの供給

全owner=root。追加入口は`repositories/play_export.py`で、直列化は`exports/{play_rows,archive}.py`。全ファイルは同snapshotから取得し、実在source 0件ならheader-onlyを成功として出す（供給型不在による偽emptyとは区別）。業務JSONのallowlist/schemaは実在model/payload codecからstep1でexact-set固定する。

| ファイル | 実在producer/source | 不足と同計画の処理 | fixture |
|---|---|---|---|
| play_links.csv | PlayRow + OperationEvent | source pairとordinalだけを同版結合、集計なし | same_play_number_two_generations |
| events.csv | OperationEvent + first_ball/ordinary payload codec + event_kinds.py | 全10 event kind/flagsのschemaをexact-set登録。資格を除いた業務値を完全保持。未知fieldは失敗 | d1_null_change_and_tombstone |
| runners.csv | PlayRunner | ページ内複数行/retired履歴の区別、source_json全業務field | runner_responsibility_and_retirement |
| lineups.csv | GameLineup | entries JSONを完全保持。現名簿から置換しない | lineup_uniform_007 |
| participations.csv | ParticipationInterval | 保存interval/unknownを原状保持、出場を推測しない | interval_unknown_vs_absent |
| game.csv | Game | 業務欄全数+ルール/時刻/label。秘密・資格なし | game_applied_rule_and_labels |
| references.csv | TeamRecord/Player/AdminVocabulary/TenantVocabulary | 当該試合で参照する業務表示欄だけ、関連なしtenant全選手を読まない | renamed_reference_snapshot |
| projections.csv | G03/G04のD-1生成target/DB primitive/G06–10記録snapshot | この計画が入口を実装。既producer不存在を理由に空JSONでreadyにしない | projection_all_88_bindings |
| preserved_sources.csv | 新規記録には旧移行原本は存在しない。採用済退避業務原本はRecordingRights側の既保存表がsource | 新規の非移行・非退避試合は正当に0件。採用イベントがあるなら同版で業務値を読む。旧原字面復元/TSK250完了は後続移行へ | new_native_no_legacy_source / adopted_business_event |

各rowの型/NULL/キーはsidecars.candidate.jsonへ固定。本表の実装前statusはplannedでありacceptedではない。step1の型付きpure契約とD-1宣言/生成target、step2のDB/同TX snapshot、step3の実HTTP、step4/5のDL/往復をもってacceptedへ更新する。


## G04-A: DB primitiveの対象集合・単一入口

ownerはroot（T5の**既確定primitive供給**担当）。T5全27指標を実装するという意味ではなく、CSVが必要とする球数/各回scoreだけの共通事実供給である。型付き契約を`contracts/exports/play_primitives_v1.json`、宣言の唯一の人手保守元を`backend/domain/play-export.model.json`、実入口を`repositories/play_export_primitives.py::ReadPlayExportPrimitives`へ固定する。現行D-1-dの有限reducer→生成SQLを使い、手書きSQLで別の野球判定式を作らない。

- **選択集合S**: 同RR snapshot内の同tenant/gameの可視PlayRowと、そのsourceである受理済OperationEvent。hidden/trashed試合・hidden行・retired/replaced source・tombstoneを除く。訂正は適用済み最新PlayRow.versionとその確定slot版を使い、取消前の旧値を二重算入しない。世代はsource pairの一部であり、current世代だけへの絞込によって引継ぎ前の有効プレイを消さない。Sとsnapshot digest/slot versionの対応を契約化し、監査events sidecarの全履歴集合とは分離する。
- **列34**: Sの`play_rows.event_kind='pitch'`をA-2/4.0-2の1投球として、`tenant/game/pitcher_id`で分割。各行のsource D2論理順＋source_event_idの安定順で、その行までの`COUNT` windowをDBで求める。`non_pitch`は算入しない。投手ID/順序欠測は未知値のまま非成功。source D1/世代は識別に保持し、D1を跨世代の論理順序に転用しない。表示行のキーセット条件はwindow評価の**後**に適用し、2ページ目の累計を0から再開しない。
- **各回score/86–87**: 受理済みT1の保存before/afterの`inning/half/state.score`と確定scoreboard差分がsource。CSV側でアウト/得点の有効性を再判定しない。SのT1完成値から生成SQLが`tenant/game/攻撃側/回`をWHERE/GROUP BYし、確定済み得点差分だけを合算。必要な累積・最新値選択はDB windowで行う。完了0点と未消化の区別も保存T1到達状態を使い、プレイ不在を0点と推測しない。旧配列末尾の定義/表示はDL precedenceの契約に従い、指標式をCSVへコピーしない。新延長等の構造値はprojections sidecarに完全保持する。
- **計算しない処理**: SQL結果の型/版検証、保存T1 fieldの参照、source JSONの直列化、既完成人名/語彙表示の結合、manifest作成。これらはPythonで行える。式/丸め/結果合成はD-1宣言からの生成targetが担当する。
- **検証**: 同じSで独立期待値へ構造値/完成表示一致、再開・訂正・取消・再終了・再送/世代の対向、500前後の累計継続、数値0/NULL、DB explainのtenant/game/有効版絞込と索引利用。Python/JSに全イベント列を渡して累積する経路が無い構成検査を行う。生成器が必要window/有限reducerを表せなければ手書き式へ逃げず、その具体構文不足だけをrootへ返す。

## 追加計算の方式と独立先行範囲

| 区分 | 対象/実行所在 | 現行方式と着手条件 |
|---|---|---|
| 読取・整形 | G04-R、履歴/ID/語彙結合、JSON/CSV/ZIP、tenant固定抽出、HTTP/DL | 新しい計算を含まないPython/SQL参照と既writer。step1のpure契約準備とrootが指示したstep2以降の準備を先行可。未供給409は成功ではない |
| 行単位計算/表示 | G03/G10保存→画面、G04の未供給表示式 | 現行**D-1**宣言モデル→必要Python/TS/formatter生成。B-7の意味既決と実現方式を分離。対象別独立契約/基盤→正本/生成target/呼出部/3層同一変更という既ゲートを守る |
| 確定primitive集計 | G04-A球数/各回score、DB | 現行**D-1-d**宣言reducer→SQL、DB WHERE/GROUP BY/window+索引。手書きJS全件reduce/CSV Python集計禁止。T5全体や未決指標へ広げない |

D-14-mはT1/T2/座標入力形成だけ。出力変換・本primitiveへ同JS artifactの例外を広げない。実装上D-1の射程外が具体的に判明しD-2へ置く必要が出た場合のみ、対象を名指したADR/要件の最小正式化・7.6該当確定ゲートを**当該計算コード追加前**にrootが行う。本候補の承認/contract追加/3層検査だけで方式改訂を代替しない。今回はD-1を選び、未承認D-2 artifact追加パスをスコープから外した。
