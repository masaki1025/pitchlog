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
