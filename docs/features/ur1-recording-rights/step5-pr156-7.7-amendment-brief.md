# PR #156 7.7受理値の連動digest是正案（2026-10-19、未受理）

## 停止理由と固定範囲

比較元は`015dfa9db0b7b8740369911a9cb5195dd59a62ea`、受理時のローカルHEADは`8a2f332626a57762cab90d6957a56624a5e8e650`、限定レビュー差分SHA-256は`d054e2397564c314505a808bb099e55f593576d2740840915bd3a9939cf75d27`。POが受理した元[payload](step5-pr156-7.7-payload-proposal.json)・[単一記録案](step5-pr156-7.7-record-proposal.json)は改変しない。

資産revisionを承認どおり8件進めると、`db-api-inventory.json`の実ファイルSHAが変わる。`base-allowlist.inventory.sha256`を旧値に据え置いた元候補では、TB002検査器がinventoryの封印不一致で拒否した。また、revisionを進めた4資産の`source_digest`を旧値に据え置くと同検査器が各資産を拒否する。検査器・許可条件・製品コードの変更は不要。診断に使った正式資産・snapshot・archiveの未コミット変更は戻した。宣言とJSON登録の2ローカルコミットは保持し、pushしていない。

## 必要な最小追加差分

| 対象 | 元受理値側 | 是正案 | 理由 |
| --- | --- | --- | --- |
| `base-allowlist.inventory.sha256` | `b103a48b6190e6e18cb45e456c75ec26321571c10fafc5d2c2152011f0bed8d3` | `522b6351474f200da48451edd511ba944c05d5159142b675f9ccec095d76b636` | revision 16のinventory実ファイルSHAへ一致させる |
| `cache-invalidation-contract.source_digest` | `fe17aaac414b51043ae1c978b8dd054c48d005aa824454d29ff8ec308cf9be7c` | `21fccdb4522166611918694fe32de05d437ccd5705b1d0eafedaddcb099e5cd7` | revision 16の自己封印 |
| `repository-contract.source_digest` | `117c924bf5c0174b4846c301d3a6fbb0e2457283fccd2edbf7de7a3139baedae` | `5a961d7acca738d13fca0cd96d79c6b004854f521acce4415d6ed16c06faa2b5` | revision 22の自己封印 |
| `runtime-authz-contract.source_digest` | `13eeb95f54a8a713620a12c369505311349e72148c521141ed524ece91b0f62d` | `fa4bd7776c1e16bf4ddf5aa96601dc87e6788da7d52c636d56ed6bacc7c92b83` | revision 18の自己封印 |
| `tenant-context-allowlist.source_digest` | `fc213ee3133d0463df96f8d71e68ce93487926373508853d5636fc284ec191cc` | `a7eaf9a0498ef43d0741a20221ead0f3ad47b5f0d91f64b50817202a8399b260` | revision 17の自己封印 |
| base after snapshot・射影SHA | `7c62db133f0859f581313fac39279bdad6c62d182d33541f250a54eaba42787c` | `8e7f41fcf9d1edca4e4bac871bebc6094fec37763b65659f246bb80379030f9e` | inventory参照SHAが凍結射影へ入る |
| archive corpus after digest | `1535ff098defae52a7cdd653e54032d9244f118f62c6801f8fc4fc3c1f085085` | `51264ae66762fc42e5e789ecf3e7c4067528e2869c36939394b91ed6af95bdf1` | corpusがraw JSONを含む |

4資産の`source_digest`は凍結射影の除外フィールドであり、当該4件を含む残り8資産のafter snapshot・全資産のrevision・before・既受理履歴は元案どおり。#156の単一記録という単位も変えない。許可シンボル・操作・経路を拡大しない。

新しい完全[payload案](step5-pr156-7.7-amendment-payload-proposal.json)のSHA-256は`8559617ed7714bc85a8dfa51f6bfad866aa43d40eaf39d266eeba4a2a90e96dd`。[単一記録案](step5-pr156-7.7-amendment-record-proposal.json)のSHA-256は`550d5c78aa77597c52459514f017205580b23ab03c3026432519c41fb6d41025`。記録案に承認者・日付はまだ記入していない。

## 診断結果と次のゲート

是正値を一時的に反映した診断状態では、TB002の`test_repository_is_green`が成功し、archive関連36件が成功した。元候補でのTB002全件初回はinventory封印不一致により多数失敗、自己封印追随後は350件成功の時点で旧候補base snapshotの孤児1件により停止した。孤児を除いた後の全件完走は未実施であり、正式な全件合格やCI成功とは扱わない。

改訂案の7.7正式受理が必要。受理後にのみ8資産のrevision・連動digest、#156の単一履歴記録、正しいbase snapshotと他7件のsnapshot、検査器snapshot、corpusを反映し、全件検査・通常push・CI・PR更新へ進む。元受理値を黙って差し替えない。旧レビューP0/P1/P2=0は元の限定差分に対する結果であり、この連動是正差分の独立再レビューは未実施。
