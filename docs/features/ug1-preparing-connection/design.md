# preparing接続の限定設計候補

親U-G1の意味契約は変更せず、今回のAPI/保存/readと画面境界だけを具体化する。未承認候補。

## 1. 所有パス

Codex Dの限定主担当は2026-10-22のPO指定。backendの新設候補は`api/schemas/games.py`、`api/routers/games.py`、`services/game_creation.py`、`repositories/games.py`と固有backend試験。既存U-G1/開始・resolver/codec・RG1 SQLは変更しない。

共有候補は`api/app.py`・`api/tenant_access.py`、repository/operation registryと生成契約、認可route/matrix/lock/seal、tenant-boundary/履歴、core宣言/登録/試験。必要な差分は実基線から導出し、実際の並行変更パスのみ順序調整する。

U-F8との限定接続候補は`GameScreenEntry.vue`、`GameScreenEntryRecord.vue`、`GameScreenEntryTypes.ts`と各spec、新`frontend/src/api/games.ts`、必要なら薄い`GameScreenEntryProvider.ts`。`router*`は既存/gamesと記録入口を再利用し、原則変更しない。正式供給→表示専用EntrySupplyへの変換はこのproviderが担う。フォーム/必須大会情報/UI共有パスは先行照会の回答待ちで、D担当指定をU-F8の受理にしない。実並行変更があればそのパスだけ停止する。

## 2. API・DTO候補

| 入口/型 | 内容 |
| --- | --- |
| `POST /games`、`PreparingGameCreate` | awareなscheduled_at、5種のgame_type_key、away/homeのteam_record UUID、必須大会指定、任意plate_umpire/section/week/day/game_numberの各label。status/tenant/applied_rules/rule_override/started_at/D4は受理しない。extra forbid。201はcommit後のみ |
| `GET /games`、`PreparingGameListRequest` | preparing限定。limit既定20・上限100、opaque cursor。tenant・trashed_at IS NULL・hidden_at IS NULLをSQLで限定し、scheduled_at DESC/id DESCでkeyset。limit+1で次cursorを返す。状態filterを端末に開かない |
| `GET /games/{game_id}`、`PreparingGameRead` | 同tenant/可視/preparingを1件。ID、入力保存項目、status=preparing、保存済み6-key snapshotを返す。現在の規則を再解決しない。0件・不可視・別tenantは同じ404 |
| `GET /games/preparation-options` | 動的ID経路より前に登録。必要な試合区分・有効な大会候補を上限/cursor付きで返す薄い供給。既存roster self/opponent APIをチーム選択に再利用し、全team/player一覧を複製しない |
| 大会指定 | existing keyとnew nameの排他的指定。名称長/正規化は既存語彙契約に従う。未提供のkeyをUIが生成しない。new nameではserverが同tenantの有効tournament語彙を一意に確定し、その結果keyをresolverへ渡す。既存無効名との衝突は復活/上書きせず拒否。独立した大会管理画面/更新APIを作らない |

大会はGame.tournament_keyがNOT NULL/FKであり、#152候補resolverも有効なtournament親を要求する。現developのAPI/repositoryにこの製品供給は見つからない。既存のtenant_vocabularies権限/正規化/一意性・#152の親ロック順を照合し、既存契約で不足する新権限/スキーマが必要なら実装前に個別ゲートへ出す。黙って大会なしや固定大会へ縮小しない。

snapshotは#152の正規公開codecをimportする。構造検証済みを出所/相関検証済みへ昇格させず、旧{}・5-keyを補完しない。公開codec未統合の段階では、入力DTO・SQL/read候補・不正行の拒否までを独立検証し、成功応答用codecをコピーしない。

## 3. 認可・失敗・保存境界

既存CAP:games:insert/readと必要な既存tenant vocabulary権限だけを使用。入口別のroute_id/operation_idは既存catalog規則から導出した具体候補を契約検査へ提出し、認可registry/HTTP matrix・7.7反映前にappへ公開しない。全入口にTenantMatchedRoute/既存C2 expected-tenant/challengeを使い、認証tenantと照合を本文検証/業務SQLより先に行う。frontendは正規clientのtenantBoundを使う。

createの成功順は、認証・認可/tenant照合→単一tenant_transaction_scope→RG1非ロック事前→大会親/両team検証（新大会は同scope）→登録済みresolver→出所/相関検証済み結果を1回encode→games INSERT(preparing,rule_override=NULL)→RG1 FOR SHARE NOWAIT直前→commit→201。resolverの親→既定→規則ロック順と、team/vocabularyの追加順序は#152公開契約との差分だけ受理する。別Session・規則再読・scope分割をしない。

resolverの4分類は維持する。候補外形はstage_a_unsupported=422、rule_not_available=404（越境/欠損と同外形）、invalid_rule=409（詳細を公開しない）、outcome_unconfirmed=503。RG1Unavailable/lock timeout/deadlock/serialization failureもrollback後の非成功503へ写す。HTTP statusを再送指示とせず、変更要求は自動再送0。応答不明は成功にせず保存確認を促す。DB内部メッセージ/他tenant原本の存在を本文へ出さない。具体例外の識別はRG1/resolver所有が提供する型に従い、例外文字列で判定しない。

結果不明のcreateに同じ要求を無条件再送しない。サーバー冪等キーの新仕様は加えず、利用者が一覧/詳細で保存結果を確認し、明示的な新規作成を行う場合だけ再実行する。送信中は同一フォームから二重submitを防ぐ。

readはRG1の通常書込許可に依存しないが、認可とsnapshot検証を省かない。破損/旧snapshot行を成功DTOにせず、非機密の失敗として扱う。認証切替時にrequestのtenant/authEpochを再照合し、旧GET/POST結果が新tenantの選択/cacheを変更しない。

frontend共通clientはgamesもCookie更新可能な認証付き経路に分類する必要がある。既存の旧Cookie不確実性無効化・通知dedupe・tenant metadata不正拒否を保持し、正当性をstorageから証明しない。必要な最小分類差分/試験だけを今回対象とし、通信層をコピーしない。

## 4. 外部提供と未成立事項

| 提供元 | 回収する差分 | 現状/提出単位 |
| --- | --- | --- |
| #152/TSK-550 | 公開入力/結果型、固定operation token/登録、提供担当・提出単位 | 現公開HEAD401ea428はstep3配置候補/製品登録0件。計画上step4登録・step5公開resolver、旧9ステップを維持。実担当の提供回答は未受領 |
| U-R1/#173 | RG1が成功を許可できる条件、既存2呼出しの具体例外境界、提供担当/提出単位 | read_rg1_open/assert_rg1_open_before_commit、RG1Unavailable、登録2件はdevelop提供済み。SQL2関数は状態読取後も常にfalse、0032 seedはclosed。#173は文書のみで、安全な成功許可は未提供。falseをtrueへ変更しない |
| U-F8 | フォーム・必須大会情報・一覧/詳細providerの具体パス分担 | 先行照会/PO指定通知を同じコメントへ集約。回答未受領。開始/記録権/1球の封鎖は維持 |

既存の復元解除と新D4不可分の規範を変更する判断は本計画に含めない。安全なpreparing許可が既存方式で提供できない場合は、U-R1が限定差分と安全根拠を個別ゲートへ提示する。実台帳/D4全体をread/DTOの一律待機条件にしない。
