---
feature: phase4-6-acceptance
type: research
date: 2026-08-25
---

# 調査メモ: Phase 4-6 — win-setup ランナー選定 + NFR-021 Phase 4 受入判定

## 問い

Phase 4-6 の実装計画を書くために、次の 4 点を典拠付きで確定させる。

1. **合格の定義**: `gate_kind: phase4` の受入で「合格」とは具体的に何を満たすことか。証跡に必須の項目は何か(正は要件書 NFR-021)。
2. **win-setup ランナー選定**: 何が候補として既に洗い出されており、どこまで決まっていて、何が未決か。
3. **機構の実態**: 実装済みの `verify_nfr021_evidence.py` / `check_nfr021_append_only.py` / 予約レコード / 証跡テンプレートを、実際にどう呼び出し・どう埋めるか。
4. **境界**: 4-6 でやってはいけないこと(`P4-後` の責務・過去に否決された案)は何か。

調査方法: spec-checker(要件突合)/ decision-tracer(決定経緯)/ 広域探索(機構実態)の 3 並列。矛盾点は原典で裁定した(F 節)。

## 本メモの有効範囲(2026-08-26 追記 — 重要)

> **本メモは調査時点(2026-08-25)の記録である。** その後の確定ゲート 1〜2 周目により、**タスクの構成そのものが変わった**。
>
> **失効した部分(現行は [計画書](plan.md) 4 節が正)**:
>
> - **結論(要約)の 2**(「PR 内で選定 → `T` → `E` の順序が強制される」「受入は feature ブランチのツリーに対して実施する」)— **1 PR 構成を前提としていた**。現行は**前提 PR(第 2 号)を先に `develop` へマージし、4-6 が `develop` 起点で `T` を採る 2 PR 構成**である
> - **E 節「実行順序の制約」**・**F-1 の裁定**(feature ブランチのツリーで受入する)— 同上。**受入は `onboarding.md` v1.1 の 2 章 2-1 節に従って候補コミットを OID で固定して取得する**
> - **C 節の「未決」表現**(「未決はどの案を採るかのみ」)— **選定は (d) で確定済み**(G-1 に決定を追記済み)
> - **D 節・G 節の前提**のうち「4-6 が正本改訂と受入判定を同一 PR で行う」ことを前提とした記述
>
> **有効な部分**: A 節(合格の定義)/ B 節(機構の実態)/ C 節の調査結果そのもの / H 節(Web 調査結果)。**これらは構成変更の影響を受けない。**

## 結論(要約)

1. **合格条件は 5 項目に確定**(ハーネス pytest / backend pytest / frontend Vitest / 開発 DB 接続 / backend・frontend 起動疎通)。一致性・越境・E2E・同期故障系・Playwright は**明示的に対象外**(要件書 `:921`)。証跡の必須記録は **11 項目**(同 `:923`)。
2. **最大の制約は実行順序**: win-setup 選定が触る正本(設計書・要件書・`.github/workflows/`)は**すべて失効対象パス**であり、**`T`(試験コミット)より後・`E`(証跡コミット)以前に置くと証跡が失効する**。したがって **PR 内で「選定を先に確定 → その状態を `T` として受入 → `E` を積む」順序が強制される**(E 節)。この帰結として、**受入は `develop` ではなく本 feature ブランチのツリーに対して実施する**(F-1 の裁定)。
3. **win-setup 選定は「部分的に決着済み」**。役割(補助検査・受入ゲートの代替にならない)と除外(GitHub-hosted Windows Server は受入プロファイルの証跡にならない)は approved 正本で確定済み。**未決はどの案を採るかのみ**で、候補 4 案が申し送られている(C 節)。**後送りは明示的に禁止**(設計書 `:810`)。
4. **4-6 でやってはいけないことが 4 つ明文化されている** — `/release` 手順 0 の置換 / 13 章の現況追随 / 完了証跡の記録 / マージだけでの完了宣言。いずれも `P4-後` の責務(D 節)。加えて **v1.9 で明示的に閉じた 3 提案の再提案も不可**。
5. **受入は人間(判定者 = PO)が実施する**。Claude は操作補助と記録の起草のみ(設計書 `:638`)。onboarding は**新規 WSL ディストロ作成から**の完走で、対話的ログイン・GUI 操作など**人手が必須の箇所が 17 件**ある(B-5)。

## 詳細と典拠

典拠の記法: 要件書 = `docs/requirements/requirements-pitchlog-2026-07-22.md` / 設計書 = `docs/development/dev-harness-design-2026-08-07.md` / 台帳 = `docs/development/harness-evaluation.md` / 受入 README = `docs/ops/nfr021-acceptance/README.md`。

### A. 合格の定義(正は要件書 NFR-021)

#### A-1. 受入プロファイル — 要件書 `:919`

> Windows 11 x64 ホスト＋**新規に作成した WSL2 ディストリビューション「Ubuntu 26.04 LTS」の番号付き x64 WSL イメージ**(既定名 `Ubuntu` のディストリビューション、および他ディストリビューション・他版は保証対象としない)。Windows ホスト側の事前導入は **WSL2 の有効化のみ**を前提とし、その他の開発ツールはすべて onboarding の手順内で導入する(Docker Desktop の事前導入は前提としない)

