---
feature: mvp-runner-physical-evidence
status: proposed
branch: feature/mvp-runner-physical-evidence-20261107
承認: root の PO 委任判断待ち（2026-11-07）
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# 走者操作の物理原本を実観測へ結合する

起点は `d83bc1f31a5e5466644702a0fe44c7e9889a1580`。実画面の先行安打後 `steal-nonpitch` は prepare に到達したが `ProgrammingError` の SQLSTATE は診断待ち。静的には、v3 prepare が旧 `runnerAdvanceOverrides.overrides` だけで `status_source` を判定するため、実 `RunnerEventT1Input.runnerObservation.perPitch` から生成した `manual` 走者行を拒否する。旧検査は走者アウトを一律拒否する。根拠は `~/.cache/pitchlog/runner-np-prepare-static-20261107/REPORT.md`。この静的所見を実例外の確定原因とは扱わない。

| # | 実装単位 | 成立条件 |
|---|---|---|
| 1 | 現行 post-P3 prepare の走者物理証拠を閉じる | 親 `prepare_play_prefix_projection` の全本文 SHA256 `cb25ab6f9e8ab9906d69821f452521dbc9e2e2a917e3630689307d862860f917` と宣言を厳格照合し、現行 v3 runner 分岐だけを限定 overlay。旧通常投球・打球・P3 baseline と非投球後 normal 分岐を保持。真正 `runnerObservation.perPitch` の runner ID/base/明示原因/到達先を唯一 T1 の out 対象・進塁結果および保存予定の物理10列と全値照合する。hold/進塁/アウトの `status` と `status_source` は既 Python 投影と同一の保存ラベル宣言を使い、計算や未観測原因を追加しない。未知操作/欠損/矛盾/別走者を拒否する。 |
| 2 | 純対向と共有接合 packet を固定 | 盗塁、牽制アウト、他の既許可 runner 形、通常球、旧打球の正負を、唯一核の既期待値と同一保存行で検査。旧本文の変換箇所以外の byte・署名/owner/ACL/nonce/XID/tenant/拒否順を比較。`first_ball_product.py` は root 専有なので現行 post-D03/post-RR 登録末尾への最小 cache patch だけ渡し、正式 catalog/assets は変更しない。root の SQLSTATE 診断後に実 PG/画面・故障全取消を別途確認する。 |

作者が編集するのは本計画、`backend/src/pitchlog/authz/runner_physical_evidence_sql.py`（新規）、必要なら保存ラベルの単一宣言と `terminal_pitch_projection.py` のその参照、対応する専用 pytest のみ。既 `terminal_pitch_write_stamp.py`/`p3_function_product.py`/`first_ball_product.py`/共有 catalog・正本・台帳・他 WT は編集しない。共有登録は cache patch と全 byte/宣言 pin を root へ渡す。

`guard_play_prefix_runner_insert` は現行で保存予定10列と `NEW` を全値照合し、`finish_play_prefix_projection` は挿入後の走者集合を照合するため、旧 `runnerAdvanceOverrides` 条件の複写は見つからない。両関数および current P3/read/started RR の本文・pin は不変更を初期方針とし、変更が必要と判明した場合だけ plan 追補を root に提示する。旧 P3 の親11本文 pin、`read_started_play_prefix_history_page` の元 reader pin は維持する。

本候補の純検査は実 DB 保存成功・正式受理を意味しない。走塁の未裁定配置、D07 の二死二三塁単打以外への補助拡張、未対応 Batted applied、打点・第3アウト因果の推測は含めない。
