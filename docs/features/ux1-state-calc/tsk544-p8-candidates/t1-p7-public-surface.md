# TSK-544 T1 P-7公開境界の具体案 v0

状態: **担当受理前の候補**。既存U-S1の`SyncEvent`、`ProjectionPort.apply(event, writer)`、`ContentValidationPort.validate(event, writer)`、`PortWriter`を維持する。実Portの提供SHAと着手前の公開契約を区別する。T1のTS正本・同一JS artifactはU-X1が1つだけ所有し、HTTP/画面/同期核にコピーしない。

**未解決の配線点**: 既存Port署名は`event, writer`だけで、候補`T1AppliedContextV1`の確定名簿・投影前状態・規則snapshot・D4を渡せない。U-S1所有側に(a)同一イベントwriterに結ぶcontext引数をPortへ追加する、(b)適用核の既存認可済み読取経路からcontextを組み立てて同一scopeでadapterへ供給する、の2案を提示する。**どちらも未受理**。U-X1が独自のDB読取・Sessionを増やさず、返答までは配線成立としない。

U-S1の2026-10-20回答（`tsk544-p7-us1-response.md`、コミット`5ca7ef2e`）では、既存`validate(event, writer)`と`apply(event, writer)`だけで評価共有は保証されず、⑦のeventとT4のprojected_eventは写像/採番の前後で同一objectとも限らない。**推奨された未採用案**は、不変`T1PreparedEvaluationV1`を一イベントscopeの局所変数に置き、入力同一性・event/prefix/規則snapshot/投影前状態と結果を束縛して投影へ明示的に渡すこと。候補署名は`prepare_t1(event, writer)`と`apply_prepared_t1(event, prepared, writer)`であり、既存Portに無断でメソッドを足さない。評価を現⑦で行えるか、写像/T5後に移すとO4・内容拒否の優先順が変わるかは**未決**。U-S1の計画/Port所有ゲートで確定する。旧D5/source指紋は変更しない。

| 境界 | 提案する公開型/署名・版 | 失敗と責任 |
| --- | --- | --- |
| U-X1 T1正規化 | `normalizeT1EventV1(raw: SyncEvent, context: T1AppliedContextV1): Result<T1NormalizedInputV1, T1InputRejectionV1>`。適用時文脈は認証済みtenant/game、不透明文字列のD4、**照合済み**D1/D5、確定prefix、保存済み規則snapshot、当該scopeの確定名簿/投影前状態を含む。値はU-S1/U-G1/U-R1から受け取り、画面は作らない。追記前の画面下書きではD1/D5を「受理済み」とせず、表示用の事前評価文脈とサーバー適用時文脈を区別する。下書きのV8/state_diffは確定保存を示さない | 欠落・矛盾はtyped rejection。HTTP外形S-1と混同せず、U-S1既存B3a/T9へ対応するか項目別に受理を求める。独立したD5消費・ACK判定はしない |
| U-X1 T1計算 | `evaluateT1V1(input: T1NormalizedInputV1): Result<T1EvaluationV1, T1DomainRejectionV1>`。評価はTS正本→同一artifactの単一実装。`T1EvaluationV1`は正規化入力の同一性、同一event/prefixの状態差分・有効得点・成績フラグ・undo再評価に必要な射影を型付きで返す。厳密なfield集合はP-8正式版と同時に固定 | validator/projection間で意味が変わらないよう同一イベントscopeに評価結果を結ぶ。Port署名を変える必要があればU-S1所有ゲートへ。別の計算核・セッション・transactionを作らない |
| U-S1同期入口 | 単一路`apply_sync_request`、P1/P2混在は`apply_sync_events`。既存Portの同一イベントwriterは維持し、T1文脈/評価の渡し方は上記(a)/(b)/不変prepared値からU-S1所有側が確定する。D5/拒否原本/投影はイベント単位で原子化し、バッチの前方確定は維持 | validatorの内容拒否は既存B3a/T9、同D5/同指紋はDI2再掲、RG1読取/失効は既存B7/P3 B10等へ。Port例外を内容拒否へ変換しない。前方確定を後方失敗で取り消さない |
| U-R1記録権 | 既存`RecordingRightsPort`の実装/登録と、terminal contextを含む復旧世代・保持照合の公開署名を所有側が確定する。T1は検証済みcontextのみ消費する | 閉鎖・失効・不保持・照合不能を混ぜず、既存のB区分を維持。実Port提供SHAはまだ無い |
| U-F8画面 | 1球の観測入力を欠落なく保持し、U-X1の正式TS型で正規化入口へ渡す。追記前の表示用事前評価と、D1/D5照合後の適用結果を区別し、同一scope/event/prefix/snapshotの確定結果を表示する。表示内で得点/RBIを再計算しない | 観測欠落は入力補正を促す。送信未確認/停止を成功表示しない。型/normalizer/formatterの提供SHAはU-X1実装後 |
| TSK-506 HTTP | E-1/E-2 requestからU-S1の本物の適用核へ配線し、ACK/拒否wireを所有する。P1/P2をHTTPで分割しない | 認証・DTO外形S-1とT1意味拒否を分離。実Port未提供ならHTTP接続完了としない。現在の受取担当の受諾は未確認 |