- onboarding の `wsl --install -d Ubuntu-26.04`(`docs/development/onboarding.md:23-79`)は「番号付きイメージ」の指定と整合する。**既定名 `Ubuntu` で入れると保証対象外**になる。
- 測定方法 — 要件書 `:918`: 受入プロファイルを「**試験対象として事前に一意化**」し、「**approved な** `onboarding.md` の手順を完走できることを **2 時点で 8 章の判定者が確認**する」。**draft 版での実行は測定方法を満たさない**。

#### A-2. Phase 4 完了時の合格項目(5 項目) — 要件書 `:921`

| # | 合格項目 | onboarding の対応箇所 |
| --- | --- | --- |
| 1 | ハーネスの pytest | `onboarding.md:290`(6 章 項目 3 `uv run pytest tests/`) |
| 2 | backend の pytest | `onboarding.md:328`(7-1) |
| 3 | frontend の Vitest | `onboarding.md:334`(7-1) |
| 4 | 開発 DB へ接続 | `onboarding.md:377-379`(8-2) |
| 5 | backend・frontend が起動して疎通確認 | `onboarding.md:396-416`(8-3) |

**明示的な対象外**(同 `:921`「実装期のため対象外」): 一致性・越境・E2E・同期故障系。**Playwright はリリース候補時のみ**(同 `:922`)。設計書 `:637` は合格項目を再列挙せず要件書を参照しており(同 `:631` の非複製宣言)、**要件書側が正**。

#### A-3. 証跡の必須記録(11 項目) — 要件書 `:923`

日時 / commit SHA / Windows 版 / WSL 版 / ディストリビューション版 / onboarding 版 / 主要ツールの版(python・uv・node・docker) / 実行コマンドと終了コード / 各合格項目の期待値と実測値 / 標準出力またはログ成果物への参照 / 判定者。

`gate_kind`・`tested_commit_sha`・`onboarding_blob_sha`・`result`・`attempt_seq`・`attempt_id` は**要件書に記載がなく**、設計書 `:641` が機械検証のために**上乗せ**したキー。

#### A-4. 判定者 — 要件書 `:1007`「判定者: システム管理者(=プロダクトオーナー)」

設計書 `:638` が追随し「**開発担当・Claude は操作補助と記録の起草のみ**」(1 名体制で別ロールを書いても独立性は成立しないため分離を装わない)。この役割分離は設計書側の規定で、要件書には記載なし。

### B. 機構の実態(実行手順)

#### B-1. 検証器の CLI — `scripts/verify_nfr021_evidence.py:2363-2405`

サブコマンドは無い。`phase4` 経路の実コマンド:

```bash
uv run python scripts/verify_nfr021_evidence.py \
  --root /home/ymdms/projects/pitchlog-worktrees/feature-phase4-6-acceptance \
  --gate-kind phase4 \
  --candidate-sha <E の完全な小文字 40 桁 commit OID> \
  --evidence-path docs/ops/nfr021-acceptance/<結果証跡のファイル名>.md
```

- `--gate-kind` / `--candidate-sha` / `--evidence-path` が **required**、`--root` は任意(既定 cwd)。
- **`phase4` では `--release-version` を渡してはならない**(渡すと入力エラーで fail-closed — `:2426-2427`、実メッセージ `tests/test_verify_nfr021_evidence.py:2028`「phase4 では --release-version を指定できない」)。
- `--evidence-path` は**リポジトリ相対**・**`docs/ops/nfr021-acceptance/` 直下と完全一致**(`:2559-2576`)、かつ**候補 SHA のツリーに収録済み**であること(`:3306-3310`)。作業ツリー上の未コミットファイルは対象外。
- 終了コード: **0 = 合格(stdout・stderr とも空)** / **1 = 違反または `GuardError`**(`:3380-3403`。裏取り `tests/test_verify_nfr021_evidence.py:2388-2400`)。
- **自己同一性検査**(`:2700-2737`): 実行中の `verify_nfr021_evidence.py` と `.claude/nfr021-invalidating-paths.json` の作業ツリー blob が候補 SHA のツリーと一致しないと `GuardError`。→ **候補 SHA を checkout した状態で実行する**。
- テストでの実引数がこの契約と一致(`tests/test_verify_nfr021_evidence.py:1855-1885`・`:1505-1523`)。

#### B-2. append-only 検査 — `scripts/check_nfr021_append_only.py`

- CI ジョブ `nfr021-append-only`: `.github/workflows/ci.yml:91-103`(`uv run python scripts/check_nfr021_append_only.py` を**引数なし**、`fetch-depth: 0`、paths filter なし)。
- 検査するのは **`develop` を base とする `pull_request` のみ**。それ以外はスキップして exit 0(`scripts/check_nfr021_append_only.py:506-531`)。
- ローカル手動実行: `uv run python scripts/check_nfr021_append_only.py --base origin/develop --head HEAD`(両方指定必須 — `:209-211`)。

#### B-3. 未閉塞の予約レコード(閉じる対象)

`docs/ops/nfr021-acceptance/2026-08-19T142916Z-phase4-phase4-seq001-reservation.md`:

| キー | 値 |
| --- | --- |
| `gate_key` | `"phase4"` |
| `attempt_seq` | `1`(引用符なし整数) |
| `attempt_id` | `"phase4-001-20260819T142916Z"` |
| `started_at` | `"2026-08-19T142916Z"` |
| `operator` | `"山田正輝"` |

