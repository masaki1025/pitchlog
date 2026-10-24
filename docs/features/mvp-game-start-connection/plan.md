---
feature: mvp-game-start-connection
status: active
承認: 済（PO委任によるCodex判断・開始入力の限定単位）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-game-start-connection
created: 2026-10-24
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 試合開始の入力境界と実接合の先行単位

## 1. 位置付け

実起点は`4b2db6907f329c3dde113c3b7e1c3515600fb915`（実develop、PR181統合点）。正常PR180の初期付与部品を含む。本起案は新branchのplan/researchだけで、製品実装の承認ではない。巨大なfirst-path隔離組立をmergeせず、台帳・RG1・作成候補は必要な固定sourceを後続で個別供給する。

親は固定`67dff5f707dcb2311a35140ae870b44f46e24803:docs/features/ug1-game-lifecycle/plan.md`の8ステップ中3と、既存[U-F8計画](../uf8-full-game-followup/plan.md)の6・8。親U-G1は本起点に未収録のため固定Git参照とし、旧8/9ステップ・レビュー回数・開始側の着手条件を改番/消去しない。本単位のレビューを#175の旧追加枠へ算入しない。

開始operation/DTO/endpoint/clientの製品実装は実baseに存在しない。既存`InitialGrant`と`issue_initial_recording_right`は単一部品として再利用できるが、`InitialGrantScope`はProtocolだけで実DBadapterがない。開始全体をT1/T2計算核の完成待ちにしない一方、transportを通っただけの入力を開始可能・権利保持・計算Readyとは判定しない。

## 2. 今回提案する1ステップ

最初の小単位は開始要求のtransport DTOだけとする。物理未受理のDBを仮設して成功を返すadapterや、常に拒否するだけの製品endpointを作らない。実scope/実DBadapterに必要な有限の追加集合は[research](research.md)へ具体化し、rootが物理契約/所有を確定した後に同じ親step3の次小単位へ進める。

| パス | 次の製品委任で許す変更 |
| --- | --- |
| backend/src/pitchlog/api/schemas/game_start.py | 新設。`GameStartRequest`と両側の`StartLineupInput`を既存`BaseSchema`/`EntityId`で定義する。HTTP/router登録・service・DB呼出しはしない |
| backend/tests/test_game_preparing_components.py | 既存試験へtransport正負例を追加。既存作成/read試験を保持し、新testpathを作らない |
| 本feature research.md | 版・結果・失敗・後続接合の記録だけ |

共有metadata/認可/正本、既存U-G1/U-R1/U-M2/U-F8のsource、台帳package/Protocol、plan自体、他worktreeは製品委任の編集対象外。現在の起案は本plan/researchの2pathだけ。

### 要求DTOの閉集合（新規提案、レビュー/PO委任後に採用）

`GameStartRequest`は`start_request_id: EntityId`、`device_id: EntityId`、`device_credential: SecretStr`、`away: tuple[StartLineupInput, ...]`、`home: tuple[StartLineupInput, ...]`のexact5field。資格は非空・repr/検証エラーに原値を含めない。ゲームIDは後続のURL側で受け、tenant/game/status/started_at/D4/D3/V12/復旧世代/予約attempt/名前/背番号/任意extraをbodyへ加えない。UUIDは既存型と同じ解析契約に従い、端末ID自体を資格証明にはしない。

各要素は`player_id: EntityId`、`batting_order: StrictInt | None`、`fielding_position: JsonValue`のexact3field。打順は非nullなら1〜9、両側配列の外形は9又は10枠。fielding_positionは既存U-M2の保存/復元DTOと同じJSON表現を保持する。このDTOでは守備値の業務集合・重複・DH整合・現役/在籍・背番号・権利を検証済みとしない。守備値の正式な値域/表現が未確定である事実を、任意JSONの開始許可へ読み替えない。後続開始serviceにはサーバー保存snapshotの`dh`と名簿に対する単一の確定検証が必須であり、未提供中は開始呼出部を接続しない。

