# 文脈参照・閉payload構造の構築境界候補

この文書は局所契約候補であり、実行constructor・正式schema・登録済みPortの提供ではない。
対応する[schema](context-refs.schema.json)と[readonly宣言](context-refs.d.ts)は、初回のUS1固定外殻4定義を保持する。
第1〜3節は初回の境界、第4節は追加した閉payload構造候補の境界である。完全Ready、Pending/result union、DB読取能力は定義しない。
規範の採用済み範囲と、候補・未提供の範囲は[source所有対応](source-ownership.md)で分ける。

## 1. 構造受理

外殻の必須field、余剰field拒否、string/integer/object、正整数、非空文字列、UUID、digest pattern、内部参照を検査する。
4定義をsourceからそのまま抽出し、新field・上限・既定値・正規化・認可用boolを追加しない。
`T1ContextRefsV1`が外殻schemaの根である。下位3定義も同じschema内で個別に構造検査できる。

既存`schema_checker._validate_instance`はUUID formatを検査しない。
局所試験では別途標準UUID parserとハイフン付き表記の照合を行い、大小文字を許し、入力を書き換えない。
他のformat・未対応キーワードは黙って通さず試験を失敗させる。
これは採用キーワードと合成入力に対する限定試験であり、Draft 2020-12全機能・全数値表現の適合証明ではない。

d.tsは全field必須のreadonly構造宣言である。TypeScriptの構造的代入だけでは余剰field拒否・実値凍結を保証しない。
`number`はschemaのintegerとの静的対応に留め、精度・端末の整数ABI・計算実装を決めない。
試験はschemaと宣言のfield/型/readonlyを静的に照合し、TSコンパイラ・JS実行artifactの提供とは扱わない。

[構造case](structure-cases.json)は全て新規合成値である。`expected_structure`は構造のaccept/rejectだけを示す。
非空のwire D4や、keyとprefixでlineageが異なるcaseが構造上acceptでも、版の一致・真正なsource・意味上の受理は未判定である。
任意のcontract ID/digest文字列がこの検査を通っても、登録済みcontractや実payloadの存在証拠にはならない。

## 2. 構造検査の後にも必要な照合

| 境界 | 必要な照合と所有 | この単位の成果 |
| --- | --- | --- |
| 認可・業務scope | U-S1の発行側が認証tenant/game・内部世代・対象D1/D5・scope/lineageへ束縛する。利用者の任意tenant/refや「検証済み」boolを権威にしない | 条件の参照のみ。token/認可/DB wrapperは実装しない |
| 4sourceの版と参照 | 固定SELECTの供給値と、544/U-X1が受ける意味版・source識別子・内容digestを同scopeで突合する。意味版をwire codec版/保存record版と混同しない | schemaの`contract_id/contract_version/content_sha256`は参照外殻だけ。実在・版受理・digestの再計算対象/符号化はこのschemaから確定しない |
| 時点と正史 | 規則/名簿/投影前状態/有効prefixを同時点・同系譜の証拠へ結ぶ。現在名簿・C2投影後状態・旧系譜を代用しない | 対象D1に対する`before_d1`の具体相関、閉payload/供給証拠の受理は各所有側の残件。schemaへ新しい等号制約を発明しない |
| prefix完全性 | 対象の全有限ページが同scope/版で読み終わった証拠を必要とする。D3や部分ページでは代用しない | `snapshot_id/lineage/before_d1/content_ref`だけでは全履歴終端のexact証拠にならない。`complete:true`や新fieldを追加しない |
| 一時IDとC2 | 実prefix内のoriginと受理ledger/event/map、同一名簿を突合し、C2後も同じ証拠で再照合する | PlayerRef/J6の正式タグ、originの実保存/読取契約は別依存。写像ページの`continuation:null`を履歴全体の終端へ流用しない |
| 不変性・失効 | U-S1の同業務scope終了、例外、rollback/commit、fence喪失、別イベントへの移行で読取能力を失効させる。意味核へ渡す値は不変にする | readonly宣言を実凍結や失効検証済みの証拠にしない。DB handle/Session/SQL/書込token/callbackを意味核へ渡さない |

