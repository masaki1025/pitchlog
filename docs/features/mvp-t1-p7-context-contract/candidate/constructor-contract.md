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