`phase4` ゲートキーの未閉塞予約は**この 1 件のみ**。これを閉じる結果証跡 1 件を追加すれば検証器の合格条件 ⑦⑧⑨ を満たす(`scripts/verify_nfr021_evidence.py:3164-3230`)。結果証跡の `attempt_id` は**同一文字列**、`attempt_seq` は **1** でなければならない(受入 README `:106-110`、実装 `:1778-1794`)。

#### B-4. 結果証跡の作り方 — `docs/ops/nfr021-acceptance/evidence-phase4-template.md`

- **フェンス内の `:16-52` だけを複写**して新規ファイルにする(テンプレ自身の frontmatter・変更履歴表は複写しない。フェンスが 1 個であることの契約 = `tests/test_nfr021_evidence_templates.py:342-346`)。
- 埋める箇所は **プレースホルダ `<...>` が 26 個**(frontmatter 5・証跡表 11・合格項目表 10)。検出は `PLACEHOLDER_RE = r"<[^<>\n]+>"`(`scripts/verify_nfr021_evidence.py:104`)なので、**実測値に `<` `>` を 1 組でも含めると不合格**。
- `各合格項目の期待値と実測値` の値 `下表に記載` は**そのまま残す**(空欄検査の特例 — `:129`・`:1432-1436`)。
- 欄名は**文字列完全一致**が必要。特に `主要ツールの版（python / uv / node / docker）` は**全角括弧**(`:122`)。
- 合格項目表の `#` 列・`合格項目` 列は候補ツリーのテンプレートと**完全一致・行数一致**(`:1449-1476`)。
- ファイル名の正規形(受入 README `:43`・`:46-52`):

```
YYYY-MM-DDTHHMMSSZ-phase4-phase4-seq001-<tested_commit_sha の先頭 12 文字>.md
```

`docs/ops/nfr021-acceptance/` **直下**に置く(サブディレクトリ不可)。`seq<NNN>` はゼロ詰め 3 桁なので `seq001` 固定。先頭タイムスタンプは証跡自身の秒精度 UTC で、**予約と一致させる必要はない**(検証器のレコード間契約はゲートキー・`attempt_seq`・`release_version` の 3 点のみを比較 — `:1774-1794`)。索引 `docs/README.md` への掲載は**不要**(受入 README `:114-119`)。

#### B-5. onboarding 完走に人手が必須な箇所

`docs/development/onboarding.md` は frontmatter `status: approved`・**v1.0**(`:1-3`・`:14`)。現 HEAD での blob = `9f5beb1708ef6af5301a13def078464d24744b7b`。章立ては 0(WSL2 用意)〜8(開発 DB と起動疎通)で、受入で完走するのは 0〜8 章(受入 README `:191`)。

人手が必須(自動化・委任不可)な箇所は次の 7 系統・17 件:

- **Windows ホストの管理者/GUI 操作**: PowerShell(管理者)での WSL 操作一式(`:31-58`)/ WSL 初回起動の対話的ユーザー作成(`:44`)/ VERSION=1 時の `--set-version`(`:50-54`)
- **対話的ログイン・外部認証**: `gh auth login` の対話 4 問(`:118`)/ **Windows 側ブラウザでのデバイスコード入力**(`:118`)/ git author 設定(`:122-125`)/ Codex CLI 初回サインイン(`:193`)/ Claude Code の信頼選択 + ブラウザ認証(`:234`)/ Notion MCP の OAuth(`:257-269`)/ `/setup-dev` の対話(`:271`)
- **承認プロンプト・sudo**: apt / Docker 導入 / `usermod`(`:86-87`・`:154-170`)/ corepack の pnpm 初回取得 TTY 承認(`:218`・`:222`)/ docker グループ反映のシェル開き直し(`:174`)
- **Claude Code セッション内でしか再現しない確認**: 6 章 項目 1・2・5・6(`:280`・`:288-295`)。**項目 5 は 8 行を 1 行ずつ別々に実行**させる必要がある(`:299`・`:310`)
- **複数シェルの手動運用**: 8-3 はシェル 3 枚で前景起動 → `Ctrl-C`(`:392`・`:429`)
- **個人ファイルの編集**: `~/.codex/config.toml` に WSL 上の絶対パスを手書き(`:243-247`)
- **判定**: 実測値の妥当性判断と最終判定(受入 README `:166`・設計書 `:638`)

> 裁定済み(F-2): onboarding 6 章 **項目 6 は negative test** — Claude Code に `codex exec "test"` を実行させ、**codex_guard がブロックしラッパー経由の案内が出る**ことが合格条件(`:312`)。CLAUDE.md の「生の `codex exec` は codex_guard がブロック」と矛盾しない。

### C. win-setup ランナー選定

#### C-1. 既に決着している部分(approved 正本)

- **役割**: win-setup は**補助検査**であり本ゲートの代替にならない。ランナー未決の間は**人手の本ゲートのみが受入判定の根拠**(設計書 `:652`)
- **必須ゲートの中身**: Windows 11 x64 上の WSL2 を再現すること = 手動再現(要件書 `:1037`)
- **除外**: GitHub-hosted の Windows Server ランナーは**受入プロファイルの証跡にならない**(設計書 `:621`・要件書 `:1037`)
- **ジョブ内容と時期**: 「`onboarding.md` の手順を再現し NFR-021 を継続検証する」・定期実行・導入時期「Phase 4 以降」(設計書 `:621`)
- **決着の場所**: 4-6。**後送りは認めない**(設計書 `:810` — 認めるなら 10.1 側の改訂 = 版繰り上げ + 7.3 確定ゲートが要る)

