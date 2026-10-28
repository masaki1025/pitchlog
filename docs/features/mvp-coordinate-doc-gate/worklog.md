# 単一ゲート運用記録

2026-10-28起案。PO委任によるCodex主担当判断。適用規範の暫定固定はapproved harness v1.19、条文commit 64c9eec75690d55f1a4f6e9b4594ae2fe7617892、全文SHA-256 12753078ce7804f401d55101c4f2fffa30ce9a537d3c646873bfc3e1af5adbd5。初回レビュー直前に再照合し、以降固定。ゲート対象はADR-003 v0.10と要件v2.18の2正本で記録1件。初回は全文、過去の計画レビューをゲート回数へ転用しない。

前提：WB ADR v0.8と既承認v0.9の不一致はba3e1082で3行のみ保全。既成果7d6ce544との同値を確認し、採用済T1 J5/J6を落とさない。今回新改訂はD18=A/D11=Aのみ。J2未回答。草案sourceはcache d18-d11-single-gate-draft-20261028、draft patch 8f5ad625…（完全値は同manifest）。変更履歴in-reviewと本記録を同commitで固定し、初回敵対レビューへ渡す。

未実施：初回レビュー、指摘採否/反映、J2/最終PO判断、approved化、索引更新、実装/ベクタ/host/DB。3層の既要件を免除しない。