DTOの返却を開始成功receiptとして使わない。成功時の内部値は既存`InitialGrant`を再利用し、D4/V12/復旧世代の新しいwire表現や成功応答DTOをこの小単位で定めない。後続の実commit確認より前にV12を応答へ出さない。

## 3. 実装ステップ（親の改番ではない）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 開始入力transport DTOと既存component正負例を追加 | exact5/3field、UUID、9/10外形、StrictInt/null、SecretStrの非露出、extra/サーバー所有値の拒否が緑。既存作成/read試験不変、HTTP/DB/権利/状態計算の実提供を主張しない |

独立限定計画レビューとrootのPO委任承認後、指示されたこの1ステップだけを実装・検査・単一ステップcommitして停止する。現時点はsource編集禁止。

## 4. 影響する正本・core・検査

本DTOのtransport先行だけは正本反映なし。既存`api/*`と`test_game_preparing*.py`でtenant-isolationのcore捕捉を確認する。記録権判定・同期動作・DBadapterをこの2pathへ紛れ込ませない。後続の実adapter等は別の具体scope/必要な領域登録を先行宣言→別JSONで確定し、本単位の承認を流用しない。

対象component pytest、backend Ruff/ty、root Ruff/ty・docs/局所plan-sync・diff checkを行う。DB起動/全backend/census反復は本transport単位には不要。入力型の正例は開始成功証拠ではなく、現実の端末資格やD4を試験stubへ置換したことにもならない。新鍵・運用秘密を発行せず、`.env`/共有DB/P6/封印へ触れない。

後続の側列/資格/再交付/epochの構造的変更はdata-model等の具体節とハーネス7.6/7.3をrootが判定し、認可/凍結の実差分と7.7はroot唯一writerが直列受理する。現在の未受理値を成功へ変えない。

## 5. 到達点と時間見込み

この最初のコード小単位は楽観30〜45分、通常1〜2時間（対象検査/commit込み）。実DBadapterは物理契約と所有固定後、楽観3〜4時間・通常6〜10時間を見込む。開始HTTP/UI/実browserはその後の別小単位で、T1計算は開始準備/初期権adapterの着手条件にしない。守備値・側列・端末資格・暗号鍵の実供給/登録の確定時間は現時点で算定しない。

製品開始・初期名簿・初期記録権・同一transaction・1球保存は未完成。全復元/全設備喪失proof完成も本transportの前提には加えない。準備中作成の実画面成功を、開始・MVP完成へ拡張しない。


## 計画レビューとPO委任判断

2026-10-24T01:11:08.323361+00:00、Codex主担当/rootは今回PO4/5/8/10の委任により、対象2b6c694743765ba43dfb926ee68a2fce091eb755（plan0a6db0e81f83c85583d9c19b272e051f931f4d1f65befddb4940916ef5fa55ba/research7085e4be6ed16725070e51618287a4a19652ab73dba5f183824a0de3d4f9f158、標準diff f3473cba203d8d84c74518c81169065f654c3a0795e213a1a5603b85fbcc3ab7）を承認する。新案作成に非関与のresolver_ledger_plan_reviewによる初回全文0/0/0と実4b2/UG1親計画/既存型/core捕捉を照合した。exact5/3fieldのtransport入力境界・既存component正負例のステップ1/1だけを指示し、HTTP/権利/DB/新資格・鍵発行/状態計算へ拡張しない。資格の非露出はSecretStr単独とせず、他fieldが不正な場合のerrors()/json()/strも局所検証する。これは既DoDの具体例であり新しい意味仕様ではない。旧U-G1/U-R1/U-F8の承認・ステップ/レビュー系列、実保存/開始の全条件を保持する。起案時の製品編集禁止は本対象版の限定ステップにだけ解除し、本人の実値確認/逐行確認/署名を代記しない。