#### C-2. 未決の部分 — 候補 4 案(`docs/features/req-v1-9-nfr021-wsl2/research.md:67`)

| 案 | 内容 |
| --- | --- |
| (a) | `ubuntu-latest` を必須の週次検証にし、WSL 固有部分は対象外と明記 |
| (b) | `windows-2025` 固定で WSL2 ジョブを置くが**非必須(情報収集)扱い**・冒頭で `wsl -l -v` をアサート |
| (c) | (a) + (b) の併用 |
| (d) | WSL 固有部分は self-hosted runner または手動チェックリストへ寄せる |

同行に「**ハーネス設計者の回答が未着**」と明記。**各案に却下理由は付いていない**(= 未評価のまま申し送り)。**コスト(金額・実行時間)の記載なし**。

判断材料(同 `research.md:43-63`):

| 論点 | 結論 |
| --- | --- |
| `windows-latest` で WSL2 | **使える**(Windows Server 2025・イメージに `WSLv2: 2.7.11.0`)。「使えない」は誤り(`:45`・`:17`) |
| 公式サポート | 入れ子仮想化は「**experimental / at your own risk**」・保証なし(`:46`) |
| `windows-2022` | イメージ一覧は **WSLv1 のみ**。使うなら `windows-2025` 固定 + アサート(`:48`) |
| WSL1 での代替 | **不十分**(managed VM・Linux カーネル・syscall 互換・systemd が無い)(`:49`) |
| `Vampire/setup-wsl@v7` | 既定 WSL2 だが**第三者 Action**で GitHub の保証ではない(`:50`) |
| larger runners | 入れ子仮想化の正式サポートを示す公式記載は**見つからず = 不明**(`:51`) |
| self-hosted | 実機なら要件を満たせる。VM なら親側で仮想化拡張の公開が必要(`:52`) |
| `ubuntu-latest` | 非 WSL 固有の手順には妥当だが「WSL2 上で完結」の証明にならない(`:53`) |

`ubuntu-latest` 単独で**検証対象外になるもの**(同 `:55-61`): `/mnt/c` の DrvFS/NTFS 権限変換 / Windows 側コマンド呼出し・`WSLENV`・**Windows 側 PATH の混入**(※「本プロジェクトは実際にこれを踏んでいる — pyenv-win のシムが WSL の PATH に紛れて `python` が壊れた」`:59`)/ `wsl.conf`・systemd ライフサイクル / `/mnt/c` と Linux FS の性能差。

**採用時点で再確認すべき事項**(同 `:69` — 設計書 9.2「Codex 出力を鵜呑みにしない」): Windows2025-Readme の WSLv2 記載 / GitHub-hosted runners ドキュメントの「experimental / at your own risk」の原文。

#### C-3. 4-6 が「実装」まで含むかは不明

設計書 `:810` の 4-6 定義は「**ランナー選定**」とだけ書き、10.1 の表(`:621`)は導入時期を「Phase 4 以降」と書く。**`ci.yml` へのジョブ実装まで 4-6 に含むと明記した記述は無い**(= 不明)。→ /plan で範囲を明示的に決める必要がある(G-1)。

#### C-4. 要件書 10 章の未決事項行

要件書 `:1037` — 項目「NFR-021 の継続検証基盤(WSL2 再現を CI で自動化するか手動運用にするか)」/ 決定者「山田さん」/ **期限「Phase 4 着手時」**(v1.9 = 2026-08-11 に登録)。

- 表の列は 項目・暫定方針・決定者・期限の 4 列で、**「解決条件」欄は存在しない**(`:1034`)。
- **要件書の期限「Phase 4 着手時」と、設計書の実施スロット(4-6 = Phase 4 末尾)には時点のずれがある**。要件書側に 4-6 を禁じる文言は無く、決定者は PO。是非の規定は要件書に無い。
- 4-5 時点の調査は「決着記録が要件書に反映されておらず、決着済みか否かは要件書からは**判定できない**」とし、4-6 へ申し送っている(`docs/features/nfr021-evidence-verifier/research.md:90`・`:450`)。**この行を閉じる責務が 4-6 にあると明記した正本は無い**(= 不明)。

### D. 境界 — 4-6 でやってはいけないこと

| # | 禁止事項 | 原文の要旨 | 典拠 |
| --- | --- | --- | --- |
| 1 | **`/release` 手順 0 の置き換え** | 「`/release` 手順 0 の置き換えは含まない(v1.7 — 確定ゲート 2 周目 P0)」。4-6 で置換すると、検査が不合格だった場合に**「Phase 4 未完了のまま `/release` が開いた」状態が develop に残る** | 設計書 `:810`・`:811`・`:654` |
| 2 | **13 章の現況追随** | 「13 章の現況追随は `P4-後` で行う(2 周目 P1)。**4-6 はマージ済みで事後変更できない**ため、4-6 で書くと『不合格時に虚偽の完了記録が develop に残る』か『事後追加できない』かのどちらかになる」 | 設計書 `:835` |
| 3 | **完了証跡の記録** | 「完了証跡は 13 章の現況追随として記録する(3 周目 P1)…`docs/ops/nfr021-acceptance/` へは置かない」 | 設計書 `:811` |
| 4 | **マージだけで完了を宣言すること** | 「Phase 4 の完了は『4-6 のマージ**かつ**マージ後検査の合格』をもって成立し、その事実は `P4-後` で記録する。**マージだけで完了を確定させない**」 | 設計書 `:818` |

