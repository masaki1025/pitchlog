---
date: 2026-09-16
topic: alembic の fileConfig がアプリのロガーを無効化する問題の是正
branch: fix/alembic-logging-isolation
---

# 作業ログ: 2026-09-16 alembic の fileConfig によるロガー無効化の是正

## やったこと

- /task-start(2026-09-16): TSK-387 の PR #67 が CI red になった原因の根本側を別タスクとして起票
- /investigate(2026-09-16): 2 並列(spec-checker / decision-tracer)+ 自分の実測 → `research.md`
  - legacy-analyst は外した(ロギング設定は旧 Baseball_Scoring と接する面が無い)
- /plan(2026-09-16〜17): 計画書を作成。**敵対レビュー 2 周**(コア領域のため `review adversarial`)→ 承認

## 決定

- **決定①** 修正は `env.py` の `fileConfig` へ `disable_existing_loggers=False` を渡す 1 行。
  `alembic.ini` の `[loggers]` に `pitchlog` を足す案は却下 —
  **ロギング方針が未決の段階で alembic.ini がアプリのログ水準を決めてしまう**
- **決定②** `error_logger` フィクスチャは**残す**(1 周目レビューで方針を反転)。docstring のみ現況化
- **決定③** 検査は**子プロセスで env.py を実行**する。pytest プロセスの logging 状態を汚さないため
- **重さ分類 = コア領域**。意味範囲としては 6.3 の境界定義表に直接該当しないが、
  **機械 paths に登録済みで規則④が PR 単位の例外を禁じる**ため運用上コア PR

## レビューで訂正した自分の誤り

**1 周目(P0 5 件・全件正当)**

- 「**NFR-015 違反の是正**」は過大 → 「**顕在化経路のうちログ側が将来無効化されるのを防ぐ予防的是正**」。
  アプリのプロセスは `env.py` を import しないため、現時点で製品の挙動は壊れていない
- 「**alembic は自分の設定だけを行い、他人のロガーに触らない**」は**事実誤り**。
  CPython の `_handle_existing_loggers` は非列挙ロガーへ `disabled` を代入するため、
  **`False` は意図的に無効化されていたロガーも有効化し直す**
- **意味判定の典拠が誤り** — TSK-343 の除外撤回は**そのタスク固有の判断**であって、
  ロギング変更が 5 領域に属する根拠にならない。正しい根拠は**規則④**
- 「3 ファイルだけ」と書いて **4 つ列挙**していた
- **Claude 一次レビューが DoD に無く**、典拠 `:370` も誤り(正は `:371-372`)

**2 周目(1 周目の反映は P0 なし・新規部分に P0 1 件)**

- **子プロセス設計が実行可能な水準になっていなかった** — `monkeypatch` は子プロセスへ継承されないのに、
  `alembic.context` のスタブ化を書いていなかった。起動条件を表で固定した
- 「**非列挙ロガーすべてを再有効化する**」という訂正も不正確 —
  **列挙ロガーの子孫**(`alembic.autogenerate.*` 等)は `disabled` ではなく
  `level=NOTSET` / `handlers=[]` / `propagate=True` にリセットされ、**引数の影響を受けない**。
  → **番兵ロガーの qualname を `alembic.` / `sqlalchemy.engine.` の子孫にしない**ことを明記
  (気づかなければテストが静かに空振りしていた)
- **表明 4 が副作用を受け入れ条件に格上げしていた** → characterization test と位置づけ、
  **落ちたときに副作用を復活させてはならない**ことを先に決めた
- スナップショットの検査面が主張より狭かった(`datefmt` 欠落・`handlers` の定義が未定)
  → 正規化スキーマを列挙し、**DoD の主張を「列挙した項目が一致」に狭めた**
- **CPython の行番号引用**は同じ 3.12.3 でもビルドでずれる(実測で食い違い)→ **関数名で引く**
- 親プロセスの前後比較は**過剰反映**だったので削除。**2 ステップを 1 本へ統合**

## 実測

- `fileConfig` 前後: app ロガー `disabled` が `False` → **`True`**(既定)/ `False` 指定なら `False` のまま。
  alembic 側の 3 値(alembic=INFO / sqlalchemy=WARNING / root handlers=1)は**どちらでも同一**
- env.py が `fileConfig` に到達する直前の `loggerDict`: **実ロガー 34 件・`disabled = True` は 0 件**
  (`.python-version` = 3.12.3)。→ 決定①の副作用を許容する根拠 1。**将来の保証ではない**
- `fileConfig` を呼ぶのは**リポジトリ全体で `env.py:17` の 1 箇所だけ**

## 未決・次の一歩

- /implement へ。**ステップ 1/1**(根本是正 + 子プロセス回帰テスト + docstring 現況化)
- **別タスクへの申し送り 2 件**(計画書 6 節): ① `fileConfig` の**ハンドラ全消去・close** は
  引数に関わらず起きるため「同一プロセスの logging 構成の保全」は本修正で解けない
  ② 非列挙ロガーの再有効化は現時点の実測で無害だが将来の保証ではない
- **台帳の未処理の申し送り** — `harness-evaluation.md:2756`「昇格の可否は PO 判断事項として上げる」
  (候補「検証コマンドを人が選ぶと…」の `H-*` 採番)。本タスクの射程外
- **`codex_guard` の誤検知を 1 件観測** — heredoc 本文に「Codex」の語が含まれるだけで
  コマンド字句解析に失敗して遮断された(Write ツールへ切り替えて回避)。
  台帳の既存候補「guard 群がコマンド文字列の部分一致で誤検知する」の再発。/pr で追記を判断する
