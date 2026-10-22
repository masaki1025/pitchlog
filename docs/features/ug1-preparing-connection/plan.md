---
feature: ug1-preparing-connection
status: active
承認: 未
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3da93b75e687812e9b44d0b6ff5196e7
branch: feature/ug1-preparing-connection
created: 2026-10-22
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# U-G1限定追補: preparingの作成・再取得

## 1. 背景・目的

[TSK-395/U-G1](https://app.notion.com/p/3da93b75e687812e9b44d0b6ff5196e7)のFR-001作成面を、実画面→実API→隔離PostgreSQL→reloadで取得する。[要件正本](../../requirements/requirements-pitchlog-2026-07-22.md)のFR-001/013/014/033/034、NFR-005/014/018/019を適用する。

親計画は既存`feature/ug1-game-lifecycle`の`67dff5f707dcb2311a35140ae870b44f46e24803:docs/features/ug1-game-lifecycle/plan.md`（2026-10-14承認、計画レビュー2周）。親の8ステップ・受理履歴を複製/改番しない。親のステップ1はresolver契約差分が残り、ステップ2作成は未着手。本追補は未完の親ステップ2とステップ4のpreparing read面を限定先行する追加実行単位であり、開始・同期済み再開は親へ残す。既に完了したステップに後発変更を押し込まない。

2026-10-22のPO指示はCodex Dを本限定範囲の主担当に指定し、追補起案・6.1レビューを許可した。最終計画承認・製品実装・push/PR作成は未許可。実基線は`7717b98686395b2c0db9d545a5effa06888885ff`。親worktreeはcleanを2回確認し、編集しない。確認根拠・送付/受理/提供の区別は[作業ログ](../../worklog/2026-10-22-ug1-preparing-connection.md)。

## 2. スコープ

### やること

- preparingの作成入力DTO、tenant限定ページング一覧/詳細read、登録済みoperation、認可・C2 tenant照合・拒否経路。
- 実resolverによる出所/相関検証済み6-key snapshotと試合を同一scopeで保存し、commit後にだけ成功を返す。GETは保存値を読み、現在の規則へ再解決しない。
- 必須大会情報と両チームの選択供給を確認し、既存製品経路がなければ今回の作成に必要な最小の大会候補読取/名称登録を同一境界に追加する。仮の大会キーで埋めない。
- U-F8の既存`GameScreenEntry*`に作成フォーム/一覧・詳細providerを限定接続し、認証切替の旧cache・遅延応答/変更結果を拒否する。共有Pinia/QueryClient/正規clientを再利用。

### やらないこと

開始、スタメン、D4/D3/V12/保持端末の発行、記録権Port、1球保存、T1/T2、同期済み再開、終了、全15経路、削除、規則の大会割当/上書き設定、RG1関数の成功化/運用open、resolver/codecのコピー、新カード・新ハーネス機能。親U-G1全体・TSK-395/TSK-523全体を完了にしない。

## 3. 影響する正本

| 対象 | 差分・ゲート |
| --- | --- |
| requirements/design/ADR/development/ops | 本追補から改訂しない。既存の作成時snapshot/RG1/非再利用の意味を維持。RG1の安全な成功許可や規範変更はU-R1所有の個別ゲートで、追補承認へ抱き合わせない |
| 認可registry/matrix、lock/seal、tenant-boundary登録/派生JSON・Python、snapshot/履歴 | 既存CAP:games:insert/readと必要な既存vocabulary権限を使う新入口/operationだけを登録。固定候補の完全前後値を7.7へ提出。新権限/DB grant/RLS/migrationが必要なら停止し具体差分を個別提示する |
| `.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py` | 新パスの宣言・試験→別コミットのJSON登録。既存対象/拒否能力を減らさない |

予定パス・API候補と境界は[design.md](design.md)。既存のtenant-boundary基線・履歴は最新実developから導出し、#152/#162/#173の未統合枝を基線にしない。正式7.7・人間逐行確認・公開/マージは別ゲート。

## 4. 実装方針

テナント分離、認可源、RG1、規則snapshot保存の接合は6.3のコア領域。NFR-018の単一resolver/codecを再利用し、DTOの構造検証を出所証明と混同しない。

### 所有・開始条件

- **確定**: PO指定によりCodex Dがpreparing作成・再取得の限定主担当。旧U-G1全体/開始、#152のresolver、U-R1のRG1、U-F8全体は移管しない。
- **通知済み・未受理**: 旧担当/#152とU-F8へ予定パスを通知。未回答を所有解除としない。実際の並行変更があれば当該パスのみ調整し、他の非共有作業は継続する。
- 製品着手には本最終計画のPO承認が必要。親の既受理RG1①〜⑤、6-key保存/4失敗の方式を再承認待ちに戻さない。
- ステップ3のcomponent実装は実resolver/安全なRG1 openを待たない。公開型未提供部分は接続準備として区別し、仮の成功型やダミーresolverを製品に置かない。readの保存snapshot検証に必要な正式codecが未統合ならSQL/入力DTO/拒否境界までを独立検証し、snapshot成功応答の合格は未達と記録する。
- ステップ4の公開read成立には正式codec・登録/認可の7.7・UIパスの実競合調整が必要。正式型なしのsnapshotを有効として公開しない。保存前resolverは不要。
- ステップ5の保存成功には#152の公開resolver/固定operation登録と、安全な成功許可を返すRG1実提供が必要。D4の未提供は一律条件にしないが、RG1の現行常閉を迂回しない。
- 必須大会の名称→有効keyは既存製品経路が現存しない。designの限定案を本レビュー/PO承認対象とし、所有・権限・resolverの親ロック順を接続前に照合する。名前をkeyへ推測変換しない。

### 実装ステップ(コミット単位)

| # | 追加実行単位 | 合格条件 |
| --- | --- | --- |
| 1 | D限定新規パスのcore宣言・試験 | 既存親/U-F8対象を保持し、宣言のみでguard試験が通る。製品・JSON登録は追加しない |
| 2 | core JSON登録 | ステップ1と別コミット。全予定パス検出と本人確認未記入の拒否を確認 |
| 3 | backend作成入力DTO、preparing readのSQL/tokenと拒否境界 | 実resolver/RG1成功許可を待たず実装。extra拒否・5区分・aware日時・入力長/UUID、tenant束縛、LIMIT/cursor/不可視排除、正式codec未提供/旧snapshot拒否を既存試験経路で確認。routerをappへ登録せず、製品で仮成功させない。共有operation/凍結登録は候補として分離し、正式値を先行反映しない |
| 4 | preparing readの実HTTP/認可登録、既存画面の一覧/詳細provider | 正式codec・7.7受理後に登録を反映。既存認証を使い、同tenantの保存済み値を返す。別tenant/未認証/旧snapshot拒否、ページング、authEpoch切替/遅延GET/旧cache破棄を確認。DB fixtureを用いたread検証を実画面からの作成成功に数えない |
| 5 | 必須大会候補/名称登録、実resolver/RG1を使う作成API、作成フォーム接続 | 実提供・担当契約/7.7確認後に同一scopeで作成を実装。大会/チーム検証→resolver→game INSERT→RG1直前→commitを全確定/全取消。新大会名を使い、語彙INSERT後の故障とRG1直前拒否の各試験で試合・新語彙がともに0件へ戻ることを確認。正式関数のfalseを変更せず、未提供ならこの単位を停止。前段で作成入力フォーム/拒否試験は進められるが、保存成功を合格にしない |
| 6 | 実画面・実API・隔離DBの作成/reloadと故障系・全検査 | 同じ試合ID/status/preparing/6-key snapshotをreload後に取得し、規則変更非遡及、越境・通信失敗・旧mutation・commit前故障/RG1両競合を確認。同一フォームを送信中に二度操作してPOST1件・保存試合1件を確認。全品質検査、レビュー採否と本人確認対象を固定。開始/初期権/1球は未完のまま |

各行は1委任・1コミット。異なる行を1件へ詰めず、親の旧コミット件名を変更しない。ステップ内に個別受理待ちが残れば未完として止め、通過したことにしない。予定PRは最小1件。push・Draft先行で実番号が必要となる場合は、準備した差分/未通過検査と必要な例外をまとめてPOへ求める。今回の起案/レビュー許可をpush/PR許可に流用しない。

## 5. DoD

- 実認証の画面から実APIを通り、隔離DBへpreparingと規則snapshotが一度だけ保存され、実GET/reload後も同じID・値を確認できる。
- 先攻/後攻・日時・5区分・必須大会・既存任意ラベルを保全。紅白戦は同一team IDの作成までとし、両側スタメンの開始課題を持ち込まない。
- 出所/相関未検証、割当あり/上書きあり、無効な親・別tenant、不明なRG1、結果不明は成功にせず自動再送しない。失敗時に試合/新大会語彙だけを残さない。
- 一覧のDB絞り込み/上限/cursor、入力自動エスケープ、tenant照合の業務SQL前拒否、遅延応答/遅延mutation/認証切替の旧cache拒否を維持。
- `backend/tests/conftest.py`差分0。既存レビュー履歴を保持し、本追加単位の6.1レビュー範囲/採否/未再レビュー差分を記録。正式受理/本人確認の代記なし。

## 6. テスト計画

| 種別 | 検証 |
| --- | --- |
| 単体・契約 | 既存BaseSchema/Page、公開codecによる6-key/旧行拒否。aware日時、5区分、任意ラベル、余剰field、予約field拒否。cursor改変/同時刻複数行/複数ページ |
| 越境・認可 | 別tenantのteam/大会/試合、未認証、expected tenant不一致は業務SQL前拒否。非存在/不可視/他tenantの外形を同じにする |
| DB・故障系 | 製品service/登録scopeで保存・再取得、snapshot非遡及、game INSERT後/commit前故障の全取消。新大会名を指定し、語彙INSERT直後の故障、RG1直前拒否それぞれで試合・新大会語彙が0件、既存語彙は不変と確認。RG1復元先行と作成先行を本物の関数/権限で2接続検証。合成Port・直接SQLseedを作成経路の証拠にしない |
| 画面・E2E | 実画面の選択→POST→一覧/詳細→reload、必須大会の取得/登録、対戦相手/self供給の回帰。送信中の同一フォーム二重操作でPOST1件・保存試合1件を確認。認証切替・複数タブ・遅延GET/POST・応答消失で旧cache/成功表示/自動再送を拒否。開始・1球ボタンは封鎖のまま |
| 品質 | backend Ruff format/check・ty・pytest、root Ruff/ty/pytest、frontend Prettier/ESLint/vue-tsc/Vitest/build、既存認可/凍結/宣言/基線/closure/文書同期・core-guard。失敗/skip/timeout/中断を通過にしない |

## 7. 今回の承認対象

1. 親8ステップ/既レビューを維持し、preparingだけを上表6コミットの追加実行単位とすること。ステップ3の独立component→4のread→5の保存成功→6の実受入の順と個別開始条件。
2. designの具体API/DTO・必須大会の最小供給案、U-F8既存画面の限定接続。新たな権限/正本改訂が必要になった場合はその差分だけ別判断へ戻すこと。
3. 固定候補の7.7・本人確認・公開/マージ・必要ならDraft先行の操作許可を、今回の計画承認に含めないこと。

未回答の担当受理・resolver/安全なRG1成功許可は未成立のまま提示する。本レビューが候補を採用しても実提供/正式受理/PO最終承認を代記しない。