**再提案してはいけないもの**(v1.9 で「増やさない」と確定 — 設計書 `:829-832`):

1. マージ後検査の期待値の新しいキー・媒体(`phase4_base_sha` のキー化・`evidence_path` の永続化など)
2. **論理スロットと Notion タスクの対応の機械化**(計画書 frontmatter のスロットキー・DoD の機械可読マーカー・`/task-start` の着手制限)— **9〜15 周目で 7 案を起案し、すべて次の周に否決**。どれも「起票する行為そのものは誰も検査できない」という同じ限界に突き当たる
3. 再試行タスクの初期化項目のうち、最小 3 項目を超える部分とその機械的な検査

その他の「戻してはいけない」決定: `P4-後` まで覆う完了条件を設計する案(循環 — `:815`)/ 元タスクを `ブロック中` にする案(撤回済み — `:818`)/ 手順 0 の中断条件を時点ベースで書く案(`:43`・`:633`)/ onboarding の approved 化を 4-6 に戻す案(循環 — `:51`・`:841`)/ 合格条件 ⑩・append-only 検査を全証跡へ広げる案(恒久閉塞 — `:644`・`:651`)。

**4-6 に義務として残る接続点**:

- **検査結果は合否どちらでも 4-6 の PR コメントへ記録**。記録項目 4 つ = `M` の完全 OID / 検査の実施日 / 合否 / 確認者(設計書 `:826`)
- **`/task-done` で、合格なら `P4-後` を、不合格なら「Phase 4-6 再試行」タスクを起票**して 4-6 のタスクへ相互リンクするまでが完了条件(設計書 `:834`)
- 排他区間(`main`・`develop` を進める**あらゆる操作**の停止。UI/API マージも含む)の**開始と解除を PR へコメント記録**(設計書 `:640`)

### E. 実行順序の制約(本タスク最大の設計上の縛り)

失効対象パスの機械可読な正本 `.claude/nfr021-invalidating-paths.json` は **`default: "invalidating"`** であり、allowlist は **`/docs/ops/nfr021-acceptance/**`・`/docs/worklog/**`・`/docs/features/**` の 3 つだけ**。したがって:

- `docs/development/dev-harness-design-2026-08-07.md`(設計書)
- `docs/requirements/requirements-pitchlog-2026-07-22.md`(要件書)
- `.github/workflows/**`

は**いずれも失効対象**である(前 2 者は明示列挙ではなく `default` により失効側へ落ちる)。

失効判定は **`T` → `E` の各コミットの変更パスの和集合**に対して行う(2 点差分を使わない — 設計書 `:649`)。`E` の後に別コミットを積むことはできない(マージは `--match-head-commit <E>` で `E` を head として行うため — 設計書 `:648`)。

**帰結**: win-setup 選定の記録(設計書 10.1 の追随・要件書 10 章の決着記録・`ci.yml` へのジョブ追加のいずれも)は、**`T` を採るより前に確定していなければならない**。PR 内の順序は次に強制される。

```
[1] win-setup ランナー選定を確定し、正本へ追随(設計書 / 要件書 / 必要なら ci.yml)
        ↓
[2] T = この時点のブランチ HEAD ← ここで tested_commit_sha を採る
        ↓
[3] 受入の実施(T のツリーを新規 WSL2 環境で完走) ※人間 = PO
        ↓
[4] E = 結果証跡コミット(docs/ops/nfr021-acceptance/ = allowlist なので T→E は失効しない)
        ↓
[5] candidate_sha = E で検証器を直接実行 → 判定者の合格判定
        ↓
[6] 排他区間を開始 → gh pr merge --merge --match-head-commit <E>
        ↓
[7] マージ後検査(M の第1親 = phase4_base_sha / 第2親 = E / ツリー = E のツリー)→ PR へ記録 → 排他解除
```

`T` → `E` の間に許されるのは allowlist 配下(`docs/ops/nfr021-acceptance/`・`docs/worklog/`・`docs/features/`)の変更のみ。**worklog と計画書・調査メモの更新はこの区間でも安全**。

### F. 裁定(エージェント報告の突合と原典確認)

#### F-1. 受入は `develop` ではなく **feature ブランチのツリー**に対して実施する

- onboarding 2 章は develop への切り替えを指示する(`onboarding.md:200`)。その理由は注記に明示されており「**`main` には `mise.toml`・`backend/`・`frontend/`・`docker-compose.yml` がまだ無い**ため、切り替えずに進むと `mise install` で止まり合格項目へ到達できない」(`onboarding.md:206`)= **`main` を避けることが目的**であって、develop でなければならない理由は書かれていない。
- 受入 README `:191` は「**予約を含む候補ツリー**で onboarding の手順を完走し」と書く。`T` は候補ツリーであり、E 節のとおり本タスクでは feature ブランチ上のコミットになる。
- 予約レコードは既に `develop` へ統合済み(現 HEAD に存在)なので、feature ブランチのツリーも「予約を含む」条件を満たす。
- **裁定**: 受入時は `feature/phase4-6-acceptance`(= `T`)へ切り替えて完走する。onboarding の記述からの逸脱ではなく、注記が排除しているのは `main` のみ。**ただし approved な手順の逐語からずれる点は計画書に明記し、判定者の了解を取る**(G-2)。