参照と内容が一致するという呼出者の自己申告では、これらの照合を完了できない。
出所の突合には供給者が発行した同scopeの読取証拠が必要であり、任意refやdigestの形式一致だけで真正性を認定しない。
raw event、payloadの保存、D5消費、投影更新、読取token発行、commit/rollbackはpure prepareの責務へ持ち込まない。

## 3. 未閉鎖依存と既採用意味

規則snapshotはF-1と既存単一保存codecへの参照だけを使い、schema/normalizer/計算をコピーしない。
時点名簿、投影前状態、有効prefixの3payloadと履歴全体の終端証拠、PlayerRefタグは未閉鎖である。
これらを自由JSON/`any/object`や省略可能fieldで穴埋めしない。
閉payloadと真正な出所/完全性の受理前には、外殻の構造成功を完全Readyへ変換できない。この候補はReadyを公開しない。

既採用B+Dとundo依存交代除外A、⑦→O4→C2、DI2/DI3、P3既定順を維持する。
O4は希望D2の1行占有ではなく永続D2重複であり、完全Ready＋O4は必要契約未閉鎖の③未証明のままである。
新D2検査を前置きして優先を決めない。新resultID/wire、未裁定O4競合、P3新結果、ACK/recoveryは本単位で補完しない。
実Port/DB/HTTP成功をこの局所候補整備の前条件にしない。正式contracts/7.7/P6盲検・期待値・原封印の受理にも読み替えない。

## 4. 閉payload構造候補への後続（ステップ3/3、未正式受理）

前節までの外殻4定義は初回成果として保持する。本後続は同schemaへ別定義を追加した候補で、根は従来の`T1ContextRefsV1`のままである。`T1RosterAtEventV1`、`T1PreStateV1`、`T1EffectivePrefixV1`を構造検査できるが、正式T1入力/Ready unionや実行constructorは提供しない。source対応と未閉鎖fieldは[source所有表](source-ownership.md)第4/5節による。

`PlayerRefV1`の`official/player_id`・`temporary/temporary_id`、UUIDで表すcontent版/cursor、`point`/`manifest`/`version_relation`等は今回のDTO候補である。IDの文字列がUUIDでもtenant/game/teamへの帰属は証明しない。J6のScorerRefだけは正本のsnake `runner_id/batter_id`に従う。1〜4の順序付き一意列を保持し、入力をsort/正規化しない。JSONとして異なるID大文字小文字、runnerとbatterのタグ違い、temporary/official写像の別名は`uniqueItems`だけでは人物同一性を検査できない。実際の有効候補exact-set・人物の重複・攻撃側/出場者/scope・OUT3後の有効性は同scopeの意味照合が必要であり、実装していない。

### 後続constructorに必要な条件（実装未提供）

以下のIDは局所文書の照合項目であり、新しい公開結果ID・拒否順・ACKではない。試験の相関診断も合成値上の構造照合だけで、これらの実証/認可を代行しない。

