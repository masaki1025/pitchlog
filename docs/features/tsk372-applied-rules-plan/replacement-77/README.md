# PR #172 の7.7受理候補（未受理）

## 最新develop追随（2026-10-21）

- #167統合後の最新比較元は`32a4d828d6afe748e72ea16623711525f4912b6c`。追随merge`39b49e4b`で増えたのはU-F8のfrontend・文書9ファイルで、#172対象ファイルには触れない。最新の完全値は`decision-packet-32a4d828.json`（SHA-256`64513a4d8d164d05957004335acfc030d59b9a40ad9d4f8c6f267a5969381d40`）、候補入力treeは`64b42211f398c184128d7f863746d4e6ee5240d1`。下記の#166時点の資料は履歴として保持する。
- 比較元を`fb719e368f6dbc8a178cba9d42af875553c1bc1f`（#164・#166統合後）へ更新した。追随mergeは`ed9aa966`で、追加差分はU-F8のfrontend・文書15ファイルに限られ、#172対象ファイルとの競合はない。
- 最終候補の完全値は`decision-packet-fb719e36.json`へ再導出した。SHA-256は`77c18f343ed8a554852606be960b1ddbba2eca5b62b4d95266ea81e9d7becd80`。候補入力treeは`c2bfbdf7f96f1414c0fa9f5c1625f54bfbc64a36`。前回の`decision-packet.json`は当時の比較元を示す証跡として保持する。
- 9資産・外部8ファイルの全射影digest、規範識別値、corpus入力digest、#172受理記録案の内容とSHA-256は前候補から**不変**。そのうち変化する資産はruntime-authzのみで、`061eeb9e96f110e059ad51bf3026d9b420f7c636a24045809afa33e7a0f6b393`→`f4fcc729d19247df3c6cf01694e9cb6f314e2e9d290b8bc38bbc5fb5f8b124b6`。corpus入力digestは`f50b17a2bb95e95828ced277c4288dd64a0be11a2e5132fdee691683a877634b`→`b80afca5ca0249990661f0e02ffbe2bd6b53b82271d6204b471a84ddf816cef1`。
- 旧#161と一致する移植17ファイルの集合SHA-256も不変。新基線での追加レビュー対象は、#172への置換・#165以後の受理履歴直列化と新7.7記録案、最新develop追随の直接影響に限定する。既済み計画レビュー4回と製品レビューの回数は維持し、追加の独立レビューは6.3のPO裁定1回分が必要。

- 比較元: `caf5634787aeb60f692254fdcc179bb4fe34decf`（#165統合後、受理履歴24件）。旧#161の受理記録は移植しない。
- 候補入力tree: `a03a53bb49d23d7bd22b90fad828f3e67d818401`。ステップ1〜3と未コミットのステップ4製品候補、下記の記録案・候補snapshotを含む。正式履歴とcorpus manifestの更新は含まない。
- 移植した製品・契約・試験17ファイルは旧#161の最終候補とバイト単位で一致する。ファイル集合のSHA-256は`2e90b294f12f2d7b2d3c8c5b838f28e1dede6a53b02c53b1d6417b175750f925`。
- `decision-packet.json`に9資産・外部8ファイルの完全な前後射影digest、識別値、corpus digest、移植ファイル一覧を収録する。同ファイルのSHA-256は`110a2ce24127d2c99c84caf757073504de00fbdf054652c4c7fc90d9cbde0acd`。
- `record-proposal.json`は新PR ID `masaki1025/pitchlog#172`による25件目の案で、SHA-256は`50531a87072e66e0dfebdd6ec4d154c78c3b68ebba5ccd62b45dff629e9f5e9b`。`approved_by`と`approved_on`は未記入。
- `step4-candidate.patch.gz`はステップ3の公開HEADへ適用する、未受理の認可資産・試験11ファイルの候補差分を`gzip -n`で圧縮したもの。圧縮ファイルのSHA-256は`3a276fbebc26d538d41821a4e1580ee204098c24b19738edbeec5a4f654c9a2b`、展開したpatchのSHA-256は`24295dc5d0be6b0f16ddbf2d4eeef19b01d1cc1300ba5f151acb0a34526ac0ee`。実ファイルの正式履歴には反映していない。
- corpus入力digestは`f50b17a2bb95e95828ced277c4288dd64a0be11a2e5132fdee691683a877634b`から`b80afca5ca0249990661f0e02ffbe2bd6b53b82271d6204b471a84ddf816cef1`への候補遷移。正式corpus manifestは未変更。

このディレクトリは判断資料であり、正式7.7履歴・正式snapshot・corpus manifestではない。最新比較元の判断には`decision-packet-32a4d828.json`を使用する。新実値の正式受理後にだけ、計画ステップ4で反映する。旧#161の承認を新実値へ流用しない。#162へ置換順は送付済みで、#162側の`d9b3459f`に引渡し受諾と派生値の再導出条件が記録された。#172の正式受理・実統合と#162の再導出は未了。

追加確認の対象は#165からの新しい7.7遷移、受理行とcorpusの直列化、および置換PRの最終差分である。既済みの計画レビューと製品レビューは、17ファイルの内容が不変な範囲の証跡として維持する。移植後の限定レビューと本人逐行確認を完了済みとは扱わない。