**失敗分類の未決**: 入力の内容起因と確定した拒否だけU-S1のB3a/T9へ渡す。DB読取不能、保存規則・投影状態破損、artifact障害を入力不備や`False`へ変換しない。P3内容拒否はB14であり、D1付きと統一しない。Port例外一般が自動でB7になるとは仮定しない。commit不明を未適用と断定しない。

**着手前に必要**: U-X1の上記候補型・版/失敗分類と、U-S1/U-F8/U-R1/506の項目別責任受理。`T1NormalizedInputV1`の具体fieldと拒否理由enumはP-8正式契約と同時に確定し、架空のSHAを記載しない。**実装後に必要**: 本物のPort登録、同一scope全取消と前方確定、DI2二重適用防止、画面→実HTTP→隔離DB保存/再読込を実測する。2026-10-20のU-F8回答は文脈保持・観測入力・描画・拒否表示の責任を受理したが、D4と下書き/適用文脈の区別を要修正としたため本候補へ反映した。具体型の正式受理ではない。

**2026-10-20のU-S1追加回答（HEAD `695a4faf`）**: `T1PreparedEvaluationV1`を一イベント取引の不変局所値としてprepare→T4へ渡す責任境界は条件付き受理。現⑦内容検査→T5/O4の拒否優先順を維持する案が推奨される。ただし⑦入力とT4の写像/採番後入力の論理同値性は未証明であり、変わるなら意味変更をPO/正本へ提示する。U-S1が同一認可scopeで読取tokenから`T1AppliedContextV1`を組み立てる案が推奨され、U-X1が型、506がHTTP composition/実adapter注入を所有する。提案署名は`prepare_t1(event, writer, *, context) -> Result<prepared, rejection>`/`apply_prepared_t1(event, prepared, writer) -> None`で、既存Portへ無断追加せず版付き接続を審査する。J6の観測順序保持・同D5の順序変更拒否・保存観測からのundo再評価の責任はU-S1が受理したが、原wire/codec保存、正式field/参照解決、undo実接続と実Port SHAは未提供。**責任受理は正式V1型・P-7全成立・製品接続の受理ではない。**

**2026-10-20残4項目のU-S1回答（同担当枝HEAD `9ecb437024fab3da31783164e2b9a835b9d53501`）**: 版付き`prepare_t1(event, writer, *, context)`/`apply_prepared_t1(event, prepared, writer)`の署名案は維持するが、contextの規則snapshot・名簿・投影前状態・T1履歴prefixの同scope読取口が未提供。D3とT1履歴prefixを同一視しない。現行の⑦prepare→T5/O4→T4を推奨し、⑦入力と写像/採番後のT4入力の意味同値が未証明なら拒否優先順を確定しない。preparedのscope内配線はU-S1、評価adapterはU-X1、HTTP注入は506の担当。J6順序/原wire/codec版の保存と限定resolverの接続責任はU-S1が受理したが、物理保存方式・正式型・提供SHAは未確定。責任受理はP-7着手前公開契約の全成立でも実Port完成でもない。