| 条件ID | 必要な照合・構築できない条件 |
| --- | --- |
| `SCOPE` | 4source/全ページ/manifestが同じ認可済みkeyのtenant/game、原wire D4、内部世代、対象D1/D5、business scope/lineageへ束縛される。keyを書き合わせた自己申告だけでは不足。prefixの過去event自身のD4/世代/D1を現在keyへ書換えない。正史は世代を連結する |
| `SNAPSHOT` | pages/manifestのprefix参照（snapshot/lineage/before_d1/content_ref）が対象prefixと同一で、内容と供給sourceが一致。`before_d1`は外殻の読取境界参照であり、D1順を論理再生順にしたり、全entryのD1が対象値未満なら完了と推定したりしない。境界選択のexact規則は`prefix-selection`の未閉鎖依存 |
| `VERSION` | content_versionを同じ固定snapshot内の同版へ束縛する。名簿point版とpre_state.roster_version、state/source参照、規則保存値を突合。版UUIDはDTO候補で単調増加やwire/record版の代替を意味しない。異版混在やC2後の状態を⑦のpre_stateとして渡さない |
| `PAGE-CHAIN` | 空prefixも最低1ページ。先頭index0/start、以降indexに抜け/重複なし、前のnextと次のcursorが一致して循環せず、非最終はcontinue。重複/欠落/別cursorの再利用/先頭不在は構築不可。page_index/cursorは読取列であってD1/D2/変更版順ではない |
| `TERMINAL` | 最終だけendで、供給者の全対象集合を読了した終端証拠と一致。最終ページがcontinue、途中でend、全対象集合を読む前の打切りは不可。mappingのcontinuation=null、D3、complete:true、件数/digestの自己申告を代用しない |
| `MANIFEST` | 実読取全ページのdescriptor列がmanifest全列とexact一致し、各page_refがその実内容に束縛される。manifest自体と選択/終端証拠が同scopeの供給者から真正に発行されたことが必要。ページとmanifestを両方改ざんして一致させても証拠にはならない |
| `ORIGIN` | 一時IDごとにUS1固定候補のmapping_id/temporary_id/player_id、origin_game/内部世代/D1/D5、accepted ledger、fingerprint/record版を実原本・受理ledger・登録event・同時点名簿/有効prefixへ突合する。既存US1候補のorigin同game/内部世代・先行D1条件を維持し、その正式受理/旧行補強は別依存。値の一致だけでacceptedを自己認定しない。C2後も同じ証拠で再照合 |
| `PROVENANCE` | 各参照のcontract/source/意味版/digestの受理・実内容・読取権威・失効を供給側証拠から確認する。前の相関が全て一致しても、現在の候補には真正な発行証拠/実読了/全選択集合との一致の実装がない。unresolvedを含む合成値をReadyへ変換できない |
| `ROSTER` | home/away各1、team/participant/打順の帰属、同一打順枠重複、交代の有効時点・元選手・DH関係を同prefixで照合。9守備位置不足はFR-011の警告であり、このDTOのroles空列や不足を新拒否にしない。二つのside/IDが構造上正しくても本当にその試合のチーム/名簿とは限らない |
| `PARTICIPATION` | original/revisionの毎球/交代/TB開始/終了宣言はown-d2、undo/オンライン変更はdependent、その場登録はsync-only、tombstoneは自身のD2なし。変更はD1なし・自身のD2なしで対象の位置へ従う。元の操作種別とrevision/tombstoneの版関係を別に持ち、旧版監査や旧拒否D5を現membershipへ混ぜない。D2=bigintは変動する位置値であり内容版/不変IDではない |

`structure-cases.json.constructor_cases`は構造がacceptでも上記条件を満たしたと採点できない入力を対応付ける。既存専用試験内の`_p7_context_candidate_prefix_shape_issues`はkey/snapshot/版/cursor列/manifest列とoriginの数値関係の相関だけを診断する。外部データ読取・発行検証・意味計算・Ready返却は一切行わず、相関問題0でも`PROVENANCE`は未成立である。二頁の構造成功も実有限prefixの完全読了ではない。

### 未閉鎖fieldを隠さない

