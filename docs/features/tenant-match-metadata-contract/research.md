# C2 調査記録: expected tenant と 2xx 照合証跡

## 2026-10-14 の基線

- `origin/develop`: `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`。
- backend のplayers/team-records routeは`require_tenant_access`を利用するが、clientが期待するtenant IDとの独立照合はない。
- U-F6 clientは共有Piniaから`authEpoch`を取得し、応答前後で古い認証を拒否する。tenant-bound option、expected-tenant header、2xx ack検査はない。
- U-F5は7routeを使い、`teamId=null`で要求しないこと、遅延mutationの結果未確認処理、query cache invalidationを実装済みである。

## 業務operation前の境界

照合はroute本体のrepository呼出しより前の共通dependencyで行う。routerごとの手書き比較を作ると経路漏れと意味差が生じるため、単一実装と7routeの適用試験で固定する。

2xx ackはtenant IDの反射ではない。clientが送ったIDをそのまま返すだけでは独立証跡にならないため、server contextとの比較通過を示す固定literalにする。固定ackだけでは過去応答を別要求へ注入した故障を識別できないため、要求ごとのchallenge UUIDを併用し、serverは比較通過後の成功2xxだけにexact echoする候補契約とした。`Cache-Control: no-store`も対象7routeへ付ける。

## 共有資産

- PR #119 は `backend/src/pitchlog/api/tenant_access.py` を所有中。
- PR #129 はDraft/open・merge state `BLOCKED`で、authz catalog、route registry、HTTP route matrix、base allowlist等を変更中。
- PR #132 はDraft/open・merge state `BLOCKED`で、core-areas/core-guardとtenant boundaryの複数凍結資産を変更中。
- C2はこれらの未統合差分をdevelop基線として扱わない。#119統合後、#129/#132の所有が確定してから必要な凍結差分を導出する。