#### F-2. onboarding 6 章 項目 6 は negative test

`onboarding.md:312` の合格条件は「**codex_guard がブロックし、`codex_run.py` ラッパー経由の案内が出る**こと」。CLAUDE.md の「生の `codex exec` は codex_guard がブロック」と整合する。矛盾なし。

#### F-3. 「win-setup」は要件書に存在しない名称

要件書全文にヒット 0。設計書 10.1 の CI ジョブ名(`:621`)。要件書側の対応物は 10 章未決事項の「NFR-021 の継続検証基盤」(`:1037`)。**正本間で語彙が一致していない**ため、計画書では両方を名指しする。

### G. 既知のリスク(台帳の未対応項目 — 計画に織り込む)

| ID | 内容 | 本タスクへの影響 | 典拠 |
| --- | --- | --- | --- |
| **H-72** | `check_plan_docs_sync.py` の突合対象が `/pr` スキルの規定より広く、**正本でない受入証跡(予約・結果証跡)が「差分にあるのに未宣言」として検出され `/pr` が中断する**。「今後の受入証跡(**4-6 の結果証跡**・将来の release 証跡・失敗閉塞 PR)でも毎回同じ別枠宣言が必要になる」 | **確実に踏む**。計画書 3 節に別枠「正本体系外だが同一 PR で更新するもの」を用意しておく | 台帳 `:970-979` |
| **H-69 (c)** | 「**NFR-021 の受入(Phase 4-6)は backend / frontend の起動疎通を含む**ため、**実施主体を設計書 13 章の 4-6 の記述に明示する**」。背景 = sandbox でソケット bind ができず `fastapi dev` の起動確認を Codex へ委任できない(実測) | 合格項目 5 は**人間の手元でしか実施できない**。委任計画を立てない | 台帳 `:940-949` |
| **H-58 / H-76** | 非文書ファイルを含む反映周コミット・レビュー是正コミットが混ざると `feature_status.py` が「不明」へ縮退(実測・再発) | 現在地表示が壊れても作業を止めない。ステップ記法を厳密に守る | 台帳 `:820-829`・`:509` |
| **H-68** | 実機のない段階で細部まで確定させようとすると確定ゲートが閉じた輪に入る(3 件。1 例目が設計書 v1.7 の 12〜15 周目) | win-setup 選定で「実装時に決めれば足りる」ものを机上確定しようとしない | 台帳 `:929-938` |
| **H-79** | 同種の欠陥を全経路へ適用せずに是正する(再発 4 件) | 是正は全経路へ一括適用する | 台帳 `:543` |
| **候補 (12)** | 13 章の順序規定からの逸脱(4-4 が予約監査 PR より先にマージされた)。「**順序を強制する機構は存在しない**」 | E 節の順序は機構で守られない。人間が守る | 台帳 `:1119-1123` |

改善台帳 `docs/improvements-from-baseball-scoring.md` には Phase 4-6・NFR-021 受入に関する項目は**無い**(NFR-021 への言及は I-6 内の 1 行のみ — `:66`)。

### H. Web 調査結果(win-setup ランナー選定の判断材料)

実施日 2026-08-25。`/research`(Codex 委任 — read-only + live search + terra high、`codex_run.py` ラッパー経由)。**Codex の出力は鵜呑みにせず、下表の 5 点は URL を自分で再取得して裏取りした**(設計書 9.2)。

#### H-1. 自分で再確認した事実(裏取り済み)

| # | 事実 | 典拠 URL | 検証 |
| --- | --- | --- | --- |
| 1 | 入れ子仮想化は**公式サポート外**。逐語: 「While nested virtualization is technically possible while using runners, it is not officially supported. **Any use of nested VMs is experimental and done at your own risk**, we offer no guarantees regarding stability, performance, or compatibility.」 | https://docs.github.com/en/actions/concepts/runners/github-hosted-runners | **✓ 自分で確認**(2026-08-25)。文言は現行ページに残存、緩和の形跡なし |
| 2 | `windows-2025` イメージの WSL 表記は逐語で `Windows Subsystem for Linux (WSLv1): Enabled` と `Windows Subsystem for Linux (Default, WSLv2): 2.7.11.0`。イメージ版 `20260818.232.1` / OS = Windows Server 2025 | https://raw.githubusercontent.com/actions/runner-images/main/images/windows/Windows2025-Readme.md | **✓ 自分で確認**。`req-v1-9-nfr021-wsl2/research.md:45` の記載は現在も有効 |
| 3 | **`Vampire/setup-wsl` は `Ubuntu-26.04` に非対応。** 受理する Ubuntu は `Ubuntu-24.04` / `22.04` / `20.04` / `18.04` / `16.04` のみ。既定ディストリは `Debian-13`、既定 `wsl-version` は `2` | https://raw.githubusercontent.com/Vampire/setup-wsl/master/action.yml | **✓ 自分で確認**。**新規の重要事実**(前回調査 `:50` には無い) |
| 4 | schedule の 60 日非アクティブ無効化は**public リポジトリ限定**。逐語: 「**In a public repository**, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days」。あわせて「Scheduled workflows **will only run on the default branch**」「shortest interval … once every 5 minutes」「delayed during periods of high loads … start of every hour」 | https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows | **✓ 自分で確認** |
| 5 | GitHub Free + private の含有枠は月 **2,000 分** / artifact 500 MB / cache 10 GB/リポジトリ。**Windows の数値倍率(2× 等)はこのページに記載が無く**、代わりに Windows 2-core (x64) `$0.010/分`(Linux は `$0.006/分`)の実単価が示される | https://docs.github.com/en/billing/concepts/product-billing/github-actions | **✓ 自分で確認**。「Windows は厳密に 2×」は**現行公式では確認できない**(単価比では約 1.67 倍) |