- entry.contentの`operation-content`、entry/stateの`canonical-membership`、半回印の`half-application-mark`、P3 sourceの`online-change-source`、prefix.replay_windowの`undo-replay-diff`、manifestの`prefix-selection`/`prefix-terminal`は、必須の`{kind:"unresolved", obligation:閉literal, source:ContentRefV1}`という**依存marker**である。実内容の代替値ではなく、これがある限り全意味閉包は成立しない。空配列や参照文字列の形を理由にこれらを成立扱いにしない。
- operation_kindは採用済み操作分類を区別するDTO候補で、revision/tombstoneを独立の新ドメイン操作へ昇格させない。version_relationのreplaces参照だけで再実行/取消差分・版連鎖が証明されたとはしない。
- 閉型・観測と全23フラグ/OUT3/RBI/G6-Sの規範行/負例、正式descriptor/T2/7.7、P6/P7項目別受理は別の未達である。実Port/HTTP/DB完成を契約準備の前提には追加せず、製品計算の全開始ゲートも縮小しない。⑦→O4→C2/B+D/除外Aを保持し、Ready+O4/新状態拒否の競合/P3新結果/旧codec移行をここで裁定しない。

## 5. 操作内容の閉union候補への接合（ステップ3/3、未正式受理）

第1〜4節は旧外殻/7d80候補の境界として保持する。今回の17追加定義はsource所有表第6節に対応し、5kind（毎球/交代/TB開始/終了宣言/その場登録）の閉内容を表せる。T1EffectiveEntryV1の旧未供給variantは保持し、供給されたcontent.kindとoperation_kindが一致する追加variantだけを受ける。kind不一致、自由JSON、未宣言field、必須欠落は構造拒否である。旧markerを受ける入力が依然構造acceptでも、その内容が供給済みとは判定しない。

正式4操作のraw payloadShapeの任意fieldと、採用済みrunner-keyed写像は不在を保持する。d.tsではこの限定集合だけがreadonly任意fieldとなり、旧4外殻の全必須条件は不変である。空name/背番号、任意field未指定、not-required、未指定runnerを削除/既定値補完/trim/観測falseに正規化しない。D8/namecarrier整合案は未採用であり、正式比較面の例外や計算開始許可ではない。

| 照合項目 | 後続constructor/正式規範行で必要な条件（実装未提供） |
| --- | --- |
| 操作原本 | 4shapeのID/PlayerRef対応・一時IDの真正origin・同scope/時点/適用名簿、交代の元/先/打順/守備/DH、TB snapshot/印/発動条件、終了宣言のGiven。既存optional fieldの欠落を新たな成功値にしない |
| 語彙snapshot | 固定版の意味ID/有効化/分類とraw入力とのlossless対応。表示名や任意質問IDを意味IDと同一視しない。runner statusの起点prefix/各out-kind・実際の在塁選手との一致を確認する |
| runner観測 | event_kindとkind、起点キー/PlayerRef/結果・到達/企図塁、変更対象の必要非空/一意・在塁/到達可能性、同一人物の相反や越境を確認。写像が空/形式一致というだけで確定しない。重複raw JSONキーは506のparse前責任で、parse済み入力の本候補へ検出済み扱いで流用しない |
| 第3アウト/J6 | thirdOutObservationの要否/種類/対象を実アウト・同scopeへ照合し、OUT3-01..03例外外の有効候補exact-setへ2値の時機を要求する。noneを未観測の代わりにせず、同時はnot-before-third-out。前位関係は選手/起点と適用prefixから導出。J6はOUT3後の有効候補exact-set/順序を同scopeで確認し、構造uniqueItemsだけで人物同一性を認定しない |
| 妨害/失策 | 採用結果だけをINT-01..07へ対応し、授与/帰塁/アウトの必要全対象、矛盾・重複・帰属、通常結果の有効性と失策件数/野手の整合を確認する。未観測の裁定・失策なしを推定しない |
| RBI/23flags | OUT3/サヨナラ上限後の計上得点者へRBI-01..09を適用し、先行分岐を除外した上で必要な走者別継続/失策なし得点可否・併殺送球失策の観測を要求する。23キーの導出元/必要十分条件/負例は未閉で入力にflagsを追加しない |