## 2026-10-21の項目別受理用契約案（未承認）

既存の⑦→O4→C2を変えないというPO指示と[拒否順判断票](../../tsk544-t1-state-calculation/t1-p7-rejection-order-decision.md)を前提にする。以下は**544が要求する候補型**であり、Python/TSの既存実装・登録済みtoken・正式schemaの宣言ではない。既存`GameReadToken`は`games.applied_rules`を読めるが閉型ではなく、`PlayerReadToken`の最大200行読取も時点名簿の保証ではなく、`OperationEventOrderReadToken`の有限D2範囲もT1適用済みprefixの完全性を保証しない。

| 要求値と候補型 | 最低限の閉入力・失敗条件 | 読取境界と回答先 |
| --- | --- | --- |
| `T1RulesSnapshotV1` | 対象`game_id`と保存済み`games.applied_rules`の同一版、規定回・タイブレーク適格/配置・コールド等T1が使うF-1規則を、未知/欠落を拒否する閉型へ投影。要求中の設定値を上書きに使わない | U-G1は保存snapshotの型・版・固定時点、U-S1は同scopeの`GameReadToken`からの認可済み読取/返却型を回答 |
| `T1RosterAtEventV1` | `game_id`、攻撃/守備team、当該プレイの選手ID・打順slot・有効な出場/交代状態・参照時点を閉じる。タグ付き一時IDは同scopeのC2写像と突合し、名前/背番号では照合しない。別試合・別team・時点不明を拒否 | 名簿データ所有側/U-G1とU-R1が時点・ACL・実データ境界、U-S1が読取token・返却型/参照上限を回答 |
| `T1PreStateV1` | 規範descriptorの`state.*`軸（半回、count、out、走者、打順）と計上済みscore/投手・打者の同一版。現在イベントの投影**前**を指し、古い画面下書きやV8差分を前状態へ流用しない | U-X1が消費する型、U-S1が同scopeの投影状態読取token/版識別とT4への束縛を回答 |
| `T1AppliedPrefixV1` | `game_id`/記録権世代/現D1より前の**受理・有効版**の論理列、D2/変更版/墓標を区別した順序と完了境界。有限ページまたは一貫したsnapshot参照の閉型にし、全件集計や`confirmed_watermark=D3`を履歴とみなさない。欠落・同値D2・scope越境を拒否 | U-X1が必要な履歴射影、U-R1が世代/保存版、U-S1が登録済み読取token・有限範囲/一貫性保証を回答 |

候補の集約署名は`read_t1_context_v1(writer: PortWriter, *, game_id: UUID, generation: int, d1: int, d5: UUID) -> Result[T1AppliedContextV1, T1ContextReadFailureV1]`。`T1AppliedContextV1`は上記4値と、認可済みtenant/game・現世代/D1/D5・同transactionの版印を含む**一イベント限定の不変値**とする。原wireのD4文字列とDB内部の記録権世代整数を同一型に潰さない。⑦のcontext読取ではC2の全参照解決を必須にせず、未解決のタグ付き参照は局所的な保留値として区別する。保留値だけで正しいT1結果を計算できるかは未証明であり、C2失敗を⑦の内容拒否へ前倒ししない。`writer`は適用核発行のものだけを受け、T1からSession/任意SQLを注入しない。読取不能・破損・参照不足は入力内容拒否へ丸めない。4値それぞれの実token、返却フィールド/版、RLS/ACLと同scope寿命は所有側の回答後に確定する。Port完成SHA・実DB試験は実装後ゲートである。

