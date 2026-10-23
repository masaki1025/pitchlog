# 文脈参照外殻のsourceと所有対応候補

## 1. 固定入力と受理状態

| 固定入力 | 状態・この候補での用途 |
| --- | --- |
| TSK544基線 `7d6ce5443d71f6f7803d2ceed7e04c7ff87422ad` | このbranchの起点。旧plan/レビュー回数・P6資産を変更しない |
| 正本確定 `52625ed6a6d7d27a212acfee16b97c8a97d987a5`、`docs/requirements/requirements-pitchlog-2026-07-22.md` v2.16、`docs/adr/ADR-003-domain-calc-method.md` v0.9 | 採用済み規範。B+D/除外A・単一計算の規範採用と、T1製品計算の未着手を区別する |
| US1 `cb0b1601f2ec76265f317e5104d4df387cf44344`、`docs/features/us1-sync-port-surface/p7-operational-types.schema.json` | 未受理の外殻候補。4定義だけを同一内容で抽出。file SHA256 `4eef9b45e8c5704af7faedd87ac1444876c5a36f0d1cfc5e5790d84fee5cfb68` |
| 同US1固定点の`p7-connection-contract-2026-10-22.md` §2・3-1〜3-3 | 所有/固定読取/同scopeと失効/未閉鎖境界の候補。file SHA256 `62fb599dd84eaf485b722456f3791ec80fb021f754bce9e0fcb38b5d5c4831c1`。新CAP/署名/ACLの正式受理ではない |
| TSK544同固定点、`docs/features/tsk544-t1-state-calculation/t1-g6-rbi-review-candidate.md`の99〜108行 | 4値の意味入力候補とReadyにできない条件のみ参照。後続のP6/期待値等は参照しない |
| 単一規則codec供給点 `bc436803902a9cde2b54e6a72636acbe522e9e20`、`backend/src/pitchlog/db/game_state/rule_snapshot.py` | 既存F-1 schema参照の保存codec。参照のみとし本候補へ実装をコピーしない。file SHA256 `d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4`。本枝に供給済み/統合済みとする記録ではない |

候補schemaの`$defs`は`ContentRefV1/T1ReadKeyV1/PrefixEvidenceRefV1/T1ContextRefsV1`の4件だけである。
JSONをキー順ソート・UTF-8・空白なしで直列化した4定義のSHA256は`a6d701ba987ec27a464ac885ee832f27daa8c4123d2de8a75f3cd554184d1a45`。
試験はこの局所抽出の同一性を固定し、CIで別worktreeや未統合commitの読取を要求しない。
正式供給型をforkする宣言ではなく、後続の正式化では所有側の受理済み資源を単一参照する必要がある。

## 2. 公開fieldの対応

以下のfield構造は全て上記US1固定schemaの同名`$defs`が出所であり、実値・供給能力の提供済みを表さない。

| 候補型・field | 意味の出所と供給責任 | 消費側/留保 |
| --- | --- | --- |
| `ContentRefV1.contract_id` | U-S1読取値が参照する、544/U-X1意味型のsource識別子 | 544/U-X1が選択した契約との対応が必要。任意IDの非空性だけでは登録を証明しない |
| `ContentRefV1.contract_version` | 同sourceの意味版 | 544/U-X1が受ける意味版を照合。wire codec版/保存record版ではない |
| `ContentRefV1.content_sha256` | 同source内容のdigest参照 | 形式のみがschema対象。内容の存在・算出対象/符号化・真正性は供給/消費の閉契約に依存 |
| `T1ReadKeyV1.tenant_id/game_id` | U-S1が認証/認可済み業務scopeから固定する対象 | 任意tenant/game入力を権威にしない。544意味核には値だけを渡す |
| `T1ReadKeyV1.wire_d4/internal_generation` | U-S1の原wire世代文字列と、別の内部世代整数 | 同一型・相互の代替にしない。変換規則を追加しない |
| `T1ReadKeyV1.d1/d5` | U-S1の対象イベント連番/要求識別子 | 既存D1/D5段階に束縛する。新要求やD5消費をconstructorで実行しない |
| `T1ReadKeyV1.business_scope_id/canonical_lineage_id` | U-S1の同業務scope/現正史系譜の識別 | 544は他4値の時点/版と照合する。UUID形式だけでscopeが実在・有効とはしない |
| `PrefixEvidenceRefV1.snapshot_id/canonical_lineage_id` | U-S1が供給する対象prefix snapshot/系譜の参照 | 544有効prefix意味型と同scope/版で束縛。旧系譜や現在状態の代用不可 |
| `PrefixEvidenceRefV1.before_d1` | US1外殻に既存の対象prefix境界 | 正整数の構造だけ。keyとの具体相関や終端証拠を新しく決めない |
| `PrefixEvidenceRefV1.content_ref` | 同prefixの`ContentRefV1` | snapshot参照だけでは履歴全体の完全読了を証明しない |
| `T1ContextRefsV1.key` | 同じ`T1ReadKeyV1` | 4sourceを同scopeへ束縛するための外殻。認可能力ではない |
| `T1ContextRefsV1.rules` | 保存済み`games.applied_rules`のF-1、既存単一codec供給側/U-S1固定読取、544意味型 | live設定から再導出しない。本候補には規則値schema/codecをコピーしない |
| `T1ContextRefsV1.roster` | 時点のteam別出場/打順/守備・交代。544/交代所有側が意味を閉じ、U-S1が固定読取を供給する候補 | payload exact schema/PlayerRefタグは未閉鎖。現在players一覧だけで代替しない |
| `T1ContextRefsV1.pre_state` | 同時点の投影前状態と状態版。544/U-X1が意味を閉じ、U-S1が固定読取を供給する候補 | payload exact schemaは未閉鎖。C2投影後の状態を代用しない |
| `T1ContextRefsV1.effective_prefix` | 有効先行履歴・系譜・origin・完了証拠。544が意味を閉じ、U-S1が同scopeの有限ページ読取を供給する候補 | payload/全履歴終端のexact証拠は未閉鎖。mappingページの終端/D3を代用しない |

## 3. 所有と後続依存

U-S1は固定読取・証拠供給/保存と能力の設計責任、544/U-X1はT1閉意味型/純粋評価/依存集合の責任を持つ候補境界である。
HTTP/wire/ACK/queueは506、画面の観測保持はU-F8、認可の実role/CAP/ACLは認可所有側の受理に依存する。
本単位はそれらの実装や署名を引き取らず、未閉鎖事項を自己申告ref/boolで代替しない。

3payload・prefix全体の終端証拠・J6 PlayerRefタグ・新resultID/wire・未裁定O4競合/P3新結果/ACK/recoveryは別依存のまま残す。
新意味fieldが必要と判明したらその単位へ分け、既存型に合わないfieldを本候補へ追加しない。
この候補整備の合格はT1/P7完了、正式contracts/7.7、実Port/DB/HTTP、独立P6の受理ではない。