構造caseの追加91件は合成入力だけで、規範分岐の正常/拒否出力や実出所を採点しない。旧147case/11constructor対応/4外殻digestを保持する。OUT3の5分岐、INTの7分岐、RBIの9分岐は原典の意味を参照するが、それら21分岐の正式全列case/負例を本候補が新たに供給した件数は0である。構造入力の生成件数を規範/独立P6成立件数へ読み替えない。

operation-contentは5/9 kindの内容を表す候補になったが、未供給状態・残4kind・他6markerは継続する。出所発行/有限読了/実constructor、正式descriptor/T2/7.7・23flags/G6閉包/P6/P7は未達で、完全Ready・製品T1計算・実画面入力の全接続は提供していない。実Port/DB/HTTP完成を契約準備の開始条件に追加しない。

## 6. V10対象参照の構造と解決権威を分離する後続候補

plan第9節の承認b112a102に基づき、`T1WireTargetReferenceV1`・`T1ResolvedTargetReferenceV1`・`T1DependentAddressProjectionV1`を追加する。既存47定義/entry/content/7marker/構築条件は変更しない。wire参照は全必須のgame_id/d4/d1で、正規小文字UUID・非空不透明D4・1..2^53−1の整数D1を構造検査する。大小文字変換、D4数値化/trim、整数丸めはしない。既存内部key/D2の域は狭めない。

`T1ResolvedTargetReferenceV1`はwire参照と既存内部世代の二つを並べるDTO候補で、名称や入力値の一致だけで解決済みを表明できない。供給者の実写像、対象event/版、認可済み同tenant/game/lineage/対象時点、失効していない読取権威への束縛が別途必要である。このconstructor/実発行検証は未提供で、合成入力ではどの正整数とD4の組も構造上表せる。schema成功を実写像・同scope成功へ昇格しない。

種別2/10/11/12の文字列tagとtarget_referenceを持つ`T1DependentAddressProjectionV1`はV5/V10だけの射影である。D5/V7/P3のV11等が不要になった全イベント型ではなく、同型へpayload等を追加すると構造rejectになることも、実wireがそれらを拒否する証拠ではない。V10は既存S-2段階の値であり、本試験からHTTP入口のS-1拒否・公開B14・D5消費・新undo失敗分類を作らない。

今回追加54caseは構造正負だけで、4操作のV7/P3 V11/undo差分・全依存集合やmembership/元半回/有限prefix・P7D06等の新結果/優先順を供給しない。operation-contentは5/9、残4kindの完全閉包追加0、7marker消去0。正式21分岐の既存6mapping/未供給15・全23flags/G6/P6/P7/7.7・Ready/T1製品計算の未達を保持する。実Port/HTTP/DB完成をこの型準備の前条件に追加しない。

## 7. 純入力packetと作者資料を分離する（第10節後続、未正式受理）

`candidate/t1-pure-inputs-v1.json`は中立format版と中立input IDの2件に、規則保存値5field/両側時点名簿/投影前状態10field/毎球の実観測だけを持つ。入力差はthirdOutTimingByRunner.thirdの2値だけ。期待値・branch・採否・作者case名/説明・作者資料への参照/hashを入れない。型/原値/同じGivenの相関を局所検査するが、真正出所/有限prefix/Readyや製品Portの成功とはしない。必要時機を外すローカル変異は、この固定Givenへの観測不足として検出するもので、新しい製品エラー型/公開拒否ではない。

`candidate/t1-author-derived-v1.json`は同IDの作者側期待値・branch対応/対向例・原典/source hash・理由・未解決fieldを別に固定する。全6比較key/23flagを列挙しても、既定進塁2fieldと正式row bindingが未提供のためformal completeではない。単打の現正式代表行から与えられていない走者配置を補完したり、実overrideを既定値の根拠にしない。実適用結果とmatrixの既定効果も同じ値としてまとめない。作者が導出した結果を独立比較/P6blindと称さない。