**評価と拒否の候補責任**: U-X1の`prepare_t1_v1(raw_event, context) -> Result[T1PreparedEvaluationV1, T1ContentRejectionV1]`は⑦で元のタグ付きPlayerRefを使い、J6/OUT3/RBI等の内容に限って拒否する。C2未解決を⑦の内容拒否へ変えない。U-S1はT5/O4後、C2とassigned D2を得た時に`assert_t1_equivalent_v1(prepared, projected_event, context) -> Result[None, T1EquivalenceFailureV1]`で、①同一scopeの一時/正式IDが同じ選手、②D2の番号変更が同じ論理位置/前状態を保持、③規則/名簿/前状態/prefixが同じ版、④元eventのD5指紋と`HomeTouchOrderV1`の順序が不変、を検証してT4に同じprepared値を渡す。T4で再計算して差を隠さない。同値が証明できない場合はT4の書込みへ進めず、当該scopeを取消する**候補**とし、境界結果・D5消費・取消確認/commit不明・復旧操作をU-S1との正式接続契約で分類する。単独のC2参照未解決の既存意味B7と、今回の同値不成立を混同しない。現行⑦内容B3a/T9、O4 B3/新台帳0、C2単独状態依存B7を混ぜない。

**J6原入力の保存候補**: 既存`operation_events.payload/state_diff`は投影後JSON/V8であり元wireではない。`idempotency_ledger`は指紋/結果だけで原wire bytes・codec版・順序の原形を持たない。3種類の結果表へ重複列を加えるより、**新wire経路だけに、tenant+D5を一意キーとする追記専用の原本行**を第一候補とする。候補`T1WireOriginalV1 = {tenant_id, game_id, internal_generation, wire_d4, d1, d5, event_raw_wire, wire_codec_version, home_touch_order_raw, source_fingerprint, record_version}`。`event_raw_wire`はHTTP要求全体や資格・permitではなく**当該一イベントの原入力**を損失なく保全する候補であり、その取得範囲・JSON外形・サイズ上限は506が提示する。原wire D4と内部世代は別に照合する。`home_touch_order_raw`を別列へ置くなら正式pathから導いた照合値であり、原入力と独立した第二の順序権威にはしない。`HomeTouchOrderV1`の意味版とwire codec/保存record版は別。新wireのD5指紋は承認済みのcodec版+**正規化した**元wire入力の規則に従い、空白・キー順だけが違う同内容のDI2で原本を上書き・衝突扱いしない。既存DTO経路/保存済み指紋を再解釈しない。受理はledger・原本行・event・T4を同一transactionで、T9に進んだ内容拒否はledger・拒否原本・原本行を同一transactionで保存する候補。T8退避、他のledger結果、競合、停止、commit不明、既存同D5別kindについては原本有無と取引境界を結果種別ごとに確定するまで未受理とする。0行更新/rollbackなら原本行も0、DI2再掲で再挿入しない。原本読取は同テナント同scopeの登録済み限定resolverだけ、利用者へ表直接INSERT/SELECTを与えない。これは**DDL/RLS/ACL/凍結ゲート前の場所候補**であり、テーブル名・FK/全結果種別・旧行移行・実装担当は未確定。U-S1が取引/接続要件を集約、U-R1がdata-model/ACL/編集境界、506がwire bytes/codec版の供給、544が閉意味型、原本Port/DDLの実装担当は項目別回答で確定する。

各受取担当には、上の該当行を**「受理／修正案（具体型・差分）／担当外（受取先）」**で返してもらう。特に「既存tokenで4値が足りる」という回答には登録箇所・返却型・認可scope・不足時結果の証跡を求める。所有窓口の受理は実Portの実装SHAや結合試験の完了を意味しない。

