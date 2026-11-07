---
feature: mvp-runner-nonpitch-read-dto
status: active
branch: feature/mvp-runner-nonpitch-read-dto-20261107
計画レビュー周回: 1
---
# Runner NP の記録済み v3 公開行を閉型へ接続する

起点 `8ce129d486bce6e8cc297b11f4dccc98d2498b88`。実 run12 の41列原本通過後、CSV producer 旧IW限定は別候補で修復中。記録済み GET にはさらに `LineupNonPitchPlayRow` / FE `commonPlayRow` のIW限定があり、有限Runner NPを読めない。本計画は既保存原本と唯一計算を変えず、公開行の供給だけを足す。

編集範囲は `backend/src/pitchlog/api/schemas/started_games.py`、`frontend/src/api/startedGame.ts`、`frontend/src/api/lineupPrefixGame.ts`、新専用BE/FE試験、本計画のみ。旧初球/v1/v2/Ordinary型、共有reader/SQL/契約/正本/asset/他WTは不変更。実PG/ブラウザはroot共通lock調整後。

| ステップ | 内容 |
|---|---|
| 1/1 | 既IWを保持し、Runner NP公開行を別閉variantでv3 Lineup pageだけに追加。実41列mapperの8有限形と正負codecを照合する。 |

新variantは `event_kind=non_pitch`、主打撃結果・course・投球6列・打球等の無関係列をNULLで固定する。走者操作の保存行は、盗塁で牽制2列/副結果ともNULL、牽制では `pitcher|catcher × first|second|third` の2列だけ、ボークでは `secondary-result.balk` のみを受ける。未知値、片側牽制、牽制＋副結果、打球/球速混入を閉拒否する。操作真正性・原観測との41列一致は既reader/preflight/SQL stampの責務であり、DTOを新たな実行許可に使わない。FEは35公開keyのexact性を維持し、共通keyの主結果必須を投球分岐に限定する。BE/FEとも既IWの厳格NULL形は不変更。8実mapper形は既唯一mapperを呼んで比較し、独自の計算/fixture正解を作らない。純検査を実GET成功に読み替えない。

承認: root が起案計画 SHA `a4ca9a6389afeb760dca26ee48be1a78be54a0c609cc7d5597f5348e1604adcf` を非作者確認し P0/P1 なし。2026-11-07 JST、PO 委任による Codex 主担当判断で step 1 着手可。本人署名や実GET証拠ではない。
