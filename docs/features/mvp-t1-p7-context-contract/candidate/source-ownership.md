# 文脈参照・閉payload構造のsourceと所有対応候補

## 1. 固定入力と受理状態

| 固定入力 | 状態・この候補での用途 |
| --- | --- |
| TSK544基線 `7d6ce5443d71f6f7803d2ceed7e04c7ff87422ad` | このbranchの起点。旧plan/レビュー回数・P6資産を変更しない |
| 正本確定 `52625ed6a6d7d27a212acfee16b97c8a97d987a5`、`docs/requirements/requirements-pitchlog-2026-07-22.md` v2.16、`docs/adr/ADR-003-domain-calc-method.md` v0.9 | 採用済み規範。B+D/除外A・単一計算の規範採用と、T1製品計算の未着手を区別する |
| US1 `cb0b1601f2ec76265f317e5104d4df387cf44344`、`docs/features/us1-sync-port-surface/p7-operational-types.schema.json` | 未受理の外殻候補。4定義だけを同一内容で抽出。file SHA256 `4eef9b45e8c5704af7faedd87ac1444876c5a36f0d1cfc5e5790d84fee5cfb68` |
| 同US1固定点の`p7-connection-contract-2026-10-22.md` §2・3-1〜3-3 | 所有/固定読取/同scopeと失効/未閉鎖境界の候補。file SHA256 `62fb599dd84eaf485b722456f3791ec80fb021f754bce9e0fcb38b5d5c4831c1`。新CAP/署名/ACLの正式受理ではない |
| TSK544同固定点、`docs/features/tsk544-t1-state-calculation/t1-g6-rbi-review-candidate.md`の99〜108行 | 4値の意味入力候補とReadyにできない条件のみ参照。後続のP6/期待値等は参照しない |
| 単一規則codec供給点 `bc436803902a9cde2b54e6a72636acbe522e9e20`、`backend/src/pitchlog/db/game_state/rule_snapshot.py` | 既存F-1 schema参照の保存codec。参照のみとし本候補へ実装をコピーしない。file SHA256 `d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4`。本枝に供給済み/統合済みとする記録ではない |

初回候補`b2b825a4`の`$defs`は`ContentRefV1/T1ReadKeyV1/PrefixEvidenceRefV1/T1ContextRefsV1`の4件だけであった。本後続で4件を不変に保持し、第4節の別定義を追加した。
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

## 4. 後続候補の各field群・採用状態

初回の`ContentRefV1`、`T1ReadKeyV1`、`PrefixEvidenceRefV1`、`T1ContextRefsV1`の4定義/同一性digestは保持し、後続26定義を同じschemaの別`$defs`へ追加した。根の外殻受理を変更しない。意味の根拠は次の固定sourceで、DTO表現自体は正式契約に未採用である。

- 要件/ADR: この枝`52625ed6`由来の要件v2.16/ADR-003 v0.9、file SHA256は要件`569b761b55f83923d8a6352705bbac3527103d4194a2819a06ac06296ee7060a`、ADR`375900aa9acc7e728cc3e28640418a37c4cd97a5f0de81cad130b74c5599684c`。本文採用と実developへの統合/正式型受理を区別する。
- 正式descriptor: 本枝`b2b825a4`の`contracts/state-transition/input_axes_descriptor_v1.json`、file SHA256 `fab52a2e17ba868ec7f818468241901a2cb12ad98e9cf19c20b52235d184ed56`、記載digest `sha256:5107f929d35ae48e01e25e0410a95235521b778ce53bae945ca5d7e2e956dd57`。stateTransitionAxesのstate10軸と既採用operation分類への対応であり、J6が正式descriptorへ反映済みとの記録ではない。
- 544の4値payload表: 本枝固定`7d6ce544`のG6/RBI候補99〜108行、file SHA256 `aec0a3d9f60a7d254fad985c088d1be2ca90d9ae1c72f73394991586a3aec7e3`。意味候補/所有境界の入力で正式schemaではない。
- 同期/データ型: 観測develop固定`547d199e0c68f3c7d73b6996056cf10ef5fb09fb`の`docs/design/sync-protocol.md`§5-5参加区分/W3・O4と`docs/design/data-model.md`§10のD2 bigint（値は再採番で変わる）。前者file SHA256 `46b61a9a1a6f0ef595631002ca217e353a6ae04df642aee849a6507cca783994`。過去entryのD1/世代を現在keyへ同一視しない。
- 守備番号: 本枝`contracts/field-regions/field_region_seed_schema_v1.json`のregion.position=1..9と要件FR-011。DHはFR-011/F-1の既採用意味へ参照し、役割literalはDTO候補。