#### H-2. 本リポジトリ固有の決定的制約(本調査で新たに判明)

**scheduled workflow は default branch でしか走らない**(H-1 の #4)。本リポジトリの実測値:

- **default branch = `main`**、visibility = `PRIVATE`(`gh repo view` 実行結果、2026-08-25)
- **`origin/main` のトップレベルに `backend/`・`frontend/`・`contracts/`・`docker-compose.yml`・`mise.toml`・`package.json` が存在しない**(`git ls-tree --name-only origin/main` 実測。あるのは `.claude`・`.codex`・`.github`・`.gitignore`・`.python-version`・`AGENTS.md`・`CLAUDE.md`・`README.md`・`docs`・`pyproject.toml`・`scripts`・`tests`・`uv.lock`)

この 2 つから次が帰結する。

1. **win-setup のワークフロー定義は `main` へ到達しないと schedule で発火しない。** `main` が進むのはリリース時だけであり、**`/release` は `P4-後` まで無条件中断されている**(設計書 `:654`)。したがって **win-setup の定期実行は、どの案を採っても初回リリースまで実際には起動しない**。
2. **発火しても、既定の checkout 対象(`main` のツリー)には検証対象が無い。** ワークフロー側で明示的に `develop` を checkout する必要がある。
3. **`workflow_dispatch` を併記すれば任意ブランチから手動実行できる**ため、実装の動作確認はこの経路で可能。

> この制約は設計書 10.1 の win-setup 行にも `req-v1-9-nfr021-wsl2/research.md` にも記載が無い。**4-6 の選定判断に直接効く**ため、計画書で扱いを決める(G-1)。

#### H-3. 4 案の評価(Codex の評価 + 上記制約の反映)

| 案 | 成立性・検証できること / できないこと | コスト | 運用負荷 |
| --- | --- | --- | --- |
| (a) `ubuntu-latest` を必須 | 成立。アプリ・pytest/Vitest・PostgreSQL・HTTP 疎通は検証できる。**Windows / WSL 固有は検証不可** | 最低 | 低 |
| (b) `windows-2025` で WSL2・非必須 | **条件付き**。Windows Server 2025 上の WSL2 は動く見込みが高い(イメージが WSLv2 2.7.11.0 を Default と明記)が、**GitHub の保証は無い**。**Windows 11 の再現ではない**。**`Ubuntu-26.04` を hosted runner 上でサポート済みとして導入する経路が未確認**(`setup-wsl` は非対応 / native `wsl --install -d Ubuntu-26.04` の runner 上での成否は**不明**) | 週 1 回 30〜60 分で月 131〜261 実行分。2× を保守的に仮定しても 261〜522 分で **2,000 分枠内** | 中 |
| (c) (a) + (b) の併用 | 必須品質は Linux で安定確保しつつ、Windows/WSL の破綻兆候も拾える。**Windows 11 固有の受入は依然として対象外** | Free 枠内の見込み | 中 |
| (d) self-hosted / 手動チェックリスト | 実機 self-hosted なら受入プロファイルに最も近い。ただし **private リポジトリでも fork PR 経由で self-hosted 環境・secrets・`GITHUB_TOKEN` が侵害され得る**と GitHub が警告(https://docs.github.com/en/actions/reference/security/secure-use)。専用の低権限 runner・runner group 限定・secret 非付与・ジョブ後の破棄が必要。手動のみなら継続的な早期検知は無い | hosted 分は不要。機材/VM 費 | 手動のみ低 / self-hosted 高 |

**Codex の推奨は (c)**。理由: `ubuntu-latest` を required にして通常の品質ゲートを安定確保し、`windows-2025` を non-required の情報収集として置く。冒頭で `wsl --version` / `wsl -l -v` をログ化し、対象ディストリが `VERSION 2` でなければ明確に失敗させる。「Windows Server 2025 + experimental WSL2 の情報収集であり Windows 11 実機の正式受入を置換しない」とワークフローと運用文書へ明記する。

**本調査者の評価(Codex への差分)**:

- (a) の「`ubuntu-latest` を**必須の週次検証**にする」部分は、**既存 CI と重複する**。`.github/workflows/ci.yml` は既に PR / push で backend・frontend・harness ジョブを回しており(`ci.yml:91-103` 他)、週次で同じ Linux 検査を足す増分価値は小さい。**(a) は「win-setup の代替」としては要件書 `:1037` の「WSL2 再現」に応えていない**。
- (b)(c) の Windows ジョブは、**H-2 により初回リリースまで schedule では発火しない**。`workflow_dispatch` でしか動かない期間が続く。
- **`Ubuntu-26.04` を WSL へ入れる手段が未確立**である以上、(b) を実装しても**受入プロファイルと同じディストリでは検証できない**。別ディストリでの検証は「onboarding の手順を再現する」という win-setup の目的(設計書 `:621`)を部分的にしか満たさない。
- → **実装を今確定させる根拠が弱い。** これは台帳 H-68 が言う「**実機のない段階で細部まで確定させようとすると確定ゲートが閉じた輪に入る**」の典型で、同項の対応案 (c)「(A) 方式が分岐する / (B) 実装時に決めれば足りる の分類」に照らすと **(B) 側**にあたる。

## 未解決・申し送り

計画書(/plan)で決めるべきこと。**いずれも判定者(PO)の決定が要る**。

1. **G-1: win-setup ランナーの選定 — 【決定済み 2026-08-25・PO】**
   - **① 採用案 = (d)**「WSL 固有部分は self-hosted runner または手動チェックリストへ寄せる」。**GitHub-hosted ランナーは採用しない。** 根拠は H 節 — GitHub-hosted の Windows ランナーは Windows Server 2025 であって受入プロファイル(Windows 11 x64)の再現にならず(H-1 #2)、入れ子仮想化は公式サポート外(同 #1)、`Ubuntu-26.04` を WSL へ導入する確立した手段が無い(同 #3)、かつ定期実行は初回リリースまで発火しない(H-2)。
   - **② 4-6 の範囲 = 選定の記録のみ。`ci.yml` への実装は含めない。** 導入時期は 10.1 の表が定める「Phase 4 以降」に従う。
   - **これは「後送り」ではない**(設計書 `:810` が禁じるのは**選定**の後送り)。選定は本タスクで確定させ、**実装**のみを 10.1 の既定どおり Phase 4 以降に置く。計画書でこの区別を明示する。
   - **③ 下位方式 = 手動チェックリストに一本化【決定済み 2026-08-25・PO】**。「**GitHub-hosted は採用せず、WSL 固有の継続検証は手動チェックリストで行う**」と確定記録する。**self-hosted runner は将来の選択肢として台帳へ送る**(採否を今決める根拠が無く、機材・fork PR リスクの隔離・低権限 runner の運用設計が別途必要なため — H-3 (d) 欄)。これにより **未決を一切残さず**、要件書 `:1037` の暫定方針「手動再現」とも一致する。
2. **G-2: 受入を feature ブランチのツリーで実施することの了解**(F-1)。approved な onboarding の逐語(develop への切り替え指示)からずれるため、判定者の明示的な了解を計画書に記録する。
3. **G-3: 要件書 10 章の未決事項行の決着記録を本 PR で書くか。** 4-6 の責務と明記した正本は無い(C-4)。書く場合、要件書は失効対象パスなので **E 節の `[1]` = `T` より前**に置く必要がある。
4. **G-4: 要件書の期限「Phase 4 着手時」を既に過ぎていることの扱い**(C-4)。是非の規定は要件書に無く、決定者は PO。台帳へ観測として起こすかを判断する。
5. **G-5: 受入の実施日程。** onboarding 完走は新規 WSL ディストロ作成から始まり、人手必須が 17 件(B-5)。排他区間(`main`・`develop` を進めるあらゆる操作の停止)を伴うため、**まとまった時間を確保して一気に行う**必要がある。
6. **H-69 (c) の対応(設計書 13 章 4-6 への実施主体の明記)を本 PR で行うか**。行うなら設計書は失効対象なので `T` より前(E 節 `[1]`)。
7. **G-6: (d) の下位二択 — 【決定済み 2026-08-25・PO】手動チェックリストに一本化**(G-1 ③ に記載)。**残作業**: ① 手動チェックリストの実体を誰がどこに置くかを計画書で決める(既存の `docs/ops/` 配下か、`onboarding.md` の再実行手順で足りるか)② **self-hosted runner を将来の選択肢として台帳へ送る**(観測または follow-up として起票)。
   - 派生する確認: **選定が (d) = GitHub-hosted 不採用となったことで、設計書 10.1 の CI 表から `win-setup` 行そのものを削除するのか、「GitHub-hosted は採用しない」と書き換えて残すのか**を決める必要がある。**行を削除すると `win-setup` という語を参照している他の記述(設計書 `:652`「`win-setup` は補助検査であり本ゲートの代替にならない」など)が宙に浮く**ため、**書き換えて残す方が安全**(H-79「同種の欠陥を全経路へ適用せずに是正する」の再発を避ける)。
8. **G-7: 正本改訂のゲート区分**(設計書 7.6-3)。win-setup の選定記録は 10.1 の CI 表の当該行を「ランナーは未決 — Phase 4 で選定」から**「GitHub-hosted は採用しない」へ書き換える**ものであり、**行の性質そのものが変わる**。これが「実装追随の節更新(PR レビューで可)」なのか「版繰り上げ(敵対レビュー + 人間承認 = `/finalize-doc`)」なのかを計画書 3 節で判定する必要がある。**後者なら 4-6 の中に確定ゲートが 1 本入り、E 節の `[1]` が長くなる**(所要時間の見積りに直結)。同じ判定が要件書 10 章の未決事項行(G-3)にも要る。