将来の新blindへは、rootが純入力fileの内容だけを独立した場所の中立名`inputs.json`へbyte同一でコピーし、その内容hash、採用済み規範原典、対象版・範囲だけを渡す。本ディレクトリの参照権/全体bundle/作者JSON/plan/research/本会話/branch mapping/比較資料は渡さない。候補作者と本会話を継承しない未曝露検証者が結果を封印してhashを固定した後に、rootが作者資料との比較を行う。新しいエージェントであることや期待値fileを削除することだけでは未曝露を証明しない。本単位は入力を準備しただけで、その検証者起動/封印/資格確認/正式受理を実施していない。

## 8. RBI因果観測と23flag条件の有限域（§11、実constructor未提供）

この後続は新観測契約/条件表/合成純入力v2/分離作者資料v3の4fileだけを追加する。旧50定義と3つの既版packet/評価は不変。7つの新閉型（`T1RbiCauseValueV1`、`T1RbiRestartValueV1`、`T1RbiCauseMapV1`、`T1RbiRestartMapV1`、`T1RbiCauseByRunnerV1`、`T1RbiRestartByRunnerV1`、`T1RbiMisplayObservationsV1`）の出所はsource所有表§9と新観測契約のterms/correlationsによる。person参照の形式だけで実tenant/game/issuerの権威を与えず、別scope値は実constructorで拒否する責務を残す。

純入力v2のcommon_inputは規則/名簿/状態/毎球の固定Givenで、変動するthirdOutTimingByRunnerとrbi.runnerContinuityByRunnerを含めない。各entryのper_pitch_observationsの2fieldをその同名位置へ明示代入すると旧毎球型になる。rbi_misplay_observationsは旧型の外の新候補sidecarで、cause_by_runner/restart_by_runnerを別保持する。これは2箇所の明示結合であり、任意patch/normalizer/保存codec/製品ABIではない。元の観測不在とfalseを正規化せず、pure内に判定・branch・期待値・作者資料への参照/hashを入れない。

同一走者がOUT3後のRBI入力域に入るときだけ因果観測を必要とし、因果があるときは既存継続観測、停止再発進ならそのミスプレイを見た再発進かを必要とする。得点無効なら観測欠落を新拒否にしない。継続とrestart true、因果なしの明示と当該restart trueという正の相反や、同じrunner-keyの別人への差替えは入力issueとして記録する。複数issueを同時に保持しても公開拒否優先順は作らず、D06の判断にしない。

構造90セルは正常90プレイを意味しない。作者表のcomplete-in-domainも、D内の必要観測と条件表の対象という意味で、実開始/適用成功/Ready/正式T1 caseではない。必要観測不足/相反があれば完全23flagを出さず、部分既知得点と判定できない面を分離する。作者の26反転負例は宣言した正常rowから1flagだけを反転した比較資料で、その一致検査だけで野球意味の正しさを保証しない。原典非作者確認/将来の独立導出と正式受理は別に必要である。

D外の20定数keyの反対条件witness、他結果/操作の全23条件、既定進塁/D07、公開拒否/D06、scoreboard絶対値/完全履歴/製品打順ABI、全7marker/G6/P2/P6/P7/P8/7.7は未提供のまま。unknown解消数はDoDではなく、新候補を正式missing15削減や本体着手の成立根拠にしない。将来blindへの切出しは第7節と同じく純入力だけとし、作者条件表/判定資料/会話を渡さない。本単位では新blindを起動しない。

本候補は両因果booleanを観測済みのprofileに限定される。片側true/他側未観測はOR成立の証拠にはなるが、この閉型では未表現なので、製品DTOとしての必須入力を確定したとはしない。q0004/q0005のように複数の可能な分岐が同じ打点数を返す場合は、完全branch-case不足でも数値の既知部分を失わない。作者表/入力issueは一般のT1拒否に直結できず、最小観測型の後続具体化は別の限定scopeとして受ける。新意味・既存値補完でこの差を消さない。
