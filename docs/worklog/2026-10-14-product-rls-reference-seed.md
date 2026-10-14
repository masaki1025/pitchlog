# 実スキーマ経路で移行 seed の参照行が消える問題の修正(2026-10-14)

## 発端 — 12-4 のゲートが develop で通らなかった

PR #119(U-A1 δ)が 12-4 の越境テスト再実行ゲートを通そうとして、
専用インスタンスに対する 48 node のうち 1 件が落ちた。

```
tests/db/test_product_authz_cross_cutting.py::test_force_rls_applies_to_owner_with_unbound_context
```

**develop(`b81ae1ac`)を対照に同じ対象で回しても同一 node が落ちた**ので、
#119 起因ではないと確定した。

| 実行 | 生成 ID | 結果 |
| --- | --- | --- |
| #119 | `20261014T045647Z-423c9e25fe8ce22e` | 48 node / 47 passed・1 failed |
| develop(対照) | `20261014T052012Z-a8d4c3c7a2e0d4dd` | 48 node / 47 passed・1 failed(同一 node) |

**対照実験をやったのが効いた。** #119 は `contracts/authz/product/ddl-elements.json` を
触っているので、「DDL 資産を動かしたから」で片付けると誤診になりえた。
実際の差分は**関数だけ**で、表・ポリシー・移行・語彙は 0 行だった。

## 原因

| # | 事実 |
| --- | --- |
| 1 | migration `0030_seed_game_type.py` が `system_vocabularies` へ試合区分 5 行を seed する |
| 2 | `table-classification.json` の 45 表に `system_vocabularies` が含まれる(`global_read_only`) |
| 3 | `_clear_product_data` がその 45 表を `TRUNCATE ... RESTART IDENTITY` する |
| 4 | **この TRUNCATE は外部供給(runner)経路でだけ走る** |
| 5 | 結果、移行が入れた 5 行が消えてからテストが始まる |
| 6 | 当該テストは「所有者に試合区分 5 行がちょうど見える」と表明する |

**製品の欠陥ではない。** テナント分離に穴は無く、**試験基盤と移行 seed の両立**の問題。

**所有は TSK-479 / PR #122。** `a3d07713`「所有者限定RLSで試合区分seedを往復検証」が
当該テストの期待を書き換えた。**担当セッションが稼働していないため本 fix が代行した**
(人間の指示 2026-10-14)。

## なぜ誰も気づかなかったか

**#97 が 48 node green を取ったのは 2026-10-07。**
`scripts/product_rls_real_schema/` は #97 以降 1 行も動いていない。
**#119 の実行が #97 以来はじめての実スキーマ実行**であり、
**2026-10-13 に入った期待がそこで初めて試された。**

**ゲートが実際に回っていれば 2026-10-13 の時点で捕まっていた。**
これは「**入口を開く PR で 12-4 の記録が落ちる**」論点の実害の側の裏付けである
(PR #95 も HTTP 入口を開いているが本文に判定記録が無い)。

## 採った案

**供給の開始時に移行済みの対象から `global_read_only` 4 表の内容を控え、
各 TRUNCATE の直後に superuser 接続で書き戻す。**

**seed の値をコードへ複製しない** — 移行との二重定義を作らない(NFR-018)。

採らなかった案: TRUNCATE 対象から外す(試験間の分離が壊れる)/
テスト側で 5 行を前提にしない(#122 の往復検証の意図を失う)/
seed を fixture へ書き写す(二重定義)。

## 敵対レビュー 3 周 — 10 件採用・1 件不採用

| 周 | 判定 | 主な指摘 |
| --- | --- | --- |
| 1 | P0 | **現在の FORCE 状態を復元すべき状態として扱うため、すでに外れていたら外れたまま残す** |
| 2 | P0 | **控えを所有者接続で取るため RLS で見えない移行 seed(在籍区分 3 行)が黙って失われる** / **控えの時点は DDL 適用前なので RLS 照合が必ず落ち、実スキーマ経路が 1 件も試験に到達しない** |
| 3 | P0 | 復元された行そのものを誰も照合していない(採用)/ 移行 seed の欠落検出(**不採用**) |

**2 周続けて「保護や前提が黙って失われる」型だった。**

**1 回目の反映が 2 回目の P0 を作り込んでいた。** さらに 2 回目の P1 は
「**いまのままでは runner が最初の試験に到達しない**」であり、
**回さずに渡していたら即座に止まっていた**。
**使い捨て DB の 48 passed はこの経路を一切検証していない**ことも、レビューが正しく指摘した。

### 1 回目の P0 の直し方を変えた

当初案(FORCE を付け外しして戻す)は**失敗の種類を 1 つ残す**。
レビューが代案として出した **superuser 接続での復元**は、superuser が行セキュリティを
完全に迂回するため**その種類ごと消える**。`applicator_dsn` が既に superuser として
供給されていることを実測で確かめて採った。

### 不採用 1 件とその理由

**「移行 seed がそもそも欠けていた場合に落ちる条件が無い」は採らない。**
本修正は TRUNCATE で消えた参照行を復元するものであり、
**移行が正しく seed したかは移行側の試験の責務**である。
ここで期待行を表明すると移行と二重定義になる(NFR-018)。
**TSK-479(PR #122)の移行試験へ申し送る。**

## DoD — 実スキーマで 48/48

```json
{"generation_id": "20261014T094359Z-a4e342bbc17b10e2",
 "target_digest": "200beaf585064556aefe6f9b19e38aff98b93d34c55613b67b74d0eac7e7399e",
 "migration_head": "0030_seed_game_type",
 "catalog_violations": 0,
 "ddl_asset_digest": "bafdec1b184d953403903a174b98a3b47c76773e3aec0813fd24f642c9e8680c",
 "test_tree_commit": "a3d077130b2c456f42b3d23faceabb25bd16b2bd",
 "executed_nodes": "7773d96181c677a80af4a05eaf41ce883967e1866c1fa8cfe76094950ae107f1",
 "docker_unreachable_during_tests": true}
```

**JUnit の実測: 48 node / 失敗 0。**

## 途中で踏んだ運用上の落とし穴 4 つ

| # | 症状 | 原因 |
| --- | --- | --- |
| 1 | `compose サービスの実コンテナを一意に特定できない` | **worktree から `docker compose` を叩くとプロジェクト名が worktree 名になる。** 対象定義の `compose_project` は `pitchlog` 固定。**`-p pitchlog` が要る** |
| 2 | `password authentication failed` | **ボリュームが古い initdb のままで、その後に変えた `POSTGRES_USER` のロールが存在しない。** これらは **initdb の 1 回きり**しか効かない |
| 3 | `healthy` なのに使えない | **`pg_isready` は認証の成否を見ない** |
| 4 | `予期しない実行失敗` | **runner は接続情報の漏洩を防ぐため例外を握り潰す。** `docker logs` と、伏せ字つきの診断が手がかりになった |