**U-S1項目別回答（`f38e6079`、正式受理前）**: 同scopeの4値集約口と⑦prepare→O4→C2後照合→T4を条件付きで受け、C2未解決を⑦の内容拒否へ移さない修正を要求した。既存GameReadTokenは`applied_rules`の行を読めるが閉じたT1型ではなく、PlayerReadToken・OperationEventOrderReadTokenも時点名簿・完全な有効prefixの保証ではない。投影前状態の専用型/token、同値不成立の結果分類、原本の限定resolver、DDL実装担当は未提供。J6原入力について上記の一イベント単位・版分離・全結果種別を要修正とした。所有窓口の回答を正式型/登録済みPort/7.7と扱わない。

## 条件付き受理を閉じる接続表（2026-10-21・候補）

`read_t1_context_v1`の`writer`引数は現状のままなら書込tokenも受けられるため、読取専用である証明にはならない。候補`T1ReadScopeV1`は適用核が同じtenant・game・transactionで発行し、登録済みの固定SELECT tokenだけを通し、書込token/任意SQL/別Sessionを拒否する能力型とする。公開署名候補は`read_t1_context_v1(scope: T1ReadScopeV1, *, game_id: UUID, wire_d4: str, internal_generation: int, d1: int, d5: UUID) -> Result[T1AppliedContextV1, T1ContextReadFailureV1]`。U-S1が発行/失効・同scope組立・固定読取接続、U-X1が4値の閉型と必要な射影、規則/名簿/履歴のデータ所有側が版・認可・上限を受ける案。既存登録済みtokenだけでは4値は完成せず、この署名も**未提供**である。

| 時点 | この時点で確定する値・検査 | まだ確定しない値・副作用 |
| --- | --- | --- |
| ④既存D5照合後、⑦の読取・prepare | 原イベントの欠落/null/タグ付き参照、`HomeTouchOrderV1`観測、wire D4・codec版1・新wireの正規化イベント指紋、同scopeで固定した規則snapshot・時点名簿・**投影前**状態・有効履歴prefix。既知の同scope参照とOUT3/RBI等の意味入力だけを一回評価し、不変`T1PreparedEvaluationV1`に原event/D1/D5/4値の版印・参照対応・評価結果を束縛する | C2の一時ID→正式ID、P2の割当D2、C2の成否、後段投影は未確定。C2 pendingを⑦の内容拒否にしない。prepareはDB書込・event保存・D5台帳挿入/消費・D3更新・T4投影をしない。純関数の評価と上記固定SELECT読取を分離する |
| T5/O4通過後のC2 | 割当D2と限定resolverによる正式参照、同game/team/scope照合。O4が先で、C2単独未解決は既存B7意味/現実装の例外伝搬を維持する | C2結果を⑦へ遡及して内容拒否にしない。T1用の新規書込/受理はまだ行わない |
| C2後・T4/ledger挿入前 | `assert_t1_equivalent_v1`で下記の閉射影を比較し、成功時だけpreparedをT4へ渡す。失敗時は後段書込へ進まず、同イベント取引の取消を要求 | 不一致をB3a/T9・O5・B7・S-STOPのどれかへ**推測分類しない**。局所取消の確認とcommit不明は区別し、公開結果/再送/復旧をU-S1と確定するまでは接続しない |

同値比較の候補射影は `(tenant, game, internal_generation, D1, D5, logical_slot, normalized_player_refs, rules_version, roster_version, pre_state_version, prefix_version, home_touch_order, evaluation_input_hash)`。タグ付き一時IDとC2後の正式IDは同じ限定写像・時点名簿の同一人物で照合し、UUID文字列や現在名簿の見た目だけを比較しない。assigned D2は数値一致でなく同じ論理位置と有効prefixを証明する。版印/タグ付き順序/新wire指紋のどれかが異なる、または証明に必要な写像が欠けるなら`T1EquivalenceFailureV1`候補へ進め、T4の再計算で隠さない。⑦で意味評価を完了できない参照がある場合は、⑦の内容判定とC2成功条件を両立できるかが**未証明**であり、U-X1/U-S1が具体反例を提示するまでは条件付き受理のままにする。

### J6原入力の結果別保存表（新wire限定・未受理候補）