| 候補型 | fieldごとの根拠・所有・未提供境界 |
| --- | --- |
| `PlayerRefV1` | kindとplayer_id/temporary_idは正式ID/一時UUIDのJ6/FR-015意味を表す今回のタグDTO候補。UUID形式は構造対象。実帰属/C2写像はUS1、意味照合は544。名前/背番号/塁で代替しない |
| `ScorerRefV1` | kind、runner_id/batter_idは要件J6のexact snake名。PlayerRefのタグは上行の候補。runner/batterの異タグ・別名を使う同一人物重複は構造uniqueItemsでは証明できない |
| `HomeTouchOrderV1` | not-required/observed、scorers=1〜4の順序付き一意列はJ6。配列を保持し反転を区別する。OUT3後exact-set/不要時の整合/順序必須局面は544意味照合、wire/保存/codecは506/US1未受理 |
| `T1EventRefV1` | event_id/record_versionは不変原本/版の参照DTO候補。正整数record_versionで正式保存版許容集合を宣言しない。D1/D2/変更版の代替ではない。実保存/読取はUS1/506 |
| `T1ContextPointV1` | keyとcontent_refは既存外殻参照、content_version UUIDは4値の同snapshot版を表すDTO候補。意味contract_version/record_version/wire版とは別。実発行/失効はUS1 |
| `T1HalfRefV1` | inning正整数・side top/bottomはFR-005/F-1と正式descriptor対応。現半回から過去の元半回を補わない |
| `T1BattingSlotV1` | none/slotのタグはDTO候補、slot=1..9はdescriptor state.battingOrder/FR-001。noneは打順を持たない守備参加者の表現で、打順不足を合法と裁定するものではない |
| `T1FieldingRoleV1` | fielding.position=1..9は上記守備番号、designated-hitterタグはFR-011のDH参照候補。配列で複数役割を保持し、DH解除の具体的成立は元の規則/交代へ依存 |
| `T1RosterEntryOriginV1` | initial/substitution、event/replaced_playerはFR-011の誰→誰/適用時点保持を表す候補。eventRef形式だけで有効な交代とは判定しない |
| `T1RosterEntryV1` | player/batting_slot/roles/entry_originは時点出場関係の閉entry候補。roles空列/守備人数不足でFR-011の警告を新拒否へ変えない。時点適格性/重複/交代の照合は544/交代側 |
| `T1TeamRosterV1` | team_id/away-home side/participantsはFR-001/011と544時点名簿。sideのliteralはDTO候補、現在players一覧で代用不可 |
| `T1RosterAtEventV1` | point/teams各side1組の二チーム構造。schemaは二件だけを検査し、home/awayの一意・実game帰属・名簿の内容を証明しない。US1時点読取/544意味型 |
| `T1BaseOccupantV1` | empty/occupied.playerは正式descriptor occupancy8値を選手参照付きで具体化する候補。塁を選手IDにしない。C2解決/同一人物は別照合 |
| `T1HalfApplicationMarkV1` | half/event/applicationは544 TB/undoの適用印候補。applicationは`half-application-mark`未閉鎖markerであって印の意味実装ではない |
| `T1PreStateV1` | point/roster_version、inning/half、outs0..2、count.strikes0..2/balls0..3、runners三塁、score両側非負整数、batting_order1..9、batter、tiebreak_active/game_endedはFR-005/008/009/010/F-1とstate10軸。half_application_marks/canonical_membershipは544候補の参照で未閉鎖。boundary記号N/R/L/Mを値として格納しない |
| `T1QueuedSourceV1` | queued/wire_d4/内部世代/D1/D5は同期§5-5群Aと既存外殻。過去sourceのwire世代/D1を現在keyへ書換えない。D4原文字列と内部世代を分離 |
| `T1ChangeSourceV1` | online-change/changeはW3/P3のD1なし変更の候補。changeは`online-change-source`未閉鎖marker。D1を発明せず、変更版順/D5等の完全な原本同定型はUS1/506と正式化する残件 |
| `T1ReplayParticipationV1` | own-d2/dependent.target/sync-onlyは同期参加区分3種のDTO候補。d2は既存data-modelのsigned bigint範囲で正数限定せず、TS numberは精度/製品ABI保証ではない。targetは参照で従属証拠の代替ではない |
| `T1EffectiveEntryV1` | event/source/operation_kind/participationは採用済み分類との対応候補。version_relation=original/revision/tombstoneとreplacesを操作種別から分離。content/canonical_membershipは未閉鎖markerであり内容/有効性を推定しない。変更/旧版/旧拒否D5の正史適格性はUS1/544の後続受理 |
| `T1TemporaryOriginV1` | mapping_id/temporary_id/player_id/origin_game_id/内部世代/D1/D5/ledger_kind/fingerprint/record_versionはUS1 cb0bのT1MappingEvidenceV1と辞書同一。origin_ledger_kind=accepted/record_version=1は同候補由来で正式ACL/保存提供の宣言ではない |
| `T1PrefixCursorV1` | start/continue.cursor_idは安定有限ページの読取位置を表すDTO候補。D1/D2/D3ではなく、cursor UUIDだけで発行/完全性を証明しない |
| `T1PrefixNextCursorV1` | end/continue.cursor_idは同じページ型候補。mapping continuation=nullを履歴終端に転用しない |
| `T1PrefixPageDescriptorV1` | page_index=0起点/前後cursor/page_refは全有限ページの閉manifest列候補。indexは論理再生順を定めず、実内容digestの算出/発行は未実装 |
| `T1PrefixPageV1` | key/prefix/content_version/descriptor/entries/originsはUS1固定読取案と544有効prefixの同scopeページ候補。ページ順とD2/変更版順を同一視しない |
| `T1PrefixManifestV1` | key/prefix/content_version/pagesは全読取列参照。selection_evidence/terminal_evidenceは`prefix-selection`/`prefix-terminal`未閉鎖markerであり自己申告の完了証拠ではない |
| `T1EffectivePrefixV1` | point/prefix/pages/manifestは同scope・同snapshotの全有限ページ候補。空prefixでも1ページが必要。replay_windowは`undo-replay-diff`未閉鎖markerで、差分/印/依存集合を提供したとはしない |

