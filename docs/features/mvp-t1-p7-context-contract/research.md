# T1/P7文脈契約の最小単位：限定調査

2026-10-24、主担当依頼により新worktree/branchを544固定点から作成した。
この回の編集は本featureのplan/researchだけ。候補schema/d.ts/constructor/純入力case/試験・製品には未着手。

## 基線と規範

- worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-t1-p7-context-contract`。
- branch: `feature/mvp-t1-p7-context-contract`。
- 起点: `7d6ce5443d71f6f7803d2ceed7e04c7ff87422ad`。
- 要件v2.16/ADR-003 v0.9確定: `52625ed6a6d7d27a212acfee16b97c8a97d987a5`。採用済み規範として扱い、T1製品計算未着手とは分ける。
- US1固定入力: `cb0b1601f2ec76265f317e5104d4df387cf44344`の`p7-operational-types.schema.json`と`p7-connection-contract-2026-10-22.md`。
- 上記schemaのSHA256は`4eef9b45e8c5704af7faedd87ac1444876c5a36f0d1cfc5e5790d84fee5cfb68`、接続契約は`62fb599dd84eaf485b722456f3791ec80fb021f754bce9e0fcb38b5d5c4831c1`。
- 544の4値入力候補は`docs/features/tsk544-t1-state-calculation/t1-g6-rbi-review-candidate.md`の99〜108行を必要範囲だけ参照した。
  P6盲検・期待値・原封印の内容は参照しない。

## 既存fieldで閉じる範囲

`ContentRefV1`はcontract ID/contract version/content SHA256、`T1ReadKeyV1`はtenant/game/wire D4/内部世代/D1/D5/business scope/lineage。
`T1ContextRefsV1`はkeyとrules/roster/pre_state/effective_prefixを必須にし、prefix参照にはsnapshot/lineage/before_d1/content_refがある。
これらは未受理外殻の固定入力であり、4意味payloadの正式schemaではない。

prefix全体の完了証拠が必要という意味は既存候補にあるが、具体field/constructorは未閉鎖。
mappingページの`continuation:null`をprefix全体の終端へ転用せず、完了証拠の具体型/sourceは別依存として残す。
規則snapshotのschema/normalizerは単一codec/F-1参照だけにし、独立コピーを作らない。
既採用B+D/除外A、⑦→O4→C2、O4が永続D2重複であること、Ready＋O4の③未証明を維持する。
新resultID/wire/P3/ACK/recovery/PlayerRefタグは本候補で決めない。

## 試験配置・依存の確認

既存`tests/test_state_transition_contract_schema.py`は`schema_checker._validate_instance`を使うroot pytestの試験であり、
`.claude/core-areas.json`の`areas[0].paths`と`areas[1].paths`へ同pathが登録されている。
新testpathは不要だが、これは新候補資産そのもののcore登録を不要にする根拠ではない（第1回レビューで訂正、後述）。
既存helperはrequired/additionalProperties/type/oneOf/const/enum/ref/pattern等を扱うがformatを扱わない。
UUID formatは標準UUID検査を別に行い、未対応キーワードを黙って合格にしない計画とした。
root依存にjsonschemaを新追加したり、backendの未提供依存を仮定したりしない。

readonly d.tsはschemaとのfield/型/readonlyの静的対応を試験する宣言候補であり、実JS artifactの提供や製品TS型適合の証拠ではない。
constructorは今回文書契約までで、構造受理と真正な意味出所/完全性を分離する。完全Ready実装を作らない。

## 起案検証・次のゲート

docs-statusは20文書/違反0、計画同期（base 7d6ce544）はexit0、両文書の空白/NUL/ローカル参照検査は成功。
作業ツリーの新規ファイルは本plan/researchだけ。候補/試験/正式assets・製品への変更なし。
独立計画再レビューと主担当のPO委任判断の後に、改訂planの指示された1ステップだけを実装する。
今回の計画系列を既存544/P7のレビュー回数・正本/正式契約・P6検証へ流用しない。


## 独立計画レビュー第1回・採否と改訂（2026-10-24）

- 対象固定SHA256: plan `cb09059c9136dabc31335a6233115c0a648703d1fe573ada093d5e41bb1b0563`、research `9a3f085c312125554490024d560dc8180af29fe87a37445a5072ac537f5aef4c`。
- 主担当からの第1回結果: **否決、P0=0 / P1=1 / P2=0**。本計画のレビュー回数は1とし、既存544/P7系列の回数は変更しない。
- P1を採用: 実行試験入力となる新candidate schema/d.ts/structure-casesは現core対象外。既存testpathが登録済みでも、それらの後発単独変更ではguardが発火せず、ハーネス6.3 paths規則①に違反する。
- 改訂: 同一planを3ステップへ分けた。①`scripts/core_guard.py`/`tests/test_core_guard.py`で追加層と受理・拒否試験を先行固定、②別コミットで`.claude/core-areas.json`だけに登録、③候補5ファイルと既存構造試験を実装する。不要な番号取得PRは作らない。
- 限定対象は`docs/features/mvp-t1-p7-context-contract/candidate/*`の1globを`game-state`と`sync-protocol`へ各1件。実行3資産に加え、構築境界/source所有の契約も覆い、本featureのplan/research・隣接feature・docs全体には広げない。
- 現guardの領域別二層契約、同一コミットのJSON/基線定義共変更拒否を利用する。従来登録済み追加層は据え置き層として保持してから宣言を回転し、既存paths/guard_paths/領域集合/拒否条件/実在検査を削除・縮小しない。
- 各ステップを緑にするため、先行試験は宣言のみ/登録済みを明示して合成履歴で検証する。未作成候補の実在はステップ1/2に要求せず、実在5ファイル被覆はステップ3で検証する。実JSONに基づく候補5パス各単独変更の未チェック拒否も検証する。
- **改訂反映済み・未再レビュー・未承認**。今回も編集はplan/researchだけで、コード・JSON登録・candidateは未着手。第2回は反映差分と影響節を対象とし、承認済み/指摘解消済みとはまだ扱わない。
- 改訂後の起案検証: docs-statusは20文書/違反0、計画同期（base `7d6ce5443d71f6f7803d2ceed7e04c7ff87422ad`）はexit0。未追跡のplan/research以外に差分なし。実装試験はまだ作成・実行しない。

独立第2回差分/影響レビュー: /root/independent_review、上記plan e02226a2/research2cd2562b、可決0/0/0、初回P1解消。主担当はplan末尾の対象版と日時でPO委任承認。旧counts/留保維持。

固定7d6のJSON未変更でorigin/develop658先端と直接比較する2既存core試験が2failed。差はO5母集合登録1件とguard_paths先端追加で、候補が削除したものではない。rootがplan末尾の日時/理由で2試験の実merge-base比較への限定追随を委任承認。実PR base拒否は変更せず、先端登録保持は統合前の別ゲート。コード反映は未レビューとして最終差分レビューへ渡す。

2026-10-24 00:49 JST記録、全`tests/test_core_guard.py`で276 passed / 8 failed（既報2件込み）を確認。残る6件も同じ先端sync母集団登録1件差であり、主担当/rootはPO委任により同scope内計8件を実merge-base比較へ揃える限定追補を指示した。追加対象はplan末尾に実名列挙した6件。元2件から8件へ拡張した履歴を保持し、失敗を隠さない。固定比較元全paths/順序・許可層以外拒否・旧登録実在を保持し、先端O5の取得済み/正式統合可とは記録しない。実PR guard/JSONは変更せず、統合前に実base登録/guard_paths全保持を照合する。今回差分はステップ1終端の独立コードレビュー待ち。

## ステップ1/3：限定追加層の先行宣言

既存`stage_a_startup.py`が現JSONのgame-state/tenant-isolationへ各1件登録済みであることを照合したうえで、追加層を今回の限定candidate globへ回転した。製品guardの判定関数/拒否条件、JSON、candidate、既存544/P6・正式資産・製品は変更していない。
新試験は候補未実在の宣言状態と登録状態、両領域への帰属、片側登録拒否、限定外非包含、別コミットの宣言→JSON登録、候補5パス各単独変更の未確認拒否/確認済み受理を検証する。旧追加層の登録・実在と拒否試験は保持した。

検証: `uv run pytest tests/test_core_guard.py -n 4 -q`は**284 passed / 10.96s**。root Ruff/ty、docs-status（20文書/違反0）、計画同期、差分空白検査は成功。失敗8件の比較基線是正後、同対象で無関係な失敗はなかった。実JSONの登録や候補作成は未着手で、ステップ1のコード独立レビューへ引き継いで停止する。

## ステップ1の独立受領とステップ2/3の限定JSON登録

2026-10-24 00:54 JST記録、主担当/rootから独立`independent_review`の結果を受領した。対象HEADは`7f8d333e8d7e784a9bdfa4601d98c04c187eff94`、ステップ差分SHA256は`51265295ee9e5351dfce95251c559b08904c5bfd11bcd759c8444f2d139cd62e`に一致し、**可決P0=0/P1=0/P2=0**、独立試験も284 passed / 13.28s。実origin先端との直接比較は未取得O5登録を引き続き拒否し、guardの非緩和も確認された。rootはPO委任でこの範囲を限定受領し、ステップ2のJSON登録だけを許可した。

宣言済み`docs/features/mvp-t1-p7-context-contract/candidate/*`を実JSONのsync-protocol/game-stateへ各1件末尾追加した。旧登録と順序、対象外領域、guard_paths等の全メタデータを保持し、宣言/試験の変更は0。候補の実在は要求せず、`uv run pytest tests/test_core_guard.py -n 4 -q`は**284 passed / 10.52s**、docs-status（20文書/違反0）・計画同期・差分検査が成功した。
この登録は候補schema等の提供、先端O5取得済み、正式7.7/統合可を意味しない。実baseの全登録/guard_paths保持を正式統合前に照合するゲートと未閉鎖意味の留保を維持する。ステップ3のcandidate作成は未着手のまま、別JSONコミットで停止する。

## ステップ3/3：局所外殻候補と構造試験

主担当/rootは`7f8d333e...6c09082b`のJSONを機械比較し、対象2領域への限定glob末尾追加以外の全paths/順序/guard_paths/他field不変を確認してPO委任で限定受領した。独立コードレビューはステップ1の既結果を保持し、最終候補でステップ2/3を含む全直接差分を確認する境界で、ステップ3の実装を許可した。

候補5ファイルと既存`tests/test_state_transition_contract_schema.py`の専用試験を追加した。外殻4定義はUS1固定sourceとの辞書同一性を実照合し、CIでは4定義の固定digestにより別worktree/未統合commitへ依存せず同一性を検査する。readonly宣言のfield/型/必須性と構造25caseを局所検査し、意味出所/同scope/完全性は構造受理から証明できないことをconstructor/source所有文書に残した。規則codecは固定供給点への参照のみ。Ready/3payload/終端証拠/J6タグ/O4新優先/P3新結果/ACK/recoveryは補完していない。

検証: `uv run pytest tests/test_state_transition_contract_schema.py -k p7_context_candidate -n 4 -q`は**51 passed / 0.84s**、`uv run pytest tests/test_core_guard.py -n 4 -q`は**284 passed / 11.49s**。root Ruff/ty、docs-status（20文書/違反0）、計画同期、JSON/宣言/参照・差分空白検査は成功。新候補5ファイルの両core領域被覆と、ステップ2のcore3パス不変を確認した。正式期待値/P6封印・正式contracts・製品・旧544planへ変更せず、局所候補として独立最終レビューへ渡して停止する。T1/P7全成立、先端O5取得済み、正式7.7/統合可の主張はしない。


## ステップ3/3後続の閉payload計画追補起案（2026-10-24）

主担当/rootから、読取結果に基づく最小追補を本plan/researchだけへ起案する指示を受領。起案者はCodex `/root/resolver_ledger_plan_review`。今回は候補作者となるため、この追補の非作者レビューは担当しない。独立計画レビュー/対象版を指定したPO委任承認は未実施。候補5パス/既存試験/core3パス/正式contracts/P6/製品へ変更していない。

### 固定点・読取根拠

- この枝のHEADは`b2b825a4d48dbda34358733680c164f618444557`、開始時clean。先行宣言`7f8d333e`→別JSON`6c09082b`→外殻候補`b2b825a4`の3段階/総数3を維持し、追補はステップ3/3の後続候補範囲とした。
- 既存計画レビュー2回（第1回0/1/0、第2回0/0/0）/採否、ステップ1コードレビュー0/0/0、既存記録の最終候補レビュー待ちを保持する。今回新scopeの計画レビューは未実施。旧544/P7/正本/P6系列へ加算・代用しない。
- 採用済み正本はこの枝の`52625ed6`由来の要件v2.16/ADR v0.9。実統合済みと記録するものではない。file SHA256: 要件`569b761b55f83923d8a6352705bbac3527103d4194a2819a06ac06296ee7060a`、ADR`375900aa9acc7e728cc3e28640418a37c4cd97a5f0de81cad130b74c5599684c`。FR-001/005/007/011/015、付録E-1 J6とF-1を根拠とする。544同固定点`plan.md`§4/step1の全開始条件を保持する。
- 正式`contracts/state-transition/input_axes_descriptor_v1.json`（この枝HEAD）file SHA256 `fab52a2e17ba868ec7f818468241901a2cb12ad98e9cf19c20b52235d184ed56`、記載digest `sha256:5107f929d35ae48e01e25e0410a95235521b778ce53bae945ca5d7e2e956dd57`。`stateTransitionAxes`のstate10軸だけを読取照合。outs/Sは0..2、Bは0..3、打順1..9、half2値、runner occupancy8値、tiebreak/gameEnded booleanを保持。inning/scoreの境界記号は実値範囲そのものとは扱わない。J6はこのdescriptorに正式反映済みとは扱わない。
- 544 `t1-g6-rbi-review-candidate.md`99〜108行の4値payload表は意味候補であって正式型ではない。この枝同file SHA256 `aec0a3d9f60a7d254fad985c088d1be2ca90d9ae1c72f73394991586a3aec7e3`。旧US1接続契約が記録する過去の別版hashと混同しない。
- US1固定`cb0b1601f2ec76265f317e5104d4df387cf44344`の`docs/features/us1-sync-port-surface/p7-connection-contract-2026-10-22.md`§3-1/3-2を照合。既記録schema/接続契約hashを維持。名簿は時点読取、prefixは有限ページ/有効版/変更/墓標の射影、mapping終端は履歴全体の終端ではない。実Port未供給を型具体化の前提にはしない。
- 実develop観測固定`547d199e0c68f3c7d73b6996056cf10ef5fb09fb`の`docs/design/sync-protocol.md`O4/D2段落を照合（file SHA256 `46b61a9a1a6f0ef595631002ca217e353a6ae04df642aee849a6507cca783994`）。従属/同期専用はD2なし、置換旧版は有効集合外、再生順はD2でD1/D4/変更版順ではない。⑦→O4→C2の既定順と新状態拒否との未裁定競合を区別する。本枝へ当該developを取得済みとは記録しない。
- 同developの単一`backend/src/pitchlog/db/game_state/rule_snapshot.py`はfile SHA256 `d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4`で既記録供給点と同一。規則5値キーとruleSetIdの既存6-key保存形への参照だけとし、schema/normalizerを複製しない。

### 具体化と未裁定の境界

採用済みJ6はsnake `runner_id/batter_id`で、1〜4の順序付き一意列と有効候補exact-setが意味要件。PlayerRefタグのliteral/ID格納、版/cursor/manifest/閉参照のDTOは候補として独立レビュー・root委任判断へ送る。prefixの自己申告bool/件数/digestだけでは真正な全有限ページ終端を証明しないため、供給側集合との照合とscope失効までconstructor必要条件に含める。実行constructor/発行証拠/Ready成功は未提供のまま。

guardや正式descriptorを変更せず、外殻4定義と旧caseを保持して同5候補/既存構造試験へ閉型・出所対応・構築不可条件だけを後続具体化する。未閉のoperation/diff参照先を文字列で隠して全意味閉包としない。旧codec移行、Ready+O4や新P3/失敗結果の新意味は別判断としてrootへ返す。正式7.7、23フラグ/OUT3/RBI/G6閉包、P6/P7受理、T1製品着手は未達である。P6封印/著者期待値・所有不明JSONにはアクセスしていない。

起案検証: docs-statusは20文書/違反0、計画同期（base `7d6ce5443d71f6f7803d2ceed7e04c7ff87422ad`）はexit0、`git diff --check`成功。実差分はplan/researchだけ。実装差分がないため構造試験/core試験は再実行せず、後続実装の検証計画として残した。


## ステップ3/3後続：閉payload/J6・prefix構造候補（独立レビュー前）

承認commit `c6f7c1ff96dcbf25e0fc595d6a92b64bcbaf33a3`を基線として実装した。非作者rights_replacement_reviewの限定計画第1回0/0/0とrootのPO委任承認を受領済み。旧計画2回/先行コード/外殻候補の各レビュー実績をリセットしない。今回の作者は`/root/resolver_ledger_plan_review`で、独立レビューを兼任しない。実差分は候補5files・既存schema試験の専用部分・本researchの7filesだけ。plan/core3/正式assets/旧544/P6/製品sourceは変更0。

- 外殻4定義を不変保持して26定義を追加（計30）。J6タグ参照/順序、時点名簿/打順/守備/交代関係、state10軸、原本/参加区分/版関係、有効prefixページ/manifest/一時ID originを閉構造候補にした。正本指定のsnake runner_id/batter_idと1〜4順序列を保持。D2は既存data-modelのsigned bigint値域で、D1/世代や変更版順と分ける。readonly numberは製品ABI/精度保証ではない。
- 旧25caseに新規合成122caseを追加（計147）。構造成功を意味上正常と採点せず、別の11対応でscope/snapshot/版/ページ/終端/manifest/originの相関不成立と出所未検証を区別。合成値の相関診断は試験内だけで、実行constructor/出所/全対象集合/実読了/Readyを提供しない。
- entry.content=`operation-content`、state/entry=`canonical-membership`、mark.application=`half-application-mark`、P3 source.change=`online-change-source`、prefix.replay_window=`undo-replay-diff`、manifest=`prefix-selection`/`prefix-terminal`の7点は**必須unresolved marker**。参照先内容の非提供を明示し、自由JSON/非空文字列で全意味閉包を偽装しない。正負構造試験とsource所有表/constructorの必要条件へ対応した。
- DTO literal/point版/cursor/manifest/版関係の表現は承認済み追補内の候補具体化。旧codec移行、Ready+O4/新状態拒否の競合、新P3/失敗分類は未裁定のまま。単一規則codec/F-1参照のみで複製0。正式7.7/23フラグ/OUT3/RBI/G6閉包/P6/P7/全T1着手条件は未達。実Port/HTTPを契約準備の前提に追加しない。

検証の履歴: 最初の専用実行162 passed / 2.41s。その後に原典/相関/旧保持回帰を追加した実行は192 passed / 2 failed（旧d.tsと新aliasの間の余分な改行によるbyte保持不一致、旧定義名の文書backtick対応不足）。改行を除いて旧byteを保持し、所有表の旧4定義を個別表記に是正した。構造/拒否のskip化や期待hashの付替えはしていない。Ruffは一度E501 4件、tyは一度配列を辿る試験変数の型1件を検出し、限定行折返し/試験変数型の修正で解消。差分検査のEOF余分空行も除いた。

最終検証: `uv run pytest tests/test_state_transition_contract_schema.py -k p7_context_candidate -n 4 -q` **202 passed / 5.04s**、`uv run pytest tests/test_core_guard.py -n 4 -q` **284 passed / 17.44s**。root `uv run ruff check .` / `uv run ty check`成功。docs-statusは20文書/違反0、計画同期（承認base c6f7c1ff）/差分検査成功。候補5ファイル両core領域被覆を既存専用試験で確認し、core3パス自体は変更なし。実DB/HTTP/意味計算/P6検証は実行せず、独立レビュー/正式受理/統合可は未成立として停止する。後続正式化前の実base全登録/guard_paths保持照合はrootへ引き継ぐ。

保持hash（JSONはsort_keys/UTF-8/空白なしの辞書/列射影）: 旧外殻4定義`a6d701ba987ec27a464ac885ee832f27daa8c4123d2de8a75f3cd554184d1a45`、旧25case`40dc00bc02bb8b54ac6f9e12fbf67bb4841931b8fd432fc7f3a15ea396e1b5ab`、旧d.ts byte prefix`fed23638e0ca11f38a5e610705ff9b609dbe33a39504112c849aff82ee9cebbd`。新T1TemporaryOriginV1の辞書hash`ca785c278d9c1b65650b9da72cf8f203eec6df479ed445744308b3de5a2987d0`はUS1 cb0bのT1MappingEvidenceV1と辞書一致を実照合。CIは固定hashを使い、別worktree/未統合commitの存在を要求しない。


## operation-content限定追補の読取根拠・正式整合案（2026-10-24、未承認）

主担当/rootから既存plan/research2文書のみの追補起案を依頼された。起案者はCodex `/root/resolver_ledger_plan_review`（7d80候補作者）で、独立レビューではない。開始HEAD `7d80d3e4a337bcd0639a4d4e7755cda1a4571a28`・cleanを確認。旧3段階/計画2回/前回追補の非作者限定第1回0/0/0・root c6f7承認/7d80の実装・検査/中間失敗を保持する。主担当から旧7d80の既レビュー0を保持する指示を受領しており、その別系列の記録はroot台帳を正とする。今回のoperation-content追補自体は未レビュー/未承認で、候補5files/専用試験/core/正式assets/製品の編集は0。

### 再利用する原典と固定hash

| 固定入力 | SHA256と読み取った範囲 |
| --- | --- |
| 7d80の`contracts/state-transition/state_transition_contract_schema_v1.json` | `9170b82ee91f521f15770e8704f629984519c15052034923072c05a226fd3a0c`。operationPayloadShapeのproperties自体は自由object、historyInputもstack内/differenceを閉じないため、これだけで入力全閉包とはしない |
| 同`state_transition_contract_v1.json` | `54448fcb5b6e598e3610bc77d60a0a3ce1895f8afee8c5361a040f4aff4244bb`。operationRows10行のoperationKind/payloadShape/根拠を照合し、4操作の各重複shapeが一致。operationKind→payloadShape辞書のsort_keys/UTF-8/空白なし正準hashは`1d055470e5f503abb3dbaa218c7448aca551481a69a5ab124100a0fbf21ce34e`。cases/独立期待値は新候補入力へ利用しない |
| 同`input_axes_descriptor_v1.json` | `fab52a2e17ba868ec7f818468241901a2cb12ad98e9cf19c20b52235d184ed56`。event.*のkind、runner別/対象別表現能力、時機valueSchema、RBI/妨害/公式失策の軸を照合。段階2未確定内部制約と、意味/DTO細部を分ける |
| 要件v2.16/ADR v0.9（52625ed6由来、本枝） | それぞれ`569b761b55f83923d8a6352705bbac3527103d4194a2819a06ac06296ee7060a` / `375900aa9acc7e728cc3e28640418a37c4cd97a5f0de81cad130b74c5599684c`。FR-003/004/009/011/015、OUT3/ADV/INT/RBI、付録E-1 J5/J6、D-8/D-11の採用済み意味。本文採用と正式入力schema/7.7の未達を区別 |
| 544 P8候補`t1-input-and-cases.md` / `t1-g6-rbi-review-candidate.md` | 本枝file hash `d3b6251524993b22648083683c5b597f2e57157c838a6240dff7c4b4f1379f5e` / `aec0a3d9f60a7d254fad985c088d1be2ca90d9ae1c72f73394991586a3aec7e3`。観測/所有/未決の候補資料であり、候補のfield名を正式採用済みにはしない。P6の封印/期待値JSONは読まない |
| UF8固定/現eb83787ca5f9e79f94bc773f99e62d74121778cfの`GameScreenPlayObservationTypes.ts` / `GameScreenSubstitutionTypes.ts` | `d2b44676c3aff2d28ee16bc26b34b1c051dae91ff81b722fa032598a4a5f4ad3` / `58a129f17ee7a27d7a1822c065d4d634ceac1e2a76379ccc4092fab4dacfc7ed`。質問/選択肢とraw回答の表示型。正式閉payloadが提供済みとはしない |
| 正式`contracts/vocabulary/vocabulary_manifest_v1.json`が参照する`input_vocabulary_v1.json` | seedの記載contentHash `sha256:0d126947a0cc884a0be731fd9cd12a93b6ce37dfa2bd649fc2ab0094a63955fe`、file byte SHA256 `fd1e445a2c3fad15aee9798ea0e6aa63b90c7c278b235d835aacebd12be56fef`。意味ID/軸の照合元。byte hashと内容hashを同一視せず、表示名をIDにしない |

型名/literal/保存表現の新候補はplan8節へ閉集合として列挙した。既採用fieldを再利用し、不明な観測要否・野球分岐・既存ID移行を候補作者が新しく裁定しない。全kindのoperation-contentが閉じたと称さず、今回対応外のundo/P3等には明示unresolvedを残す。

### FR-015の名前carrierとADR D-8：root後段正本ゲートへ返す最小案

現ADR D-8はoperationRowsのpayload文字列をenum/参照ID等とし「自由記述には用いない」とする。一方、FR-015は選手名・任意背番号で登録し、正式adhoc-registration payloadShapeはname:string/任意uniformNumber:stringを保持する。P8/descriptorもこの文字列規定の整合を段階2へ送っている。この不整合を、型名をOpaqueとするだけ・名前削除・一律enum化・無断の例外追加で解消扱いにはしない。

**正式整合の提案（未採用）**: FR-015の名前/背番号の原値を、型付きの非計算登録carrierとして損失なく保持する。T1の登録操作は既採用の状態中立と不変PlayerRefへの結合だけを評価し、名前によるID同定・文字列計算・T1表示名生成を行わない。D-8へこのcarrierと計算入力/比較面の境界を限定条文化し、D-11のpayload-string-policy-reconciliation/descriptor/入力schemaへ同時に対応させる。raw入力とcarrierの対応/不在は保持し、入力のfield除外や名前を捨てるlossy正規化を認めない。既存player APIの制約を参照する場合も対象版/処理を根拠に固定し、新たな長さ・trim/正規化・既定値を候補で発明しない。利用者への出力エスケープは既存NFR-023のまま。

後段の影響は`docs/adr/ADR-003-domain-calc-method.md` D-8/D-11、必要な要件付録E-1/FR-015への境界参照、正式descriptor/schema/consumer handoffの対応とT2共通digest、必要7.7である。rootが既存正本ゲート/独立確認/PO委任による正式整合判断を追跡して確定する。本候補のstring carrier構造成功を、この正本変更の採用/正式比較面成立としない。

### D2と今回閉じない意味・提供境界

D2についてはdata-model WAIT-03がbigint/gap方式までを採用し、5-3は値自体に意味を持たせず退避値域も許す。採用wire設計L-2はD1/D3だけで、3-4はV6表現を論点26へ送る。実547d199eの`ordering.py`（file SHA256 `37082008c2cfb8c919fea8f6003fdb21890a810e34b187794674695241eeaff9`）の適用経路は0..2^63-1だが、それだけで正本の全構造域を非負に変更しない。wire設計file SHA256 `c2e2ad6f9956277ea98a5a70a02d0d4b7c59f32d429f36aa731087425acd1381`。主担当もこの分離を受領した。旧7d80の負数構造acceptを実constructor/製品受理成功と呼ばず、今回は値域変更0とする。

他6markerは内容/issuer発行・同scope/全有限読取の具体契約を後続で閉じる。自己申告ref/bool/count/digestを証拠にせず、未提供のissuer/読了を成功扱いにしない。旧codec欠落の移行、元scope不明の既存行、新O4優先・新状態拒否/P3公開分岐・一般同値不成立の公的分類はこの追補のDTO具体化と分ける。実Port/HTTP完成を契約準備の前条件へ戻さず、正式7.7/P6/P7/全23フラグ/G6閉包/全T1製品着手を未達として保持する。

起案検証: docs-statusは20文書/違反0、計画同期（base `7d80d3e4a337bcd0639a4d4e7755cda1a4571a28`）はexit0、差分空白検査成功。差分は本plan/researchのみ。候補/試験/製品への変更がないため実装pytestは再実行せず、追補の非作者確認とrootの対象版承認前に実装へ進まない。

### 同ステップ3/3 operation-content実装差分（独立コードレビュー前）

非作者rights_replacement_reviewの限定計画第1回P0/P1/P2=0をrootが受領し、`e703ee43b8a30152e4ae39967265bb2c280c7a84`でPO委任承認した第8節だけを実装した。作者は本候補の継続作者`/root/resolver_ledger_plan_review`で、独立確認を兼ねない。差分は候補5files・既存schema専用試験・本researchの7files。旧3段階/全レビュー・7d80の履歴/中間失敗は保持し、正式source/製品/core3/P6への変更は0。

| 既存読取根拠表への到達差分 | 今回固定した数量と、未充足の数量/境界 |
| --- | --- |
| 正式operationRows4操作 | 10行の4重複除去shapeを辞書同一に対応。宣言13field=必須9/任意4。名前/背番号/任意field不在を保持しD8整合は未採用 |
| 毎球観測と閉union | 新17定義（計47）、毎球11field/8観測群、内容を格納できる5/9 kind。残4kind（undo/P3の3操作）と未供給内容はunresolved。観測要否/相反/同scope/語彙snapshotの実constructorは0提供 |
| 妨害観測の自己点検差分 | 原典INT-02の三塁走者スクイズ/本盗、INT-04の打者走者一塁前という採用済み観測2点を追加具体化。未観測をnone/falseで埋めず、not-requiredと明示観測を別に保持。INT-05の授与先空列＋明示アウト対象は構造で排除せず意味照合へ残す |
| marker 7点 | 完全消去0、operation-content 1点の部分具体化、他6点は未閉。非空ref・空写像・not-requiredを意味受理や真正issuerの代替にしない |
| 原典OUT3/INT/RBIの射影 | 分岐5+7+9=21を参照。今回新たに提供した正式全列case/意味負例/P6導出は0。23flags必要十分表/G6全閉包も未達。候補構造件数を規範成立件数へ読み替えない |
| 構造証拠 | 旧147case/11constructor対応を完全保持、新規合成91構造case（計238）。原典4shape/時機/RBI enum/意味ID・任意field/旧外殻/旧entry/旧29定義/宣言・kind束縛の局所回帰を追加。UF8 adapter/実Port/DB/HTTPは0実装 |

初回局所検査は333 passed / 6 failed。新しいentry合成正例5件の参照digest文字列が形式外だった点を、入力側の64桁hexへ修正し、source所有表の追加17定義未追記1件を追記した。schema拒否や旧case/hashの付替え・skip化は0。次回339 passed / 13.73s。その後原典/optional宣言/残kind/旧定義保持の回帰を追加し、補正前の全専用pytestは**347 passed / 96.71s**（並行検査中）。root Ruff/ty、docs-status20文書/違反0、差分空白検査は成功。

旧4定義/旧25case/旧d.ts byte prefix/US1 originの保持hashは第7d80実績のまま。旧147case正準hash `adc112a559fd15a6469b5a41c38ad4a7e2968226260a754b8979b8b2a2b315fa`、旧11constructor対応正準hash `8c8e666741ea4fcf4c00924f409796abee1e8d7d9e1ade05ed33ffda4b4368b2`、旧entry正準hash `4578cdb4d9167cc14dbb42ab014ea11487cef03b4f702ed0ab47377e0c0d7cb5`、他旧29定義正準hash `3d05206b9fcecdfc441d5885d69494a46f9ea71a2594bf91a663d2d6629134ed`を実照合。専用部分以前の既存schema試験本文・core3は承認baseとbyte一致。D2を非負へ狭めず、旧codec/元scope不明/新拒否競合・D8/namecarrier正式案は未採用のまま、正式7.7/全T1開始/P6/P7受理を代替しない。

core既存全件は**279 passed / 5 failed / 209.06s**で、5件全て既存subprocessの30秒TimeoutExpiredだった（assertion/基線不一致なし）。rootも同時core検査の遅延を観測し、待機指示到着前に既起動だった失敗5件だけの`-n 0`再走は**5 passed / 2.08s**。原失敗を保持し、timeout/guard/旧fixtureを変更せず、全件再走はしていない。上記妨害観測2点/授与先空列の補正後は影響局所（Interference/interference/readonly）だけを`-n 0`で**27 passed / 0.79s**確認した。構造caseはこの3入力追加で計238となり、347という補正前全件件数を最終版全件成功数へ読み替えない。

### operation-content非作者レビューP1の是正（独立再確認前）

rootから非作者rightsのP1を受領し全採用した。対象`7b7620d095ad7e23e92b9f15d0d9ee5dd549f67e`の`T1GameEndPayloadV1 = {}`はTypeScriptで非nullのprimitive/配列/余剰objectを受け、unionのpayload=123も受けるため正式空object/schemaと一致しない。旧350成功というroot受領結果・本系列P1を保持し、作者の構文射影検査だけで実TS適合まで確認したとしない。

実TypeScript 6.0.2の`tsc --strict --noEmit --target ES2020`で、修正前のstring/number/bool/配列/余剰objectとunion数値payloadの受理（exit0）を再現してから是正した。初回プローブは同名.ts/.d.tsによる自己参照importを誤っていたため、typesファイル名を分けて再現し直した。この起動不備を本件の型拒否成功には数えない。宣言を`Readonly<Record<string, never>>`へ変更し、既存局所rendererはproperties空のobjectだけをこの型へ射影する1分岐を追加した。他readonly宣言/旧定義/全case/schema/source所有/constructor・正式契約/製品/coreは変更0。

修正後の実TSは空objectとunion空payloadの正例2件、否定10件（string/number/bool/配列/余剰object/変数経由余剰/null/undefined/union数値/union余剰）を確認。`@ts-expect-error`付きはexit0、注記を除いた同じ否定入力はexit2/診断10件で、無効な型を通して注記だけ消費したとはしない。実プローブ/コピー宣言/結果は`/home/ymdms/.cache/pitchlog/reviews/t1-empty-payload-7b7620d0/`へ保存。before-types SHA256 `feb2f69bcebea65fcd2ac04ff744a8dd614e248444470bc9aefcfbbc8f8a82e3`、after-types `4b1fd92f003b21cb5bc53b82125c743fd745c2963ff78b97c9e71c9f6676e545`、after.ts `bfa97791d655d61e791bcf0241b8c1d75bd78c211543f5f7e885f2d32d6f9f73`、after-negative.ts `cb002fdb162ee443a627edd0146c823cbf02fdcbaf196738f667661a13135b41`。新しいTS製品artifact/runtime/整数ABI全体の適合証拠には広げない。

影響pytestは`-k 'p7_context_candidate and (empty_payload or readonly or closed_operation or operation_shapes or partial_content or prior_definitions or legacy_cases)' -n 0`で**58 passed / 2.98s**。空型renderer・schema値域・{} / object / unknownへの逆戻り拒否を専用試験に追加し、既存宣言照合はexact比較を維持した。root harness CIにfrontend依存を暗黙追加せず、skip/弱化を導入していない。Ruff/ty・差分空白検査成功。新しい重いcore全件は未実行。正式7.7/Ready/P6/P7/T1開始の境界、未閉marker・旧中間失敗・レビュー通算は不変で、本是正は独立再確認前である。


### 残4kindの次単位：V10参照型の限定追補起案（実装前）

rootから3c23の非作者rights限定0（58局所/実TS正例2・負例10）の受領を通知された。7bのP1=1と3c23是正、旧全レビュー・3段階を保持する。第8節は残4kind原本を留保しており、新しいV10閉型/4variantの追加はその実装scope外なので、plan9節だけを起案した。今回の編集はplan/research2files。候補/source/試験/正式shared資産をまだ変更していない。

| 固定出所 | hash/今回使う採用済み部分と限界 |
| --- | --- |
| 観測origin/develop a10bcd5eのsync-protocol | SHA256 `46b61a9a1a6f0ef595631002ca217e353a6ae04df642aee849a6507cca783994`。V10三要素、種別2/10/11/12、undoは対象D2へ従属・P3はD1なし/変更版順/V11必須。新しいO4/P7状態拒否の採否は含めない |
| 同sync-wire-schema/design | SHA256 `c2e2ad6f9956277ea98a5a70a02d0d4b7c59f32d429f36aa731087425acd1381`。L-1/2/3/6、V10のwire名と値域、S-2、3-4のV7/V8/V9/V11内部の留保。旧T1枝のwire文書SHA `dfda134bbd58054e802a6288c990a5d8ddb140837d7b7df0cafcc0096c1eba82`を正式最新として流用しない。該当規約は正式blobで照合した |
| 現branch/同developのsync/change_path.py | SHA256 `6e89708a591050edd39e492d42366df36c67e15468cb459dbe69b57028291cf1`。内部V10=game/d4/d1、期待版のint検査は実経路の事実。wire名・V11の正式物理型の根拠へ昇格させない |

次の候補はV10 wire3field、wire/内部世代対応2field、4kindのV5/V10投影の3定義だけとし、旧entry/contentにはまだ接続しない。V7を空型や任意JSONで埋めず、V11・undo差分/依存・P7D06などの新公開拒否/優先は未提供として残す。これは型/APIの既採用意味内具体化で、既存wire S-2を新S-1へ動かさず、実Port/HTTPを準備待ち条件にしない。

**正式21分岐の実数照合。** 3c23と観測a10の正式state contractはbyte/辞書一致、109case、SHA256 `54448fcb5b6e598e3610bc77d60a0a3ce1895f8afee8c5361a040f4aff4244bb`。branch register/row mapping/manual coverageのメタデータを突合し、期待値やP6封印の導出はしていない。

| 対象 | 既存正式row mapping | missingFixtureBranchesの実件数/ID |
| --- | --- | --- |
| OUT3 5分岐 | 0 | 5: OUT3-01..05 |
| INT 7分岐 | 3: INT-02/04/06 | 4: INT-01/03/05/07 |
| RBI 9分岐 | 3: RBI-06/08/09 | 6: RBI-01/02/03/04/05/07 |
| 合計21 | 6 branch mapping。各rowRefに2case、計12 case参照（全109内） | 15分岐。branchId文字列がcasesに無いことだけで全21不足と数えない |

branch_row_mapping SHA256 `ac9541c860820ac8855a6c72c439d03d8d8bd0d5832a810192f668be90ffef81`、manual_fixture_branch_coverage `f3235b82661a57dee50b9f32ddda44a19ab0fe3120790e946ba0d115c1981564`、clause_branch_register `26098aee10cc23c5585ecdcf68c0ee9244a5f4fd143f1afe456a9c33b39b7637`で全て観測developとbyte一致。case inputにthirdOutTiming/thirdOutObservation/homeTouchOrder/RBI3観測/officialScoringを明示するものは各0。interferenceRuling明示は7case（INT-02相当2/04相当2/06相当2/not-required1）で、閉裁定型の全branch提供を表さない。既存6 mappingを本候補作者の新case成功へ数えず、missing15を勝手に解消しない。今回追加予定も構造caseだけで、正式行/case/P6blind/独立受理の追加は0。

保持対象の正準hashは全47定義 `d1b46a28aec598d265100c9c97c96e38e744d382918aea8315b59223c8e8d9e6`、全238case `1900c78a8a0569ef4797526702a3254d638337144f7554615ec1a3e3efdb6647`、11constructor対応 `8c8e666741ea4fcf4c00924f409796abee1e8d7d9e1ade05ed33ffda4b4368b2`。新3型の構造準備でもoperation-content5/9と7markerは継続する。第9節は非作者確認/対象版root承認前で、今回起案を計算本体着手や正式contract反映としない。

起案検証: docs-status20文書/違反0、計画同期（base3c23）・差分空白検査成功。候補/試験に変更がないためpytestは再実行せず、実装は本追補の独立確認とroot承認・個別指示後とする。

### 第9節のV10参照3閉型を候補実装（同ステップ3/3、正式受理前）

承認コミット`b112a102e05700cfb4af5f661e7d58644c7e4d54`を基線に、plan第9節の3型だけを候補5files/既存専用試験へ追加した。rootの対象版再導出一致とcsv_reviewの新節限定0を承認根拠として受領したが、旧外殻作成関与の開示を保持し、旧全体独立再確認/P6資格へ広げない。本実装は候補作者による作成・検査であり、独立コードレビューはこれからである。

- 定義は47→50。`T1WireTargetReferenceV1`のgame_id/d4/d1（3field）を全必須・余剰拒否/正規小文字UUID/不透明非空文字列/1..2^53−1整数で表す。UUIDの末尾改行/余剰文字・大小文字変換・D4数値化/trim・丸めを許さず、原値を保存する。内部key/D2の域は変更しない。
- `T1ResolvedTargetReferenceV1`はwire参照と既存T1ReadKeyV1同名fieldと辞書同一のinternal_generationの2field。実写像・認可済み同tenant/game/lineage/対象時点・対象版・発行権威/失効は未実装で、構造上の組合せを解決成功としない。
- `T1DependentAddressProjectionV1`は種別文字列2/10/11/12の4variantで、それぞれevent_kind/target_referenceだけを表す。V5/V10の射影で、全envelope/操作内容に昇格させず、D5/V7/P3のV11を不要にしない。旧entry/contentへの参照追加も0。V10 S-2→HTTP入口S-1や公開B14/D5消費/新失敗分類へ前倒ししない。
- 新規合成入力は54（構造accept13/reject41）、238→292。安全整数の両端/上限超過/0/負数/bool/小数/文字列、UUID大文字/コンパクト/括弧/改行/不正字、opaque D4原値、内部正整数域・4tagの型/未知値、必須欠落・余剰を検査する。新型の入れ子欠落/余剰/型違いは既存閉構造の再帰試験も利用する。schema/readonly rendererは既存文法のままで、helper・キーワード対応範囲を広げていない。

保持回帰は旧47定義の正準SHA256 `d1b46a28aec598d265100c9c97c96e38e744d382918aea8315b59223c8e8d9e6`、旧238case `1900c78a8a0569ef4797526702a3254d638337144f7554615ec1a3e3efdb6647`、11constructor対応 `8c8e666741ea4fcf4c00924f409796abee1e8d7d9e1ade05ed33ffda4b4368b2`を照合する。新宣言の前までの旧d.ts全byte SHA256も`4b1fd92f003b21cb5bc53b82125c743fd745c2963ff78b97c9e71c9f6676e545`で固定し、空型Readonly<Record<string, never>>是正を保持する。旧4外殻/25case/147case/旧レビュー・失敗履歴も残す。

局所初回は`-k p7_context_candidate -n 0`で413 passed/2 failed/51.47s。失敗は旧定義総数47の追随漏れとsource表で新型名をfieldまで同じbacktickへ含めた表記漏れであり、50件assert/独立した型名表記へ是正した。該当2件は2 passed/0.84s。skipや拒否条件の削除で緑にせず、他413件の成功とこの初回結果を保持する。

実TS6.0.2の`--strict --noEmit --skipLibCheck`では7つの代入例（wire/対応/4tagと、TSは値域を保証しないことを示す1例）・16の負例を確認した。readonly5箇所、欠落・誤型・数値/未知tag・未知target・射影外fieldを`@ts-expect-error`で照合しexit0、同注記を除去した入力はexit2/診断16件。正規UUID/安全整数/余剰変数の一般拒否/真正性/失効をTS代入から保証しない。実プローブ/コピー宣言/出力は`/home/ymdms/.cache/pitchlog/reviews/t1-v10-b112a102/`へ保存。results.json SHA256 `465c80a5f08355542fdc5360061c5cbded9a738f49828d45b065bf83cd2a60a8`、probe.ts `cdfb5fb2f62e27b16cb38686cd81396267c86d5fd9f8d2ecef09340801813403`、negative.ts `e1857192368ae932ede4e835bf628bb5289231e7425b1a7d83b67ebc0c843d1b`。root pytestへfrontend依存・skipは追加しない。

今回閉じたものはwire V10の3field・内部対応2field・4tagの住所射影という3閉型であり、**operation-content残4kind完全閉包0/7marker消去0**。V7/P3 V11/undo差分・依存/membership/元半回/有限prefix・P7D06等の未採用意味は未供給。operation-content5/9、正式21分岐の既存6mapping/不足15・全23flags/G6/正式7.7/Ready/P6/P7/T1製品計算の未達を保持する。構造fixture生成成功を規範case・P6blind・正式受理へ代替しない。実Port/DB/HTTPを契約準備の前条件に追加しない。

是正後の最終局所全件は同コマンドで**415 passed/282 deselected/41.42s**。最後に加えた旧d.ts全byte保持回帰も含む。Ruff/ty成功、docs-status20文書/違反0、差分空白検査成功。基線はb112承認後、rootがplan冒頭の既成立承認表示だけを整合した`d577bc64`へ進んでいる。本実装はそのplan変更を含めず、候補5files/専用試験/researchの7pathsだけで固定する。重いcore全件・DB・製品本体・正式shared資産・P6封印/期待値には触れていない。計画同期と固定差分/hash・保全物はコミット後に主担当へ返す。
