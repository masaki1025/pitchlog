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
