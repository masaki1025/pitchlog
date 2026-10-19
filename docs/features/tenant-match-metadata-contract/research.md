# C2 調査記録: expected tenant と 2xx 照合証跡

## 2026-10-14 の基線

- `origin/develop`: `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`。
- backend のplayers/team-records routeは`require_tenant_access`を利用するが、clientが期待するtenant IDとの独立照合はない。
- U-F6 clientは共有Piniaから`authEpoch`を取得し、応答前後で古い認証を拒否する。tenant-bound option、expected-tenant header、2xx ack検査はない。
- U-F5は7routeを使い、`teamId=null`で要求しないこと、遅延mutationの結果未確認処理、query cache invalidationを実装済みである。

## 業務operation前の境界

当初はroute本体のrepository呼出しより前の共通dependencyを候補とした。2026-10-18の実装では、FastAPIの本文解釈・body/query validationより先に照合する承認済み優先順位を満たすため、単一の`TenantMatchedRoute(APIRoute)`を採用した。初期候補の`get_route_handler`閉包呼出しは、実sourceを固定したHEAD依存tenant-boundary検査でTB007となったため採用しない。最終候補は標準ASGI入口`handle`で、methodが対象7 operationへ一致する場合だけ照合し、既存`super().handle(scope, receive, send)`へ渡す。method/path不一致は通常405/404を維持し、本文を二重解釈しない。routerごとの手書き比較やFastAPI本体のコピー、検査器/allowlist緩和は行わない。

2xx ackはtenant IDの反射ではない。clientが送ったIDをそのまま返すだけでは独立証跡にならないため、server contextとの比較通過を示す固定literalにする。固定ackだけでは過去応答を別要求へ注入した故障を識別できないため、要求ごとのchallenge UUIDを併用し、serverは比較通過後の成功2xxだけにexact echoする候補契約とした。`Cache-Control: no-store`も対象7routeへ付ける。

## 共有資産（2026-10-14時点の調査履歴）

- PR #119 は `backend/src/pitchlog/api/tenant_access.py` を所有中。
- PR #129 はopenで、authz catalog、route registry、HTTP route matrix、base allowlist等を変更中。
- PR #131 はopenで、`.claude/core-areas.json`とtenant boundaryの複数凍結資産を変更中。
- PR #132 はopenで、core-areas/core-guardとtenant boundaryの複数凍結資産を変更中。
- C2はこれらの未統合差分をdevelop基線として扱わない。#119統合後、#129/#131/#132の所有が確定してから必要な凍結差分を導出する。

### 2026-10-18の統合済み基線と編集所有

C2の実装基線`493342be`（PR #147統合）は、上記のPR #119・#129・#131・#132を統合済みである。上記のopen/所有中は2026-10-14時点の記録であり、現在の待機条件ではない。C1ステップ2の完了により、C2は統合済みの検証済みtenant供給と共通clientを再利用する。

PR #143側が共有core/authz/repository資産を所有しているため、C2では同資産を編集しない。未統合branchの内容を基線として扱わず、現行登録済みの製品pathと認可境界のままmetadata照合を追加する。必要な既存資産不変・tenant-boundary・凍結検査の成否はC2の作業ログへ記録する。