ここでいう原入力は**一イベント**の意味変換前JSON値であり、HTTP要求全体・認証/V12・attempt_id/permitではない。候補`WireD4 = opaque str`と`InternalGeneration = positive int`は別の値で、前者は506がwireから損失なく渡しU-S1が記録権に照合、後者はU-S1が試合→世代ロックの順でDBから得る。`WireCodecVersion = Literal[1]`は506/U-S1のwire変換版、`OriginalRecordVersion = positive int`は原本行の保存schema版で、U-R1側のdata-model/DDL受理が必要。J6の`HomeTouchOrderV1`は意味入力型の版で、前二者と同じ版番号にはしない。新wire指紋はcodec版1・イベント原値・登録入力の**正規化JSON**から作り、既存DTO/保存済み指紋は変更しない。

| 結果・D5種別 | 新規サーバー原本行の候補 | 取引・保持/取消・再送時の利用 |
| --- | --- | --- |
| 新規成功（P1/P2） | 当該イベント原値/codec版/順序観測とD5指紋を1行 | ledger受理・event・T4と同じイベント取引で確定。失敗なら全取消。DI2では行を増やさず、保存済み結果を再掲。原本は再実行/下流再計算用 |
| 新規B3a/T9内容拒否 | 当該イベント原値/codec版/順序観測を、既存拒否原本とは役割を分けて1行とする候補 | T9のledger拒否・拒否原本と同じ取引だけで確定。取消なら0行。後続のW2照合/DI2は既存原本と台帳指紋を権威とし、新行で既決結果を変えない |
| 新規B4/T8退避 | 当該イベント原値/codec版/順序観測を1行とする候補 | T8のledger退避・退避原本と同じ取引だけで確定。旧世代の取扱いはT8契約に従う。DI2は再挿入せず退避結果を再掲 |
| 既存D5・同指紋（DI2） | **追加0行・既存行変更0** | ④で保存済み結果を再掲。新たに⑦prepare/C2/原本解決へ進まず、既存原本があっても上書きしない。表現差だけの同内容再送も同様 |
| 既存D5・異指紋（B3b）、O4、B2、後続未処理 | **追加0行** | B3bは先着行と結果を維持、O4/B2はT9を開始しない。前方確定は保持し、後続を勝手に保存しない。再送は既存の各境界に従う |
| `S-STOP`の5限定理由（改訂元不在/不整合/読取失敗/権限失敗/未提供墓標） | `rollback_confirmed`なら当該イベントの業務原本行は**0**。停止/試行の耐久制御記録は別契約 | 当該取引取消/未開始の権威ある確認時だけD5未消費。前方確定は残り、端末は要求全体を未確認保持。自動再送せず、前提回復後の明示再開で同じD1/D5/内容/codec版を再提示 |
| `S-STOP`または通常障害の`commit_unknown` | **0行とも1行とも断定しない** | 業務原本・ledger・eventの確定/取消を耐久照会で解決するまで保持/訂正/再送を推測しない。確定済みなら既存D5はDI2、取消確認済みなら前提再検査後の許可された同内容再開。停止のままなら自動再送禁止 |
| 既存通常B7・保存状態破損・認証/認可拒否・外形拒否 | 原則、新しいT1業務原本行を起こさない**候補**。取引途中の障害は取消確認/commit不明で分ける | B7を一律S-STOPへ変えない。認証/認可前に原本行を作らない。既存台帳破損を新しい未使用D5として再解釈しない。B7の再送可否は既存契約/試行バリアに従う |

同一バッチでは前方の確定行だけ保持し、停止対象の原本・ledger・投影は対象取引の取消確認に従い、後続は未処理とする。原本行の挿入順、競合後の再照合、T8等の全経路で原値をどう引き回すか、保存/読取token・RLS/ACL・物理実装担当はU-S1/U-R1/506の項目別回答まで未確定。原本行を全結果へ一律保存する宣言ではない。
