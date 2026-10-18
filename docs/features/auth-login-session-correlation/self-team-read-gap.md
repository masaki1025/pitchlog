# 自チーム選手の実画面受入：既存契約の不足と最小候補

## 実コードの事実

- `api/routers/team_records.py:list_team_records`は`TeamRecordReadToken`を実行する。
- `repositories/roster.py`の同token bindingとRequiredBindingは`kind=opponent`に固定。名前編集・削除の対象も対戦相手だけであり、これを緩めない。
- `GET /players`、`POST /players`、`PATCH /players/{id}`は同tenantのself配下を扱えるが、現session DTOはtenant_id/team_nameのみでselfのteam_record_idを返さない。画面の選択肢はGET /team-recordsだけで、自チームID取得経路がない。
- tenant IDとselfレコードIDは別ID。fixtureのIDを画面へ注入して受入済みとは扱わない。

## 推奨する個別追補候補（未承認・未実装）

| 所有 | 追加差分 | 境界 |
| --- | --- | --- |
| Codex D | `SelfTeamRecordReadToken`、固定operation `ROSTER:self_team_read` | tenant WHERE/RLSに加えkind=self固定、非表示を除外、上限1。既存opponent tokenを緩めない |
| Codex D | `GET /team-records/self`、`read_self_team_record` | 既存TeamRecordRead DTO再利用、検証済みtenant context、同じC2 metadata前照合、存在しなければ汎用404 |
| Codex D | 正規roster clientのself取得、TeamScreenの自チーム選択肢 | DTO/共通client/providerを複製せず、未知ID推測なし。旧auth世代/cache拒否を維持 |

新規列・migration・grant追加は現時点では不要候補。既存SELECT列とapp role/RLSで証明する。実装前にrepository契約/base allowlist/tenant-boundary snapshot、authz registry/HTTP matrix/lock/oracle sealの具体差分・7.7受理値を別提示する。人間承認前に正式資産や製品経路は変更しない。

今回承認済みのstorage/metadata2件はこの不足から独立して実装・検査する。自チーム受入は未実施を保持し、対戦相手の既成功へ読み替えない。
