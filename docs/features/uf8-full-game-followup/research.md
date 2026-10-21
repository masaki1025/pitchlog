---
feature: uf8-full-game-followup
type: research
date: 2026-10-20
---

# U-F8後続の調査根拠

- 調査基線はdevelop `7c1afebab31facc71e8cfc2731da1a9fa392de4e`（#158統合後）、U-F8第1期コード固定点`ce309be1fa6ffe891081b6d9662c8a0bdeacc68e`。#160は最新developを`96579edda48431f01da060cdc6efb5f072d5fa88`で競合なく取り込み、製品コードの変更はない。
- [第1期計画](https://github.com/masaki1025/pitchlog/blob/ce309be1fa6ffe891081b6d9662c8a0bdeacc68e/docs/features/uf8-game-recording/plan.md)5-2/5-3は実確定、再生復元、インプレー、修正、独立画面を未達としている。`GameScreen.vue`は表示文字列と下書き候補をpropsで受け、`GameScreenCommitGate.ts`は確定を止める。打球・走者・交代・undo・終了を実行する製品導線はない。
- [正式カード](https://app.notion.com/p/3f493b75e68781b49976fc6c5ed970d5)を2026-10-20に再取得。URLは#160、状態は確認待ち。DoDは単一実装・一致性・E5・鮮度・座標・5領域・敵対/人間確認であり、下書きの完成だけでは全体完了しない。
- [要件書](../../requirements/requirements-pitchlog-2026-07-22.md)4.0-4、FR-003/004/006/007/009/010/011は入力観測、走者別の裁定、断中操作6種、undoと過去修正、タイブレーク、交代、終了/再開を要求する。NFR-018の未分類はfail-closed。FR-003の入力対象判定とFR-011の9ポジション検証を画面で補完しない。
- [U-X1計画](../ux1-state-calc/plan.md)2026-10-17〜19の限定改訂はT1/T2のD-14-m対象別経過措置を承認済み。旧第1期の「全面凍結中」を一律の現況として繰り返さず、P-1〜P-9、T2のT1マージ待ちと実呼出部の同一変更を適用する。11/12のFR-040延期は既存PO裁定で、実装宣言は未達。
- [#159](https://github.com/masaki1025/pitchlog/pull/159)文書HEADは2026-10-20確認時`d1f3aa8ce93a7dc49a1a87ecb54e4282f528d3b2`。文書提供を耐久provider/実Port提供へ読み替えない。第1期[接続受領記録](https://github.com/masaki1025/pitchlog/blob/ce309be1fa6ffe891081b6d9662c8a0bdeacc68e/docs/features/uf8-game-recording/design.md#8-後任の接続契約受領2026-10-19)の限定受領を継承する。
- #153のコード/候補固定点`5a9e37bd263787106f08bb05224f01333e79ffc3`、資料`8de07d9836e500b44f38033577801f7a09eacf7b`。5セル・E02/E09/E10は画面側責任の候補受領済み。正式公開型・実formatter・独立oracle・製品比較は未提供でGAP-05はopen。
- 506worktreeは再開時`d9f3abb1`、544は`cefa0c0c`、545は`8046e2aa`。これらは所在確認値で提供SHAではない。担当へ公開契約の差分を照会済み。担当の未コミット成果を読んで正式提供と扱わず、変更もしない。

- 提示時にdevelop `8e4698f6dc254439b7d5e0c273cc2aef70cda657`（#163）までfast-forwardして照合した。増分は受入シート生成器と試験で、画面/契約/本計画の意味変更はない。
