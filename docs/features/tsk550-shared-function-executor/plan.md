---
feature: tsk550-shared-function-executor
status: active
承認: 済（2026-10-15・PO、HEAD 2f57e14d のA専用2ステップ計画と9資産の変更範囲）
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f993b75e687810fa2b0e0b6edc228bc
branch: feature/tsk550-shared-function-executor
created: 2026-10-15
計画レビュー周回: 3
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: TSK-550 共有固定関数実行器A

## 承認と境界

POは2026-10-15、TSK-550本体の`ae380801`にある独立レビュー済みA/B/C**分割追補**を承認した。続いて`2f57e14d`時点の本A専用2ステップ計画と[資産ゲート案](asset-gate-proposal.md)の全9資産の変更範囲を承認した。第2回レビュー後の反映差分も今回の人間確認対象である。Aは最新develop起点の別worktree・別PRで製品固定関数登録**0件**の共有実行器だけを先行する。統合後のBは段階A resolver1件、CはU-R1 RG1専用2件を独立した個別ゲートで登録する。旧「最初の登録はresolver1件」の順序制約だけがこの分割では失効する。TSK-550本体のcodec、規則値/出所、DB関数、U-R1のRG1関数、製品保存成功はAへ含めない。

本計画は既存TSK-550計画のステップ4から共有部分だけを切り出す。独立レビュー第1回P1 5件を全採用し、第2回P0/P1/P2=0で分割案として可。**全9資産の変更範囲は承認済みだが、実digest・7.7前後状態・正式受理、B/Cの関数権限、TSK-550本体ステップ3の正本人間承認は別ゲート**。今回の許可は本計画ステップ1だけであり、製品コード・凍結資産・ステップ2・マージへ進まない。

## ファイルと実装方針

**正本反映宣言（7.6）**: Aは既承認のTSK-550本体・U-R1の実装単位分割に従う共有repository実行器であり、`docs/requirements/requirements-pitchlog-2026-07-22.md`、`docs/design/data-model.md`、`docs/design/product-authz-surface.md`、`docs/design/sync-protocol.md`、`docs/adr/**`、`docs/development/dev-harness-design-2026-08-07.md`の本文反映は**なし**。AにはDB関数・権限・規則データ・RG1状態を含めない。これらの正本を変更する必要が出た場合はAの射程を止め、7.6で改訂ゲートを別判定する。計画・受理記録の同期はTSK-550/U-R1のfeature文書と作業ログに限定する。

- `backend/src/pitchlog/repositories/operation_registration.py`または隣接する専用moduleに、frozen固定関数登録型を加える。製品registryは空集合。登録型はexact token型、固定capability/function identity、schema修飾単一関数呼出しのSQLAlchemy文、固定bind集合・型、戻りdecoderを保持し、callerからSQL/関数名/Session/tenant IDを受けない。
- `operation_registry.py`で既存DML ID/型との横断重複を拒否する。既存`PRODUCT_OPERATIONS`とDML `run`の検査・許可集合を緩めない。`transaction.py`の同一`_TenantTransaction`に`run_function`を加え、`run`と同じscope失効・`TenantContext` exact型/発行証跡/tenant照合を実行直前に行う。session/transactionの生成・確定・取消・closeは既存scopeだけが所有する。
- 登録時に固定SQLの関数identity・引数/bind・戻り列を検査し、実行時は検証済み文とbindだけを使う。結果は同一transaction内で完全実体化し、登録済みdecoderが行数・列・型を検証して既存の不変`TenantOperationResult`へ閉じる。未登録tokenは製品registryが空のため必ず拒否する。
- 単体試験では製品registryへ関数を加えず、**試験専用の閉じた登録入力**で正常1件と変異例を同じ`_TenantTransaction.run_function`入口へ通す。固定SQL/decoder検査が空振りしないこと、DMLとのID/型衝突、偽造/派生/未登録token、任意SQL、Session注入、失効scope、tenant文脈改変、実行・decoder・例外時全取消を確認する。A単体でDB直関数呼出しの遮断を主張しない。B/CのGUC・実効ACL・直呼出し試験は各個別ゲート。
- 共有`repository-contract.json`の固定関数ID欄、`base-allowlist.json`の`run_function`/`SQLA_SESSION_EXECUTE`許可、runtime authz/capability、生成契約/検査器/fixture、受理済み履歴と比較corpus`tests/fixtures/frozen-archive-cases/manifest.json`の再pinをA所有の具体差分として固定する。承認範囲を越える凍結資産変更は行わない。実revision/digest・before/afterと7.7正式受理は、ステップ2の実装後に別ゲートで確定する。既存履歴は改変しない。製品/試験パス候補`backend/src/pitchlog/repositories/*`と`backend/tests/test_*_boundary.py`は現行core-areasの`tenant-isolation`既存globに収まり、新しいpath追加を要しないことを`matched_paths`で検証する。追加が必要なファイル名へ変えた場合だけ宣言・登録を別コミット/別ステップで扱う。

