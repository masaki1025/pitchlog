# 文脈参照外殻の構築境界候補

この文書は局所契約候補であり、実行constructor・正式schema・登録済みPortの提供ではない。
対応する[外殻schema](context-refs.schema.json)と[readonly宣言](context-refs.d.ts)は、US1固定候補の4定義だけを表す。
4値payload、完全Ready、Pending/result union、DB読取能力を定義しない。
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
