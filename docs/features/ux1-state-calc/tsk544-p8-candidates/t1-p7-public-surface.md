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

候補の集約署名は`read_t1_context_v1(writer: PortWriter, *, game_id: UUID, generation: int, d1: int, d5: UUID) -> Result[T1AppliedContextV1, T1ContextReadFailureV1]`。`T1AppliedContextV1`は上記4値と、認可済みtenant/game・現世代/D1/D5・同transactionの版印を含む**一イベント限定の不変値**とする。`writer`は適用核発行のものだけを受け、T1からSession/任意SQLを注入しない。読取不能・破損・参照不足は入力内容拒否へ丸めない。4値それぞれの実token、返却フィールド/版、RLS/ACLと同scope寿命は所有側の回答後に確定する。Port完成SHA・実DB試験は実装後ゲートである。

**評価と拒否の候補責任**: U-X1の`prepare_t1_v1(raw_event, context) -> Result[T1PreparedEvaluationV1, T1ContentRejectionV1]`は⑦で元のタグ付きPlayerRefを使い、J6/OUT3/RBI等の内容に限って拒否する。C2未解決を⑦の内容拒否へ変えない。U-S1はT5/O4後、C2とassigned D2を得た時に`assert_t1_equivalent_v1(prepared, projected_event, context) -> Result[None, T1EquivalenceFailureV1]`で、①同一scopeの一時/正式IDが同じ選手、②D2の番号変更が同じ論理位置/前状態を保持、③規則/名簿/前状態/prefixが同じ版、④元eventのD5指紋と`HomeTouchOrderV1`の順序が不変、を検証してT4に同じprepared値を渡す。T4で再計算して差を隠さない。同値が証明できない場合は書込み前に安全側で止める**候補**とし、境界結果・D5消費・保存/復旧操作をU-S1との正式接続契約で分類する。現行⑦内容B3a/T9、O4 B3/新台帳0、C2単独状態依存B7を混ぜない。

**J6原入力の保存候補**: 既存`operation_events.payload/state_diff`は投影後JSON/V8であり元wireではない。`idempotency_ledger`は指紋/結果だけで原wire bytes・codec版・順序の原形を持たない。3種類の結果表へ重複列を加えるより、**新wire経路だけに、tenant+D5を一意キーとする追記専用の原本行**を第一候補とする。候補`T1WireOriginalV1 = {tenant_id, game_id, generation, d1, d5, raw_wire_bytes, wire_codec_version, home_touch_order_raw, source_fingerprint, record_version}`。`raw_wire_bytes`は元wireを損失なく保全し、`home_touch_order_raw`はタグ付き順序を原形で照合する。`HomeTouchOrderV1`の意味版とwire codec/保存record版は別。新wireのD5指紋は承認済みのcodec版+元wire入力の規則に従い、既存DTO経路/保存済み指紋を再解釈しない。受理はledger・原本行・event・T4を同一transactionで、T9に進んだ内容拒否はledger・拒否原本・原本行を同一transactionで保存する候補。0行更新/rollbackなら原本行も0、DI2再掲で再挿入しない。原本読取は同テナント同scopeの登録済み限定resolverだけ、利用者へ表直接INSERT/SELECTを与えない。これは**DDL/RLS/ACL/凍結ゲート前の場所候補**であり、テーブル名・FK/全結果種別・旧行移行・実装担当は未確定。U-S1が取引/接続要件を集約、U-R1がdata-model/ACL/編集境界、506がwire bytes/codec版の供給、544が閉意味型、原本Port/DDLの実装担当は項目別回答で確定する。

各受取担当には、上の該当行を**「受理／修正案（具体型・差分）／担当外（受取先）」**で返してもらう。特に「既存tokenで4値が足りる」という回答には登録箇所・返却型・認可scope・不足時結果の証跡を求める。所有窓口の受理は実Portの実装SHAや結合試験の完了を意味しない。