## 実装ステップとDoD

| # | 範囲 | 合格条件 |
| --- | --- | --- |
| 1 | 固定実行器と凍結資産のexact差分・7.7受理単位を起案 | 最新developのrepository revision/allowlist revision、公開面、固定関数ID欄、`SQLA_SESSION_EXECUTE`許可、生成契約、比較corpusをbefore/after候補として列挙。Aは登録0件と試験専用登録を区別。今回は製品コード・凍結資産を変更しない。計画・9資産範囲承認を記録し、実装後の実digest・7.7前後状態・正式受理を別ゲートに残す |
| 2 | 個別承認後の共有実行器、凍結契約、単体・拒否試験と全検査 | 製品登録0件。試験専用登録を同一scopeの`run_function`から実行・decoder・失敗時全取消まで通す。DML非緩和、固定SQL/bind/decoder、未登録・偽造token/任意SQL/Session注入/失効scope拒否を確認。承認された凍結差分だけを更新し7.7 before/after・追記履歴・生成物・比較corpusを照合。backend Ruff format/check・ty・pytest、root凍結/迂回/guard試験を**最終headで緑**にする。A製品registryが空であることと既存globによるコア検出を確認。独立コア領域敵対レビュー・人間逐行確認はPRマージ前ゲート |

ステップ1・2は別コミット。ステップ2は凍結資産と製品コードを同じ最終headで検査し、未承認資産を含む赤い中間headを実装合格と扱わない。ステップ1で実digest・7.7前後状態・正式受理の単位を示す。ステップ2の実装は別指示で開始し、実装後の正式受理まで公開の成功を主張しない。U-R1の所有worktreeは変更せず、TSK-392の計画・受理記録の同期は担当へのコメントで依頼する。

**計画レビュー採否**: 第1回全文はP0=2/P1=3/P2=0で否決、5件全採用。分割承認を新計画承認として表示した誤りを`承認: 未`へ訂正し、不要なpath追加層とステップ分割の矛盾を解消。資産未承認の赤い中間head、比較corpus、試験専用登録が同じ`run_function`を通る条件を明記。第2回差分・影響節はP0=0/P1=1/P2=0で否決し、正本反映宣言の欠落を上記へ採用。基本2周を使い切ったため、この最終反映は人間承認時の逐行確認対象にする。新計画の人間承認は上記PO判断で成立した。ステップ1の記録・検証後に同ステップだけを完了とし、ステップ2の別指示までは実装へ進まず、実digest・7.7前後状態・正式受理は実装後のゲートとして維持する。

2026-10-15のPO裁定で、[ステップ2の二段階ゲート追補案](step2-gate-addendum-proposal.md)について追加の独立レビューを1回実施した。P0=0/P1=3/P2=0の指摘を全採用し、反映内容を作業ログへ記録したため、6.1に従い計画レビュー周回を3へ更新した。追補案は人間承認待ちであり、上記の承認済みステップ表・着手条件をまだ置き換えない。
