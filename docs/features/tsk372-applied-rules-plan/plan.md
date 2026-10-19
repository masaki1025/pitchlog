---
feature: tsk372-applied-rules-plan
status: active
承認: 済(2026-10-19・山田正輝、候補コミット8a45168a・SHA-256 e56e3ad535e556b710fc8bd1645fd63d52a59245a87a88f0338cab5d47254a7e)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3d993b75e687818ea93bf8ddb087fe97
branch: feature/tsk372-applied-rules-plan
created: 2026-10-19
計画レビュー周回: 3
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: TSK-372 `games.applied_rules` 保存後不変性の限定先行単位

## 1. 背景・目的

[TSK-372](https://app.notion.com/p/3d993b75e687818ea93bf8ddb087fe97)の正式範囲は、`coverage=partial`の23表の不変列分類である。本計画は2026-10-19のPO指名に基づき、現TSK-550担当が**`games.applied_rules`だけ**を代行する先行単位である。TSK-372全体の所有移管・完了、元所有側の受諾は意味しない。

現行[データモデル§6-5](../../design/data-model.md)は規則を保存時に解決して試合へスナップショットを書き、規則マスタの後日変更を遡及させないと定める。一方、試合行自身の保存後の異値UPDATEをDBが拒否する保証はない。現行manifestとORMの`games`保護列にも`applied_rules`はない。N3受入上のこの差分を限定して是正し、初回INSERTを許し、保存後の異値UPDATEを実DBで拒否する。TSK-550の試合作成公開前条件だが、同機能の完成やU-G1の成功を本単位の成果とはしない。

## 2. スコープ・所有

### やること

- 実統合後の`origin/develop`の単一Alembic headを親にしたmigrationで、`games.applied_rules`の保存後異値UPDATEをDBで拒否する。初回INSERT、別列更新、同値UPDATEは許す。既存行は更新・削除しない。
- `contracts/db/schema-manifest.json`の`games.immutability.protected_columns`と`backend/src/pitchlog/db/game_state/models.py`の対応宣言に同列を追加する。`coverage=partial`と残る22表の未分類・人間判定は維持する。
- `backend/tests/db/test_games_applied_rules_immutability.py`に恒久的な使い捨てPostgreSQL試験を置き、製品ロール、全UPDATE経路、失敗時の全取消、catalog、downgrade/re-upgradeを確認する。
- N3受入シートは行番号ではなく対象・典拠・内容で対応を追う。manifest変更時に影響行を再生成し、安全な旧判定だけを持ち越す。変更行の旧判定・理由は作業ログへ保全し、新しい人間判定を得てから収録する。無関係な判定と理由は保持する。

### やらないこと

- 23表全体の分類、TSK-550のresolver・codec・起動器、U-G1の試合作成保存、一般的なトリガ解除、列権限の拡大、既存DB適用をしない。
- 既存の#152・#149・#132の7.7受理履歴を変更・流用しない。新規の受理値・承認者・承認日は事前に記入しない。
- 候補worktree`feature/orm-applied-rules-immutability-candidate`の未コミット製品差分は保全し、計画承認まで正式実装へ移さない。

### 編集所有と順序

本計画の編集対象は上記migration・manifest・ORM・恒久試験・本feature文書と、`docs/features/orm-schema-migration/acceptance-sheets/`のN1・N3・N4・N7影響行である。生成件数が変わる場合は同ディレクトリREADMEと`tests/test_orm_acceptance_sheets.py`の固定件数も対象とする。2026-10-19現在、既存候補worktreeには同じ4製品パスの未コミット候補があり、当該候補は今回指名された担当が保全する。元TSK-372所有側の受諾は未確認。PR #156のU-R1 worktreeにもmanifest・N3シート、#152候補にもN3シートの未コミット差分がある。これらを上書きせず、U-R1の編集解除と実統合、#152の引き継ぎ枠を確定してから共有ファイルへ触れる。

統合順は**本限定単位 → 起動入口専用PR #158 → TSK-550本体PR #152**を目標とする。#158はパス登録だけであり、本単位と製品機能の相互依存はない。#152は両実統合後の基線を取り込み、Alembic revision・受理履歴・core宣言を実基線から再導出する。現在の候補名`0033_game_rules_immutable.py`は確定revisionではなく、統合時の単一headに合わせて採番する。順序が変わる場合も、互いの未統合ブランチを基線にせず、実統合SHAから再導出する。

## 3. 影響する正本・正式ゲート

| 対象 | 判断・差分 | 実装前またはPRのゲート |
| --- | --- | --- |
| `docs/design/data-model.md` §6-5、変更履歴 | 現文の「マスタ変更を遡及させない」が「試合行の保存後異値UPDATE禁止」を含むか所有側に限定判定を求める。含まなければ本実装を停止し、別の限定計画・正本ゲートへ送る。既存の6-key契約・規則値は不変 | 新しい規範条件なら別ゲートで§6-5本文・変更履歴、manifestの正本SHA・`games.source_sections`、N1/N3/N4/N7影響行、必要な7.7受理を同一統合境界で閉じ、その実統合後に本計画の比較元を更新する。実装追随に収まるという所有側判定なら、その典拠と7.6判定を記録。無回答を受理としない |
| migrationとmanifest・ORM | `games.applied_rules`だけを保護列へ追加。実Alembic headと既存不変列監査へ整合。`games.source_sections`に`6-5`がなければ追加し、N1/N3/N4/N7の影響行を再生成する。別ゲートで正本改訂が先行した場合は統合済みSHAを保持する。manifestの旧受理値は保持 | コア領域6.3敵対レビュー・本人逐行確認。manifest・正本SHAの凍結該当性を判定し、該当実値は7.7の完全な前後値・snapshot・受理記録案を提示して正式受理後に履歴反映。必要な7.6判定も記録 |
| 認可・復旧 | 現行`pitchlog_app`の表UPDATEがあってもDBが異値を拒否する。正当な訂正migration・復旧も拒否されるため、例外が必要なときは別の対象限定migration・排他・全取消・復元後照合で個別審査。通常製品に解除入口は置かない | 認可/復旧所有側の影響採否を取得。権限変更・汎用バイパスが必要なら本計画の範囲外として別ゲート |
| 要件書・開発ハーネス正本 | 反映なし。FR-014/P-30とNFR-019、6.1/6.3/7.6/7.7を適用 | 本計画の6.1敵対レビューと人間承認 |
| ORM N1/N3/N4/N7受入シート | N1/N3/N4/N7の当該games影響行をステップ3で再生成する。変更行の旧判定・理由は作業ログへ保全し、旧行と新行の対象・典拠・内容を対応付ける。行数変更時は生成README・固定件数試験も追随する | 持ち越せない行は人間が新判定・理由を記入してからrootのシート検査を通す。人間判定を代記しない。差分を「一致」へ変えるだけでDB保証の代用としない |

## 4. 実装方針・ステップ

既存の限定候補と隔離DB4件の結果は設計の補助証跡として再利用する。`BEFORE UPDATE OF applied_rules`と、別のBEFOREトリガが値を変えた場合も捕捉する`AFTER UPDATE`検査を候補とする。異値をSQLSTATE `23514`で拒否する。これらのトリガの順序、SECURITY DEFINERの要否、所有・RLSへの影響は実基線のカタログと隔離DBで確かめ、根拠なく権限を増やさない。全23表監査を弱めない。実装着手前に3節の正本解釈・編集枠・必要な個別ゲートを確定する。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 正本§6-5の所有側判定、実migration head、認可・復旧影響、manifestの7.7対象と編集枠を記録する。新規規範が必要なら別の限定計画・正本ゲートで本文とSHA・シートを同時に確定・統合してから本ステップを完了する | 未承認の規範追加・権限変更・7.7値を正式資産へ書かない。実装可能な確定契約と別ゲートの完了証跡、U-R1共有パスの所有解除を記録する。`(ステップ 1/4)`の別コミット |
| 2 | 実headからmigrationを追加し、初回INSERT許可・異値UPDATE拒否を実装する | 既存行不変更、SQLSTATE23514、別のBEFOREトリガ経由も拒否、downgradeで対象トリガ・関数だけを撤去。専用隔離DBの限定試験を通す。`(ステップ 2/4)`の別コミット |
| 3 | gamesのmanifest・ORM保護列宣言、恒久実DB負例試験、`games.source_sections`の`6-5`対応、N1/N3/N4/N7シートの影響行を一緒に更新する。別の正本改訂が先行した場合は統合済みSHAを保持する | `coverage=partial`と無関係の旧判定を維持。持ち越せない行の人間判定を得て収録し、必要なら生成README・固定件数試験を追随させ、manifest監査・N1/N3/N4/N7一致検査・DB試験・凍結検査以外のroot/backend影響検査で宣言とDB挙動を突合する。7.7正式受理前の凍結検査不合格を成功扱いにしない。`(ステップ 3/4)`の別コミット |
| 4 | ステップ3の候補・実比較元で7.7の完全値、snapshot、受理記録案を確定して人間の正式受理を得る。その値の履歴・snapshot反映を本ステップの単一コミットに収め、最終検査とPR資料を整える | 比較元の既受理履歴を追記のみで保持し、未受理値を記入しない。受理済み値で凍結検査を含むroot/backend全件を通す。コア敵対レビュー、独立一次レビュー、本人逐行確認はPRゲートに残す。`(ステップ 4/4)`の1コミット |

7.7反映は正本確定ゲートの`反映<r>周目`ではなく、本実装のステップ4コミットである。別の正本改訂が必要なら、その正本側の7.3と反映周コミットは別ゲートで扱う。レビュー・受理・人間確認をステップ完了の自己申告で代替しない。

## 5. DoD

- [ ] 初回INSERT、別列・同値UPDATEが成功し、保存後の異値UPDATEは製品ロールを含む実DBで拒否される。別のBEFOREトリガ経由の値変更も捕捉し、失敗時はtransaction全取消。
- [ ] 正本§6-5の解釈または別ゲートの限定改訂が正式に確定し、改訂時は同一統合境界でmanifestの正本SHAとシートを追随させる。本PRは`games.source_sections`とmanifest・ORM・DB catalogの保護宣言、N1/N3/N4/N7シートを一致させ、残る22表の`coverage=partial`を維持する。変更行の新判定は本人が行う。
- [ ] 正当なmigration・復旧への影響、必要な例外の別ゲート、実revisionと#152の順序を明示する。既存DB適用や試合作成公開は別判断。
- [ ] 7.7の完全値・snapshot・承認根拠を正式受理後に追記のみで反映し、既受理履歴を保持する。
- [ ] N3の既判定を保持したまま当該差分の人間再判定を得る。コア敵対レビュー、別の一次レビュー、CI、本人逐行確認をPRゲートで満たす。TSK-372全体を完了にしない。

## 6. テスト計画

- `backend/tests/db/test_games_applied_rules_immutability.py`: 専用使い捨てPostgreSQLで初回INSERT、異値/同値/別列UPDATE、製品ロールの拒否、別BEFOREトリガ、SQLSTATE23514、保存値と先行操作の全取消、カタログ・downgrade/re-upgradeを試す。既存行の更新・削除がないことも照合する。
- 既存のschema manifest監査・不変列全表監査とbackendの`ruff format --check`相当、`ruff check`、`ty check`、pytest、およびrootのruff/ty/pytestとcore-guardを計画したゲートで確認する。`ruff format`のroot実行は行わない。
- 正本・認可・復旧・7.7の承認前には、候補の隔離検証を正式成功と混同しない。CIはPRの実HEADで確認し、本人逐行確認の欄は本人の確認まで空欄とする。
