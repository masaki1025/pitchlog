---
date: 2026-10-16
topic: U-S1 の公開面と同期の失敗分類(TSK-506 への接続契約)
branch: feature/us1-sync-port-surface
---

# 作業ログ: 2026-10-16 U-S1 の公開面と同期の失敗分類(TSK-506 への接続契約)

## やったこと

- **割り当て**(山田正輝 2026-10-16・master 経由): TSK-506(同期 API の入口)へ渡す U-S1 側の公開面(公開関数・型・失敗境界・担当)の明文化と、例外と再送の 4 区分(前提違反・内容拒否・一時的 DB 障害・結果未確認)の対応付け。506 の worktree は読むだけ。TSK-547 は含めない
- **調査**(`docs/features/us1-sync-port-surface/research.md` — 読むだけ・典拠つき):
  - 入口が呼ぶのは `SyncRequest.from_payload`(`sync/model.py:231`)と `apply_sync_request`(`sync/apply.py:292`)の 2 つ。原子性はイベント 1 件ごと
  - ポートの登録表 `PORT_IMPLEMENTATIONS` が空で検査器も未接続(`sync/ports.py:134-143`)— このままでは実在する試合への要求はすべて `PortRegistrationError`
  - `InvalidationSinkPort` を注入するのは `deliver_pending_sync_intents`(`sync/invalidation.py:174`)だけで、製品の呼び出し元は 0 件(試験だけ)。起動する実行主体と本物の sink の担当は未定
  - develop には同期要求を送るクライアントのコードが無い(送信層は 506 の未マージのステップ 3)。サーバーは未捕捉の例外を 500 にし(`api/errors.py:132-146`)、wire 設計は 500 を B7 に写す
  - 正本の段階 ① は不成立を原因を問わず B7 にし(`sync-protocol.md:694`)、B7 は ACK なし・未送信のまま・自動再送・通知が届かない(`:768`)。**恒久的な失敗の受け皿が正本に無い** — 永久再送・先頭詰まり・理由の非表示

## 決定

- **PO 裁定(山田正輝 2026-10-16)**: 恒久的な失敗は **案 B + A** — 列挙した恒久的な不変条件違反を O4 と同じ形で B3 + 要操作(管理者対応待ち)として ACK に載せ(O 系の規則を 1 つ新設)、未知の例外は B7 のまま「回復しない場合の顕在化」を足す
- **PO 裁定(同日)**: 正本の改訂は**本タスクの PR で**確定ゲートを通す(sync-protocol **v0.9**。9-5 の単独 PR〔TSK-547〕は v0.10 へ)

## 未決・次の一歩

- /plan で計画書を書き、計画レビューにかける(コア領域 — 代替主体 Fable 5.1・6.3 (6) の様式)
