# 終了・追記再開の7.3起案作業ログ（2026-11-06、cache-only）

- actual worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-nonplay-product-connection`、開始HEAD `2e0205908108492fc72d8378803e7d68a34b6983`、featureブランチ。作業木へは未反映。
- 根拠: `/home/ymdms/.cache/pitchlog/mvp-lifecycle-product-author-20261106/packet.json` SHA256 `2f464208ef8ed53e78048ea5370e55204b60584b7397b51272882b1bed91fee8`。同cacheの`MINIMUM-INTERFACE.md`と`formal-proposals/sync-protocol-v0.13-draft.md`、`adr003-d11-registration-draft.md`を照合。作者の実PG・全API・実画面合格報告はない。
- PO権限: rootからの既PO委任。技術wire/保存形の具体化は許可。野球の意味、D5、拒否順、Shouldの再裁定は対象外。人間本人の逐行確認・署名を代理記録しない。
- 7.3適用版: **v1.19**。approved条文コミット `3092c6dbfd7e69a2cc96efccd46de72a87f4841b`。現HEADの7.3節と同コミットの7.3節は同じSHA256 `c2955c8a4616414524983f484b836fc84415e44e1bcb465bc9824ae12a4548f9`。実適用版は初回敵対レビュー時に再照合する（7.3-1）。
- 初回全対象: 要件書v2.20、同期プロトコルv0.13、データモデルv1.6の**全文**を一括１件でレビューする。３文書の新履歴行とfrontmatterはすべて`in-review`。承認・approved化・索引current切替は未実施。
- 受理scope案: 既Must6種へ追記再開を末尾追加し、#13 `game_reopen`をD1/D2付きP1/端末送信P2とする。閉V7のend/reopen・最新target全３値、真正control bridge、独立lifecycle admission/head、sameTXのstatus/成績版/receiptと旧確定版失効を規範にする。FR-005の自動検知とFR-010の宣言は分離し、reopen中の終了条件由来lockだけを解除する。正式contract/enum/CHECK、実DDL/ACL、実PG/実機は後続実装の受け取り先。
- 既規範保全: 旧#1〜#12、FR-040 Should、P3訂正、DI2/DI3/DI5、C2/RG1、結果不明・旧要求後着遮断、既全caseを変更しない。`docs/legacy/`・共有台帳・実DB・`.env`・P6へ不触。
- 現在の段階: 草案生成と整合確認。敵対レビュー0回、採否0件、反映0周。root/POの承認はまだない。


## rootによる実起案（2026-11-06）

- actual worktreeを feature/mvp-lifecycle-product-connection（起点a7cc3c0b）へ分離し、3文書のbefore/after全SHAをpacket eeecf3c2…と照合して起案。旧cache-only記述は作成時履歴であり、ここからactual in-review。
- 適用版暫定は7.3 v1.19/条文コミット3092c6dbfd7e69a2cc96efccd46de72a87f4841b。初回開始前に現条文と固定版を再照合する。全3正本の全文を対象とし、今回が初回。非作者レビュー前にapprovedにはしない。
- PO委任によるroot判断はこの起案とレビュー実施順のみ。意味/正式本文の最終受理は未成立。

- 初回開始前のroot再照合: 現7.3節は固定条文コミットと全byte一致。節SHA256 c2955c8a4616414524983f484b836fc84415e44e1bcb465bc9824ae12a4548f9。適用版はv1.19を維持する。

- 初回前の記録訂正: 7.3-1の「approved条文を収録する最新コミット」は起案第一親 `a7cc3c0baa05fd1a1639e1f98e8f8f7bb39ad229`。3092c6dbは条文の元固定点として保持し、ゲートの適用条文コミットはこの第一親へ訂正。条文全byte/SHAは同一で版v1.19不変。非作者レビューはまだ開始していない。
