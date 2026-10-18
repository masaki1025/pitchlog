# login/session相関の局所候補・レビュー採否

2026-10-18、製品未実装。C1既済み承認・C2/U-F3の製品レビューを取り消さない。

| 周/経路 | 対象 | 結果 | 採否 |
| --- | --- | --- | --- |
| 第2周 Codex正規wrapper | 旧frontend限定案の指摘を受けた相関候補・影響 | 否決 P0=2/P1=3/P2=0 | 全採用 |
| 第2周 実Claude CLI | 同候補と添付した関連ソース | 否決 P0=0/P1=3/P2=6 | 全採用 |
| 第3周 Codex正規wrapper | 第2周P0 2件の是正・起因P0のみ | **P0=0、P0限定pass** | 自動P0追加枠で終了 |

第3周は保証をlogin/sessionの採用とC2の7経路へ限定し、markerなし初回例外を削除し、意図の条件付き書込と採用をnative Web Locksで直列化した差分を確認した。P1/P2（遷移表、caller検査、必須UI、固定503、配布境界、実ブラウザの検証手段）の追随と、第3周後の局所1ステップ/追加PRの提示は未再レビューとして人間確認へ残す。第4周・Claude第3周は追加していない。実装・実ブラウザ受入をレビューだけで完了扱いにしない。

Codex実ログのtokens usedは第2周107,202、第3周67,546。Claudeの利用量は未取得。候補は新しい仕様・可用性・PR境界の判断が必要であり未承認のまま。既C2/U-F3の独立作業・品質検査を止めるものではない。

## 固定値

- 最終判断候補SHA-256: `8c05872d4fae6940404c3d49c98345633ddd12e0d56fb3bc03e8412b1680ae77`
- round2-correlation-codex.log SHA-256: `d5878707f0ba4e24f75173ecfa3b684746e52e07e4041b2c6a960f9ffbfb02d0`
- round2-correlation-claude.log SHA-256: `6249ac88ea6f596cc450d0b07993aa659934784903205db6cc3647c0d9d24efb`
- round3-p0-correlation-codex.log SHA-256: `193758c75d0bb1fb77270897ed2794b2f6a3eec9b14b150aa88745a8f649240b`

正規Codex経路は`uv run python .claude/scripts/codex_run.py review adversarial -`、反対側は実Claude CLIで添付全文だけを評価した（read-only、ファイル読取/試験実行なし）。別主体への代替ではない。生ログは上記cacheへ保全し、秘密/資格情報を資料に含めない。