既存外殻4定義/旧25case/旧readonly interfaceの正準hashはresearchと専用試験へ固定する。各定義の対応だけで正式型受理/実能力提供/閉意味全成立を判定しない。

## 5. 未閉鎖の具体fieldと引受範囲

| marker obligation | 未供給field/次の作業単位 |
| --- | --- |
| `operation-content` | entry.content: 各操作の閉payload/原入力とT1評価入力の対応、既存descriptor/544 P8へ正式化。任意raw JSONや非空参照で穴埋めしない |
| `canonical-membership` | state/entry: 現系譜で有効な版・変更/墓標/取消の集合選択と失効、受理ledgerとの突合。旧監査の存在をmembershipとしない |
| `half-application-mark` | mark.application: 半回印/取消/再実行の意味と正史membershipの閉内容。元半回/印の現値補完不可 |
| `online-change-source` | P3 source.change: D1なし変更の原本同定/期待版V11/変更版連鎖、必要なD5/codec/結果束縛の正式型。D1付きsourceへ流用不可 |
| `undo-replay-diff` | prefix.replay_window: 差分/印/全後続依存集合の閉内容/有限集合、元scope/半回と除外Aの照合。文字列sourceだけで取消可能性を証明しない |
| `prefix-selection` | manifest.selection_evidence: 対象境界から取得すべき全有効集合をどう選んだかの供給証拠/固定SELECT・版bindingの正式契約。D3/entryのD1比較だけで決めない |
| `prefix-terminal` | manifest.terminal_evidence: 全有限ページの実読了・全選択集合との一致の真正な供給証拠/発行/失効。最後のendやmanifestの形式だけでは不足 |

**実行constructor・出所/完全性確認は未実装**。これらは現候補で必須の未閉鎖markerとして残り、構造上acceptでも全意味閉包/Readyは成立しない。DTO literal/格納表現はPO委任内の候補で、新しい意味が必要な旧codec移行・状態拒否/O4競合・新P3/失敗分類はrootの判断票へ返す。正式7.7/全23フラグ/OUT3/RBI/G6閉包/P6/P7/製品T1開始は未達で、実Port/HTTP完成をこの契約準備の開始条件に追加しない。P6封印/著者期待値には触れない。
