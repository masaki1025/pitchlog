# -*- coding: utf-8 -*-
"""TSK-235 の実装ステップ 55 件の単一定義。

`plan.md` の §4 実装ステップ表と §5-1 DoD 表は、本ファイルから生成する。
2 つの表を人手で追随させたことが 3 周目 `P1-6`・4 周目 `P2` の原因だったため。

使い方:
    python3 steps.py steps   # §4 のステップ表本体
    python3 steps.py dod     # §5-1 の DoD 表本体
    python3 steps.py check   # 自己整合の検査

**本ファイルは計画段階の資産であり製品コードではない。**
`ruff` / `ty` の検査対象(`scripts/` と `tests/`・`backend/src`)には含まれない。
**plan.md との一致は `tests/test_plan_generation.py`(ステップ 50)が検査する。**
"""

EXPECTED_TOTAL = 56

#: 正例 B を要求しないステップの**閉じた集合**。
#: 機構を作らない宣言・導出・負例集・正例 A のステップだけがここに入る。
#: 5 周目 `P1`: 自己申告のフラグだけでは `pb` を両方 false へ倒せば通ってしまうため、
#: 集合そのものを宣言して exact-set で突き合わせる。
PB_FALSE = frozenset([2, 3, 4, 6, 14, 19, 21, 22, 23, 32])

GROUPS = []  # [(group_id, title, note, first_id, last_id)]
S = []


def grp(gid, title, note):
    """群を開始する。以後の st() は本群に属する。"""
    GROUPS.append([gid, title, note, len(S) + 1, None])


def st(title, crit, art, cmd, pb):
    """ステップを 1 件追加する。番号は呼び出し順で自動採番する。"""
    if not GROUPS:
        raise RuntimeError("grp() より前に st() が呼ばれた")
    S.append(dict(id=len(S) + 1, g=GROUPS[-1][0], t=title, c=crit, a=art, m=cmd, pb=pb))
    GROUPS[-1][4] = len(S)


grp(1, '第 1 群 — 語彙・型・前提照合(1〜5)',
    '**`P1-5`(3 周目)の停止ゲートは「着手前の前提照合」なので先頭群に置く。**\n**`P1-5`(4 周目)の是正で、旧ステップ 3 を台帳・評価レコード・ゲートの 3 つへ分けた。**')
st('**配置と DSL 記述形式の確定**(design.md §1)。D-1 v0.2 の **3 類**と `NumericValue`(3 形 + nullable)/ `DisplayAtom`(不透明型)/ 供給源 3 経路を閉じた語彙の schema に。**(β) formatter の言語・配置を確定**。**トリガー 1・2・13 を評価**',
   '`[機械]` 語彙 schema の **exact-set**(3 類・型 3 形・供給源 3 経路)/ **単位パラメータが存在しない** / 差分が **パス allowlist** に収まる **◎ 妥当な DSL 入力が実際に受理される**(**正例 B** — すべてを拒否する schema を排除する。**6 周目 `P1` の是正**: ステップ 7 と同じ理由で、語彙 schema も**入力を受理・拒否する機構**である)/ `[手動]` **トリガー 1・2・13 の該当性判定**(判定者: 山田正輝)。**発火なら design.md §12-2 で停止**',
   '`backend/domain/vocabulary.schema.json`', '`uv run pytest tests/domain/test_vocabulary_schema.py`', True)
st('**機械条件の判定方法の型**(design.md §2)。既存 5 型 + 本タスクの **7 型**を資産化し、以降の全ステップの `[機械]` 条件をこの型に紐づける',
   '`[機械]` **行番号参照 0 件** / 各型に**正例と負例が 1 つ以上**ある / 型に紐づかない `[機械]` 条件が 0 件',
   '`backend/domain/machine-conditions.json`', '`uv run pytest tests/domain/test_machine_conditions.py`', False)
st('**依拠条項台帳**(トリガー 16)。**全 {N} ステップの「依拠する正本の条項 ID」**と、**`requiresPositiveB`** を資産化する',
   '`[機械]` **文言存在**(依拠条項の逐語が正本に実在。**1 件でも不在なら fail**)/ **行番号参照 0 件** / **{N} ステップすべてに行がある**(**母集合計測**)/ **`requiresPositiveB` が全行にある** / **本台帳自身も依拠条項を宣言している**(自己適用 — design.md §16-12)',
   '`backend/domain/step-authorities.json`', '`uv run pytest tests/domain/test_step_authorities.py`', False)
st('**見直しトリガーの評価レコードの形式と定義**(design.md §12-1)。**16 件それぞれに `evaluationMethod`・判定者・証拠資産の置き場・発火値**を宣言する。**評価結果は各評価ステップが追記する** — **本ステップでは評価しない**(**5 周目 `P1` の是正**: 旧版は本ステップで 16 件すべての評価済みと 証拠資産の実在を要求していたが、トリガー 5・8・12・15 の証拠はステップ 27 以降・最遅 48 で作られるため **本ステップのコミット時点では合格不能**だった)',
   '`[機械]` **母集合計測**(16 件すべてに**枠**がある)/ **`evaluationMethod` が design.md §2 の 12 型のいずれかを指す**(**集合差**)/ **判定者が PO 以外なら fail**(**文言存在**)/ **証拠資産の置き場が宣言されている**(**この時点での実在は要求しない**)/ **評価するステップ番号が実在するステップを指す**(**集合差** — 番号の陳腐化を機械検出する)/ **評価結果の欄が空であることを許す**',
   '`backend/domain/review-triggers.json`', '`uv run pytest tests/domain/test_review_triggers.py`', False)
st('**停止ゲート**(design.md §12-3)。**発火レコードがあれば後続ステップの実行を拒否する**。**未評価は停止対象にしない** — **評価期限(当該トリガーの評価ステップ)を過ぎた未評価のみを対象とする**',
   '`[機械]` **発火レコードが 1 件でもあれば後続が exit 2 で拒否される**(**exit コード分離**)/ **評価期限前の未評価では拒否しない**(**5 周目 `P1` の是正**)/ **期限を過ぎた未評価は拒否する**(fail-closed)/ **◎ 発火レコードが 0 件なら後続が実際に通る**(**正例 B** — 常に exit 2 を返す実装を排除する)',
   '`backend/src/pitchlog/domaincheck/stopgate.py`', '`uv run pytest tests/domain/test_stopgate.py`', True)
grp(2, '第 2 群 — 封印前の独立実測(6〜12)',
    '**`P0-2` の是正**: **封印は「検査器の出力の凍結」**(design.md §3-2-d)なので、**凍結する出力を先に作る。**\n**監査専用の収集器**であり、**この群では宣言との差で fail させない**(判定は第 9 群)。')
st('**`D`(履歴文脈の検査上限)の導出と値域 schema**(design.md §5)。**FR-006 単独**で長さ 4 を導き、**`D` の具体値**と**深さ・構成・シナリオ長の全 case 集合**を資産へ固定。**トリガー 9 を評価**',
   '`[機械]` 導出が **case → 長さ → 最大値の式**として機械可読(**独立導出**)/ 典拠の**文言存在**(`FR-006 補足` の逐語)/ 主要フラグ 9 項目と表示 primitive パラメータに値域 / **`D+1` に出力同値を課していない** `[手動]` 導出の意味レビュー(判定者: 山田正輝)',
   '`backend/domain/history-depth.json`', '`uv run pytest tests/domain/test_history_depth.py`', False)
st('**マニフェスト schema の凍結**(design.md §6)。**2 層 exact-set**(per-calculation **10 宣言** / トップレベル **3 宣言** = `propertyCatalog` + コンテナ + 表示対応宣言)+ **composite target**(`kind` / `components[]` / `invocation`)+ 空を許さない 5 フィールド。**トリガー 7・10・11 を評価**',
   '`[機械]` **2 層それぞれの exact-set**(**母集合計測**で 10 と 3 を固定)/ `kind` と段数の整合 / `minItems` / **provenance が条項 ID 形式**で逐語が実在(**文言存在**)/ 否定葉の存在 / **検査器より前のコミットである**(**`history_precedes`**)/ **対象 ID ごとの `vectors[]` 帰属数が `== 1`** かつ **未知契約が `== 0`** / **対象母集合が非空** / **欠落・重複・未知の 3 負例が個別に fail** / **資産内の重複を拒否する 5 種** / **◎ 正しいマニフェストが実際に受理される**(**正例 B** — すべてを拒否する schema を排除する。**5 周目 `P1` の是正**)',
   '`backend/domain/manifest.schema.json`', '`uv run pytest tests/domain/test_manifest_schema.py`', True)
st('**検査器の schema/CLI**。独立収集器・canonical JSON・厳密キー集合・exact-set の両方向・**exit 0/1/2**・`--root`',
   '`[機械]` **exit コード分離**で 1 / 2 を直接 assert / **全葉変異**で escape 0 かつ **`assert attempts == 期待件数`** / **◎ 適合する入力で exit 0 を返す**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/cli.py`', '`uv run pytest tests/domain/test_checker_cli.py`', True)
st('**封印の機構と履歴規律**(design.md §4)。blob digest・reseal 専用フラグ(相互排他・既定 off・書き込み前に自己検査)・**`os.environ["CI"]` ガード**・**版管理ツール不在で traceback しない**。**固定 SHA は `BOOT-SEAL-BASE`**',
   '`[機械]` `--reseal*` が CI 環境変数下で拒否される / 版管理ツールを PATH から外して traceback しない / 通常検証が黙って再封印しない / **比較元が merge-base でない**静的検査 / **固定 SHA を書き換える差分が無条件に fail**(`BOOT-SEAL-IMMUTABLE`)/ **◎ 正当な reseal が実際に成功し封印が更新される**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/seal.py`', '`uv run pytest tests/domain/test_seal.py`', True)
st('**実在入口の独立収集器 — frontend**(design.md §10-1 の前半)。Vite の全 input・Web Worker・Service Worker・別 HTML・静的配信配下の入口を**全列挙するだけ**の監査専用収集器',
   '`[機械]` **母集合計測**(`assert attempts == 期待件数`)/ **解析不能例で exit 2** / **production build と import graph を直接読む**(静的リストを持たない — **独立導出**)/ **この段階では `entrypoints[]` と突合しない**静的検査 / **◎ 既知の実在入口(`courseInputView.ts` 経由の 4 ホップ)が実際に列挙される**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/collect_entrypoints_fe.py`', '`uv run pytest tests/domain/test_collect_fe.py` + `pnpm test -- --run`', True)
st('**実在入口の独立収集器 — backend**(design.md §10-2 の前半)。Python の import グラフ + `importlib` / `getattr` / entry point 経由の読み込み箇所を**全列挙するだけ**',
   '`[機械]` 同上 3 点 / 動的読み込み箇所が「解析不能」として列挙される / **◎ 既知の実在入口が実際に列挙される**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/collect_entrypoints_be.py`', '`uv run pytest tests/domain/test_collect_be.py`', True)
st('**表示経路の静的解析器**(design.md §10-3 の前半)。**製品の表示呼出箇所**を静的解析で**全列挙するだけ**。**対象集合は宣言モデル schema の閉包から機械導出**。**トリガー 13 を評価**',
   '`[機械]` **対象集合が schema 閉包から導出される**(「等」の列挙をハードコードしていない — **独立導出**)/ **母集合計測** / **解析不能例で exit 2** / **◎ 既知の表示呼出箇所が実際に列挙される**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/collect_display_paths.py`', '`uv run pytest tests/domain/test_collect_display.py`', True)
grp(3, '第 3 群 — 検査集合の分離と封印(13〜15)',
    '**`P1-2`(4 周目)の是正**: **封印集合の総数を「約 136」ではなく確定値 136 として assert する。**\n**内訳は D-11 由来 133(対象 13 × 宣言 10 + トップレベル宣言 3)+ (b) 由来 3(機構の不在)。**\n**2 つの母集合は種類が異なる**(D-11 = **宣言の不在** / (b) = **機構の不在**)ので、**拘束④(一対一)を破らない。**')
st('**検査集合の分離と exit 契約**(design.md §3)。**報告の語彙**(宣言が無い / 実体と食い違う / 判定不能)は残すが、**免除の判定には一切用いない**。**FR-040 の除外宣言 schema**。**トリガー 7 を評価**',
   '`[機械]` **exit コード分離**(封印済み由来 = 0 / 封印外 = 1 / 判定不能 = 2)/ **対象集合を 13 とハードコードせず要件書から導出**(**独立導出**)/ **報告の語彙が免除の分岐条件に現れない**静的検査 / 無宣言除外・不正な除外・採用後の case 復帰の 3 負例 / **◎ 封印済み由来のみの入力で exit 0 を返す**(**正例 B**)',
   '`backend/domain/check-sets.json`', '`uv run pytest tests/domain/test_check_sets.py`', True)
st('**封印集合の導出**(design.md §4-3)。**ステップ 10〜12 の実測**と**マニフェスト schema の 10 + 3 宣言 × 対象 13** から封印集合を**機械導出**する。**(b) 由来 3 件の閉じた母集合**(**(b)① 乖離検出の判定機構** / **(b)② 差分の検出可能性の判定機構**(3 層検査)/ **(b)③ 構成の完全性の判定機構**)を**列挙して資産へ書く**。**3 件はいずれも「判定機構の不在」であり、D-11 由来の「宣言の不在」と事項の種類が異なる**(**5 周目 `P1` の是正**: 旧版の 3 件目「本番到達可能な全域の走査対象の宣言が不在」は**宣言**であり **D-11 の `entrypoints[]` と意味上重なっていた**)',
   '`[機械]` **封印集合が実測から導出される**(手書きの列挙を持たない — **独立導出**)/ **要素数が `assert total == 136`**(**母集合計測**。**概数で assert しない**)/ **内訳が `assert d11 == 133 and b == 3`** / **D-11 由来集合と (b) 由来集合が互いに素**(**ID の積集合が空**であることに加え、**全 {N2} 件の要素を代数的型の正規キーで表す** — **`declaration_absence(target, field)`**(D-11 由来 133)と **`mechanism_absence(b_clause)`**((b) 由来 3)の **2 つの互いに素な構成子**とし、**正規キーの一意性を検査する**。**自然文の解消述語を突き合わせる形は採らない** — **言い換えれば通ってしまう**(6 周目 `P1`))/ **(b) 由来 3 件が `NFR-018` (b) の ①②③ と一対一**(**集合差**)/ **構成子が 2 つだけである**ことの静的検査(**3 つ目を足せば重複を隠せるため**)/ **`declaration_absence` の `target` が `NFR-018` 対象欄から・`field` が D-11 の宣言名から導出される**(**独立導出**)/ **(b) 由来 3 件それぞれに安定 ID と解消述語がある**',
   '`backend/domain/boot-seal.json`', '`uv run pytest tests/domain/test_boot_seal_derive.py`', False)
st('**封印の確定と拘束①〜④の検査**(`BOOT-SEAL`)。ステップ 14 の導出結果を**固定 SHA 基準で封印**する',
   '`[機械]` **実測集合と封印集合の差が 1 件でも fail**(**集合差** — `P0-2`: 後段で漏れを発見しても `BOOT-SEAL-MONOTONE` により追加できない)/ **拘束①**(改名で別要素にならない)**②**(封印後の範囲拡大が fail)**③**(対象計算の宣言全体を 1 要素にしていない)**④**(同一事項が 2 要素にならない)**の負例が個別に fail** / **◎ 正しい封印集合が実際に封印され、以後の検証が通る**(**正例 B**)',
   '`backend/domain/boot-seal.sealed.json`', '`uv run pytest tests/domain/test_boot_seal.py`', True)
grp(4, '第 4 群 — 移行状態の機構(16〜24)**新設**',
    '**`P1-4`(4 周目)の是正で並べ替えた** — **個別機構(16〜18)→ 対応表(19)→ 統合判定器(20)→ 負例(21・22)→ 正例(23・24)**。\n旧配置は**統合判定器が全 12 条項の検出経路を要求しながら、停滞・再承認と段階 2 の実装が後段にあった。**\n\n**`P0`(4 周目)の是正**: **条項の母集合は要件書 `NFR-018` (e) の 12 ID を逆引きしたもの** —\n**`BOOT-SEAL` / `-STATE` / `-PROGRAM` / `-GRANT` / `-REAPPROVAL` / `-NO-CLAIM` / `-REPORT` /\n`-SEAL-BASE` / `-SEAL-IMMUTABLE` / `-SEAL-MONOTONE` / `-STALL` / `-ACTIVATION`**。\n**`BOOT-CI-MEANING` は開発ハーネス設計書 10.1 の条項であり、この 12 件に含めない**(別管理)。\n\n**`BOOT-ACTIVATION` は①〜④が同一の PR で必須経路へ接続され実行されることを発効の条件とする。**\n**本群と第 10 群はすべて本 PR に含める** — **分けると発効しない**(design.md §4-6)。')
st('**停滞の測定と再承認**(`BOOT-STALL` / `BOOT-REAPPROVAL`)。エポックの 3 開始点・**`N` = 50**・母集合・優先順位。再承認は**失効後に限る・単回性・専用の変更・昇格後は受け付けない・期限を設けない**',
   '`[機械]` 失効前に作成された承認記録が**再承認として使えない** / 同一承認記録で 2 度エポックを開始すると fail / **再承認の記録に他の変更を含む PR が fail** / **昇格後の再承認が fail** / **承認者が PO 以外なら fail** / **時間的な期限が実装に存在しない**静的検査 / **◎ 正当な再承認が実際に停滞エポックを開始する**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/boot/stall.py`', '`uv run pytest tests/domain/boot/test_stall.py`', True)
st('**段階 2 判定器**(委任③ — design.md §4-5)。**対象単位**で判定し、**4 点が揃っているか**を意味差分で見る。**2 件以上は `ADR-003` 段階 2 違反として fail**。**判定できない場合は段階 2**',
   '`[機械]` **paths 接触を判定に用いていない**静的検査 / **対象 2 件の PR が fail**(§17 是正 `A`)/ **宣言だけの PR は fail しない**が**解消も成立しない**(§17 是正 `B`)/ **対象欄に無い対象の宣言は fail** / **発効前の資産不在が「判定できない場合」に当たらない** かつ **発効後は不成立条件へ戻る**の 2 通り / **◎ 対象 1 件が 4 点揃った PR が段階 2 と判定される**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/boot/phase2.py`', '`uv run pytest tests/domain/boot/test_phase2.py`', True)
st('**未解消レポート**(`BOOT-REPORT`)。**機械可読な未解消要素の一覧**をファイル名・スキーマ・フィールド名込みで確定し、CI が毎回出力する',
   '`[機械]` **出力の無い緑が fail**(逐語「出力のない緑は充足とみなさない」)/ 厳密キー集合 / **一覧を持たず件数だけを出力すると fail**(**`BOOT-REPORT` は一覧を要求する** — design.md §16-8)/ **件数が `封印集合 − 解消済み集合` として導出される**(毎回の再検査で数え直さない)/ **`BOOT-NO-CLAIM` の文言がレポートに含まれる** / **◎ 正しいレポートが実際に出力され、それを含む緑が受理される**(**正例 B**)',
   '`backend/domain/boot-report.schema.json`', '`uv run pytest tests/domain/boot/test_report.py`', True)
st('**条項 ID 対応表**(`BOOT-ACTIVATION` 要求①の母集合)。**要件書 `NFR-018` (e) から 12 の条項 ID を逆引きし**、各条項に**違背として検出するもの・負例 ID・正例 ID**を対応づける',
   '`[機械]` **母集合が正本の逐語から逆引きされる**(手書きの列挙を持たない — **独立導出**。**`P0`(4 周目)の再発防止**)/ **`assert len(ids) == 12`**(**母集合計測**)/ **12 ID の逐語が要件書 `NFR-018` (e) に実在**(**文言存在**)/ **`BOOT-CI-MEANING` がこの表に含まれない**(設計書 10.1 の条項であり (e) の条項ではない)/ **各行に負例 ID と正例 ID の欄がある**',
   '`backend/domain/boot-clauses.json`', '`uv run pytest tests/domain/boot/test_clauses.py`', False)
st('**移行判定器の本体**(要求①)。ステップ 16〜19 を束ね、**12 条項すべての違背を検出する**',
   '`[機械]` **12 条項すべてに検出経路がある**(**集合差** — 対応表と実装の差 1 件で fail)/ **免除適用後の green を入力にしていない**(循環の禁止)/ **exit コード分離** / **◎ 違背が 1 件も無い入力で exit 0 を返す**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/boot/judge.py`', '`uv run pytest tests/domain/boot/test_judge.py`', True)
st('**負例 — 封印系 6 条項**(`BOOT-SEAL` / `-SEAL-BASE` / `-SEAL-IMMUTABLE` / `-SEAL-MONOTONE` / `-PROGRAM` / `-REPORT`)',
   '`[機械]` **6 条項それぞれに負例が 1 件以上**(**集合差** — 負例を持たない条項が 1 件でもあれば fail)/ **各負例が個別に fail する** / **負例を無効化すると検査が緑になる**ことの変異検査',
   '`backend/tests/domain/boot/negatives/seal/`', '`uv run pytest tests/domain/boot/test_negatives_seal.py`', False)
st('**負例 — 状態系 6 条項**(`BOOT-STATE` / `-GRANT` / `-REAPPROVAL` / `-NO-CLAIM` / `-STALL` / `-ACTIVATION`)。**`BOOT-STATE` の「同じ状態に 2 つの終了条件を持たせない」の違背検出を含む**(`P0`(4 周目)で欠落が判明)',
   '`[機械]` **6 条項それぞれに負例が 1 件以上**(**集合差**)/ **各負例が個別に fail する** / **`BOOT-STATE` の負例**(軸①に 2 つ目の終了条件を与える実装が fail する)/ **負例を無効化すると緑になる**ことの変異検査',
   '`backend/tests/domain/boot/negatives/state/`', '`uv run pytest tests/domain/boot/test_negatives_state.py`', False)
st('**正例 A — 例外的遷移**(要求③)。**軸①の自動昇格**と**軸②の失効**が、実際にその条件で成立することを履歴 fixture で示す',
   '`[機械]` **未解消 0 件で自動かつ不可逆に昇格する**(昇格後に移行状態へ戻る経路が実装に存在しない静的検査)/ **50 マージ無減少で失効する** / **50 本目と減少・昇格が同一変更なら減少・昇格を優先する** / **母集合は `develop` の第一親上の PR 統合コミット**(feature 側の取り込みマージを数えない負例)',
   '`backend/tests/domain/boot/positives_a/`', '`uv run pytest tests/domain/boot/test_positives_a.py`', False)
st('**正例 B — 通常動作**(要求④)。**(i)** 封印要素由来の不合格を含む変更が `BOOT-GRANT` で**実際にマージ可能になる** **(ii)** 失効後の正当な再承認で**授権が実際に回復する**。**(iii) 実際に発効することの確認はステップ 51**(実 CI での確認に集約 — `P1-4`(4 周目))',
   '`[機械]` **(i)(ii) が個別に成立する** / **◎ すべての変更と再承認を拒否する実装(deny-all)にすると (i)(ii) とも fail する** / **`requiresPositiveB` が true のステップで正例 B を持たないものが 0 件**(**集合差** — ステップ 3 の台帳と突合。**`requiresPositiveB` が false のステップに正例 B を要求しない**)',
   '`backend/tests/domain/boot/positives_b/`', '`uv run pytest tests/domain/boot/test_positives_b.py`', True)
grp(5, '第 5 群 — 生成器と合成 fixture(25〜29)',
    '**`P1-1` の是正で runner 群より前へ。** **`P1-7` で 5 分割。** **製品ドメインではない合成 DSL** で行う。')
st('**生成コア**(design.md §6-3)。宣言モデル → 中間表現。**段別 hash / version / 生成元 ID** の付与。**言語 backend を持たない**',
   '`[機械]` **中間表現の schema が exact-set** / **空入力で exit 0**(適合判定とは別コマンド・別 exit 契約)/ **`contracts/` に何も書かない** / **生成元 ID が条項 ID 形式**(**文言存在**)/ **◎ 正しい宣言モデルから中間表現が実際に生成される**(**正例 B**)',
   '`backend/src/pitchlog/domaingen/core.py`', '`uv run pytest tests/domain/gen/test_core.py`', True)
st('**言語別 backend**(Python / TypeScript / SQL)。**3 言語の生成のみ**。formatter と参照実装は含まない',
   '`[機械]` **3 言語すべてが生成される**(**母集合計測**)/ **段別 hash が言語をまたいで一致** / **(β)⑦ に集計 reducer を生成していない** / **生成物が直接 import できない形で生成される**(ラッパー越し)/ **◎ 正しい中間表現から 3 言語の生成物が実際に出力される**(**正例 B**)',
   '`backend/src/pitchlog/domaingen/backends/`', '`uv run pytest tests/domain/gen/test_backends.py`', True)
st('**formatter と参照実装**(design.md §6-4)。**(α) Python / TS 双方の formatter** / **表示まで生成するテスト専用 Python 参照実装**。**トリガー 3 を評価**',
   '`[機械]` **参照実装が生成物であり手書きでない**(**`generated_provenance`**)/ **参照実装が formatter まで生成されている** / **参照実装が製品経路に載っていない**静的検査 / **(β)⑦ の写像①適用受け口が生成される** / **◎ 正しい宣言から formatter と参照実装が実際に生成され、同じ表示文字列を返す**(**正例 B**)',
   '`backend/src/pitchlog/domaingen/formatter.py`', '`uv run pytest tests/domain/gen/test_formatter.py`', True)
st('**生成前検査 5 種**(design.md §6-3)。生成に入る前に宣言モデルを検査する 5 系統',
   '`[機械]` **5 種が個別に fail する** / **5 種のいずれかを外すと不正な宣言が生成まで通る**ことを負例で示す / **◎ 正しい宣言が 5 種すべてを通過して生成へ進む**(**正例 B**)',
   '`backend/src/pitchlog/domaingen/pregen_checks.py`', '`uv run pytest tests/domain/gen/test_pregen.py`', True)
st('**合成 DSL fixture と全 target matrix**。**全区分**((α) / (β)①〜⑤ の 3 段 / (β)⑦ の 2 段 / (β)⑥⑧)を合成 DSL で実行検証。**トリガー 8 を評価**',
   '`[機械]` **全 target matrix が生成される**(**母集合計測**で区分数を固定)/ `kind` と段数の整合が実機で成立 / **製品ベクタを含まない**静的検査 / **◎ 合成 DSL から全区分の生成物が実際に出力され、3 層 runner の入力として使える**(**正例 B**) `[手動]` **トリガー 8 の判定**(判定者: 山田正輝。証拠 = 生成器の行数・生成 target 数・保守手順の実測)',
   '`backend/tests/domain/fixtures/synthetic_dsl/`', '`uv run pytest tests/domain/gen/test_target_matrix.py`', True)
grp(6, '第 6 群 — 証跡の収集と経路一致(30〜32)',
    '')
st('**層別収集器**(design.md §8-5)。pytest(JUnit XML の `properties`)/ Vitest(reporter JSON)から実行証跡を採取。**composite では段別 I/O を必須入力とする**。**skip・xfail・todo・0 ケース生成を「実行済み」に数えない**。**トリガー 14 を評価**',
   '`[機械]` 4 通り(skip/xfail/todo/0 生成)を**個別に** fail / 5 項目の欠落を**個別に** fail / **段別 I/O を欠く提出が fail** / **実行証跡の生成元も負例で検査** / **◎ 正しい実行証跡が「実行済み」として実際に数えられる**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/collect_layers.py`', '`uv run pytest tests/domain/test_collect_layers.py`', True)
st('**経路一致の証跡 schema と比較器**(design.md §7)。5 判定・**6 次元要求集合**・**値の連鎖の独立検証**・**表示値は文字列の完全一致**。**トリガー 4 を評価**',
   '`[機械]` 5 判定のいずれか不成立で fail / **要求集合と証跡集合の差 1 件で fail**(**集合差**)/ 入口 2 つで片方だけ実行を検出 / **比較器が丸めない** / 未知・欠落フィールドで fail / **状況判定は構造化のみ・断中前処理は表示値を含む**を両方 fixture で確認 / **◎ 正当な証跡が実際に 5 判定を通る**(**正例 B**)',
   '`backend/domain/path-match.schema.json`', '`uv run pytest tests/domain/test_path_match.py`', True)
st('**経路一致の敵対 fixture**(design.md §7-4)。**偽 SQL / 段別 hash 不一致 / 期待値直返し / 値の連鎖不整合**の 4 種 + **恣意的迂回を保証範囲外として記録**',
   '`[機械]` 4 種すべてで fail / **アダプタが `true` を 5 個返すだけでは通らない** / **段別 hash が `generated[]` と不一致で fail**(段数分)/ **「迂回を検出する」合格条件を持たない**静的検査',
   '`backend/tests/domain/fixtures/adversarial_path/`', '`uv run pytest tests/domain/test_path_adversarial.py`', False)
grp(7, '第 7 群 — 3 層 runner(33〜37)',
    '')
st('**網羅ベクタ runner の基盤**。合成契約で **生値 → 生成済み正規化 → 正規化後値の照合 → 計算入力**、**全 case 消費**、**未知 field / 重複 ID の拒否**',
   '`[機械]` **正規化を素通りさせた入力が fail** / 未対応 case・未知 field・重複 ID・schema 不一致がそれぞれ fail / **◎ 正しいベクタが全 case 消費で実際に通る**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/runners/vectors.py`', '`uv run pytest tests/domain/runners/test_vectors.py`', True)
st('**要求 case 集合と網羅性の証明**(design.md §8-1)。**表示 primitive の同値分割 8 軸** × **丸め境界 × 符号の直積**を要求 case 集合として資産化し、**証跡集合との差を fail**',
   '`[機械]` **8 軸すべてに case がある**(**母集合計測**)/ **丸め境界(直前・一致・直後)× 符号(正・負)の直積 6 通りが完全一致で存在する** / **負値の丸め境界一致が存在する** / **6 通りを 1 件ずつ削る負例が個別に fail** / **集合差** / **要求集合を正本 ID と schema 軸から独立生成する**(**独立導出**)/ **「全 case 消費」だけでは通らない**負例 / **◎ 要求 case 集合を満たす証跡が実際に通る**(**正例 B**)',
   '`backend/domain/required-cases.json`', '`uv run pytest tests/domain/runners/test_coverage_proof.py`', True)
st('**不変条件 runner の本体**(design.md §8-2)。カタログの述語を**生成 case へ適用**し偽なら fail。**述語ごとに典拠(条項 ID)**',
   '`[機械]` 述語違反で fail / **述語ごとに典拠がある**(**文言存在**)/ **0 ケース生成を「実行済み」に数えない** / **不変条件テストと等価性テストの双方が 1 件以上完走**しないと fail / **◎ 述語をすべて満たす case 集合で実際に完走する**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/runners/properties.py`', '`uv run pytest tests/domain/runners/test_invariants.py`', True)
st('**プロパティ runner(等価性)**(design.md §8-3)。**(β) を 3 区分**に分け区分別の比較面を持つ。ライブラリ選定',
   '`[機械]` 区分別に等価性違反が fail / **構造化段と表示段の両方を比較している** / **参照実装が生成物であり手書きでない**(**`generated_provenance`**)/ **製品経路に載っていない** / **◎ 等価な実装どうしが実際に一致と判定される**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/runners/equivalence.py`', '`uv run pytest tests/domain/runners/test_equivalence.py`', True)
st('**プロパティ runner(カタログ独立性)**。**allowlist × ファイルアクセス証跡**の突合 + **生成器依存グラフにカタログが現れないことの静的検査**',
   '`[機械]` allowlist 外の読み取りで fail / 依存グラフにカタログを混ぜると fail / **◎ allowlist 内の読み取りだけで runner が実際に完走する**(**正例 B**)',
   '`backend/domain/property-catalog.json`', '`uv run pytest tests/domain/runners/test_catalog_independence.py`', True)
grp(8, '第 8 群 — 変異(38〜42)',
    '**`P1-5`(4 周目)の是正でエンジンと言語別演算子を分けた。**')
st('**変異エンジン**(design.md §9-2)。**未対応箇所の列挙と fail**・**生成変異 0 で fail**・**kill 要因の必須記録**・**プロパティ層 kill 0 件で fail**・**(b)① による kill を分子に数えない**',
   '`[機械]` 未対応 1 件で fail / 生成変異 0 で fail / **対象計算ごとに `generated - approved_equivalents - killed == ∅`** / **負例 3 種が個別に fail**(生存 1 件 / 他対象による希釈 / 未記録を等価扱い)/ **合成対象が非空で固定されている** / **hash 検査だけで kill された mutant が分子に入らない** / **◎ 正しい変異が実際に生成され kill される**(**正例 B**)',
   '`backend/src/pitchlog/domainmut/engine.py`', '`uv run pytest tests/domain/mut/test_engine.py`', True)
st('**言語別変異演算子**(Python / TypeScript / **SQL**)。**トリガー 5 を評価**',
   '`[機械]` **3 言語それぞれが個別に mutant を生成する**(**母集合計測**)/ 未対応構文が「未対応」として列挙され fail する / **◎ 3 言語すべてで実際に mutant が kill される**(**正例 B**)',
   '`backend/src/pitchlog/domainmut/operators_lang.py`', '`uv run pytest tests/domain/mut/test_lang_operators.py`', True)
st('**表示系変異演算子**(design.md §9-1)。文字列リテラル置換・placeholder の削除と入替・写像テーブルの値と順序・**表示 primitive のパラメータ変異**・**formatter 呼出の削除と言語既定文字列化への置換**。**トリガー 5・15 を評価**',
   '`[機械]` 5 系統の演算子が個別に mutant を生成 / **表示生成物を持つ対象計算で表示系が 0 件なら fail** / **`scale=0` の formatter 迂回が等価変異として台帳へ回る**(kill 要件にしない)/ **◎ 5 系統それぞれで実際に mutant が生成され kill される**(**正例 B**)',
   '`backend/src/pitchlog/domainmut/operators_display.py`', '`uv run pytest tests/domain/mut/test_display_operators.py`', True)
st('**変異の影響範囲解決と時間予算**(design.md §9-4)。**変更対象 + 依存先の逆引き**・**全面発火条件**・**変異処理内の 10 分 / 30 分タイムアウト**・**逆引き不能は全面**(fail-closed)',
   '`[機械]` 発火条件 7 種を個別に検査 / **逆引き不能で全面へ倒れる** / **内部タイムアウトで fail** / 上限超過が暫定マージにならない / **◎ 変更対象と依存先が正しく解決され、全面へ倒れずに完了する**(**正例 B**)',
   '`backend/src/pitchlog/domainmut/scope.py`', '`uv run pytest tests/domain/mut/test_scope.py`', True)
st('**等価変異台帳の基盤**(design.md §9-3)。識別子・理由・**判定者 = PO**・判定日。**空台帳でよい**。**未記録は非等価扱い**。**トリガー 15 を評価**',
   '`[機械]` 厳密キー / 判定者が PO 以外なら fail / **未記録の変異が非等価として扱われる** / 台帳の改変が全面発火を起こす / **◎ 台帳に記録された等価変異が実際に kill 要件から外れる**(**正例 B**)',
   '`backend/domain/mutation-equivalents.json`', '`uv run pytest tests/domain/mut/test_equivalents.py`', True)
grp(9, '第 9 群 — (b)① と (b)③ の判定(43〜47)**第 2 群の収集器を使う側**',
    '')
st('**(b)① 乖離検出と D-3 のコミット単位検査**。**PR 内の各コミットを走査**し、正本変更と当該生成物・generator version 変更と全生成物が**同一コミットにある**ことを検査',
   '`[機械]` **片側コミット → 後続で揃える**履歴が fail する(**最終ツリー一致では通さない**)/ 古い派生物・手修正の 2 通りが個別に fail / **`backend/domain/` だけの変更でも発火** / **◎ 正本と生成物が揃ったコミットが実際に通る**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/divergence.py`', '`uv run pytest tests/domain/test_divergence.py`', True)
st('**(b)③ frontend 閉域 — 依存規則**(design.md §10-1)。**ステップ 10 の収集器の実測**と `entrypoints[]` の突合 + `dependency-cruiser` + lint による動的機構の禁止 + **`src/lib/generated/` の新設**。**トリガー 6 を評価**',
   '`[機械]` **実在入口と `entrypoints[]` の差 1 件で fail**(**集合差**)/ **正例・負例・解析不能例の 3 通り** / **判定不能を合格にしない** / **import graph を直接読む統合テスト** / **◎ 実在入口と `entrypoints[]` が一致したとき実際に通る**(**正例 B**)',
   '`frontend/.dependency-cruiser.cjs` / `frontend/src/lib/generated/`', '`pnpm exec depcruise --validate` + `pnpm test -- --run`', True)
st('**(b)③ frontend 閉域 — CSP と build**。`index.html` の CSP + production build 検査',
   '`[機械]` **CSP 設定を直接読む統合テスト** / **外部リソース参照が 1 件でも fail** / 正例・負例・解析不能例の 3 通り / **◎ 外部リソース参照の無い build が実際に通る**(**正例 B**)',
   '`frontend/index.html` / `frontend/vite.config.ts`', '`pnpm run build` + `pnpm test -- --run`', True)
st('**(b)③ backend 閉域と実行時制限**(design.md §10-2)。**ステップ 11 の収集器の実測**と `entrypoints[]` の突合 + `importlib` / `getattr` / entry point 経由の読み込み禁止 + 実行時の制限',
   '`[機械]` 3 通り / **宣言外の入口を拒否する**(検出ではなく)/ **集合差** / **◎ 宣言と実在が一致したとき実際に通る**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/closure_be.py`', '`uv run pytest tests/domain/test_closure_be.py`', True)
st('**(b)③ 表外既定の表示対応の突合**(design.md §10-3)。**ステップ 12 の解析器の実測**とマニフェストの表示対応宣言を突合。**トリガー 6・13 を評価**',
   '`[機械]` **登録漏れ・formatter 非経由の表示経路が差分として fail**(**集合差**)/ **対象集合が schema 閉包から導出される**(**独立導出**)/ **未宣言項目がステップ 14 の封印集合に既に含まれている**(後から足せない)/ **◎ すべての表示項目が宣言と一致したとき実際に通る**(**正例 B**)',
   '`backend/domain/display-binding.json`', '`uv run pytest tests/domain/test_display_binding.py`', True)
grp(10, '第 10 群 — 実測・整合検査・CI 配線(48〜54)',
    '**`P1-5`(4 周目)の是正で旧 1 ステップを 3 つへ分けた**(ジョブ新設 / 依存とツール設定 / 発効の実確認と文書同期)。\n**`P0`・`P1`(5 周目)の是正で 2 つ追加した**(トリガー評価の完了検査 / 計画書と生成元の一致検査)。')
st('**変異コストの拘束実測**。ステップ 29 の合成生成物・全 runner・**4 系統の演算子**で **mutant 数 × スイート再実行時間**を実測。**トリガー 5・12 を評価**',
   '`[機械]` 生ログ・コマンド・commit SHA・runner・mutant 分類が schema 化されて記録 / **◎ 実測レコードが実際に生成され、10 分 / 30 分以内なら通る**(**正例 B**)`[手動]` **上限判定**(判定者: 山田正輝)。**超過なら design.md §12-2 で停止し ADR 改訂ゲートへ**',
   '`docs/features/domain-calc-dsl/mutation-cost.json`', '`uv run pytest tests/domain/mut/test_cost_record.py`', True)
st('**見直しトリガー 16 件の評価完了検査**(**5 周目 `P1` の是正** — ステップ 4 から分離した後段)。**全 16 件に評価結果があり、未評価が 0 件**であることを検査する。**証拠資産の実在もここで要求する**',
   '`[機械]` **16 件すべてに評価結果がある**(**母集合計測**。未評価 1 件でも fail)/ **`[手動]` 9 件の証拠資産のパスが実在する**(**パス allowlist** + 実在検査)/ **発火レコードがあれば本ステップより後をすべて拒否する**(ステップ 5 と同じ機構を再適用)/ **◎ 全件が非発火で評価済みなら実際に通る**(**正例 B**)',
   '`backend/src/pitchlog/domaincheck/trigger_completion.py`', '`uv run pytest tests/domain/test_review_triggers_complete.py`', True)
st('**計画書と生成元の構造検査**(**5 周目 `P0` の是正** — §5-3 の 8 検査のうち 5 件に実装ステップが無かった。**3 周目 `P0-7` の 3 回目**)。**`steps.py` の出力と plan.md §4・§5-1 の本体を完全比較し、表の構造を検査する**。**履歴と `command` の監査はステップ 51**(**6 周目 `P1` の是正**: 一致比較・全射単射・履歴時点の実在・{N} 件の `command` 実行・自己整合負例を 1 コミットに集約しており、**しかも本ステップ自身の `command` を全件実行すると自己再帰する**構成だった)',
   '`[機械]` **`emit_steps()` / `emit_dod()` の出力が plan.md の当該範囲と完全一致**(1 文字でも違えば fail)/ **全射**(ステップ表の 1〜{N} がすべて DoD 表に現れる — **集合差**)/ **単射**(各 `stepId` が 1 回だけ — **母集合計測**)/ **§5-3 の「実装ステップ」列に空欄が無い**(**母集合計測**)/ **`steps.py check()` が総数・群 ID の一意性と昇順・`S[].g` と群範囲の突合・見出し範囲の存在と一致・`PB_FALSE` の exact-set を検査する** / **`PB_FALSE` が封印されており、集合とフラグの同時変更が fail する**(ステップ 9 の封印機構を流用 — **6 周目 `P1`: `PB_FALSE` へ足せば正例 B を免れる経路を塞ぐ**)/ **◎ `scripts/feature_status.py` が全 {N} ステップを正しく読める**(**§16-14** — **群見出しを `####` にすると表が分断される**。**文書を読む機構を実際に走らせて確認する**)/ **◎ 一致しているとき実際に通る**(**正例 B**)/ **負例 7 種が個別に fail**(末尾 1 件を落とす / 群を誤配置する / 群 ID を重複・逆順にする / 見出し範囲を解析不能な表記へ変える / `pb` を両方 false へ倒す / `pb` と `PB_FALSE` を同時に書き換える / **群見出しを `####` にして表を分断する**)',
   '`tests/test_plan_generation.py`', '`uv run pytest tests/test_plan_generation.py`', True)
st('**履歴と `command` の監査**(**6 周目 `P1` の是正** — ステップ 50 から分離)。'
   '**各ステップのコミットを履歴から検査し、当該ステップ完了時点で `artifact` が実在したこと**と、'
   '**`command` が実際に実行され終了コード 0 だったこと**を確認する',
   '`[機械]` **`artifact` の実在を履歴時点で検査する**(**現在木では「当該ステップ完了時点の実在」を証明できない** — '
   '**`history_precedes` と同じく履歴を見る**)/ **各 `command` の `cwd`・期待 exit=0 を資産に持つ**(**パス allowlist**)/ '
   '**`command` の重複が無い**かつ **`artifact` の重複が無い**(**母集合計測**)/ '
   '**◎ 本ステップ自身の `command` は他ステップの `command` 実行から除外する**(**自己再帰の禁止**。'
   '**除外が実装に存在することの静的検査**)/ **◎ 全 `command` が exit 0 で完了したとき実際に通る**(**正例 B**)/ '
   '**負例 3 種**(履歴時点で不在の `artifact` / exit 非 0 の `command` / 自己再帰を許す実装)**が個別に fail**',
   '`tests/test_step_history_audit.py`', '`uv run pytest tests/test_step_history_audit.py`', True)
st('**CI ジョブの新設と配線**(design.md §14・§4-6)。`consistency` + 変異ジョブ(別ジョブ)の新設。**§14 の所有ジョブ分離**。**両ジョブに `timeout-minutes`**。**DB を使うジョブへ `services: postgres`**。**第 4 群 9 ステップの資産を `consistency` へ配線**',
   '`[機械]` `tests/test_ci_wiring.py` の YAML 契約木の**全葉変異で escape 0** かつ **母集合計測** / **全葉変異の母集団を新設ジョブまで一般化** / **DB を使う全ジョブで image が 3 者一致** / **新設ジョブに `services: postgres` を書き忘れると red** / `services` を持たないジョブが DB テストを呼んでいない / **同一テストが二重実行されない** / **第 4 群 9 ステップの資産がすべて `consistency` の実行対象に含まれる**(**集合差** — 1 件でも外れたら fail)/ **◎ ステップ 50・51 のテストが PR 必須ジョブ ちょうど 1 件から実行される**(**集合差**。**6 周目 `P1` の是正**: 旧版は第 4 群だけを配線対象にしており、**計画書の整合検査がローカルだけで終わる構成を排除できなかった**)/ **◎ 新設ジョブが実際に実行され緑になる**(**正例 B**)',
   '`.github/workflows/ci.yml` / `tests/test_ci_wiring.py`', '`uv run pytest tests/test_ci_wiring.py`', True)
st('**依存・lock・`ty` の対象・coverage**。`ty` の `include` / `testpaths` / package-data + 依存と lock + **`backend/.coverage` の index 除去**',
   '`[機械]` **`backend/domain/` が `ty check` の対象** / **`uv sync --locked` が通る**(`TSK-343` の 3 assert を通したまま再生成)/ **`backend/.coverage` が index から消え、再生成後も untracked** / **実 wheel に含まれるファイル一覧のテスト** / **◎ `uv sync --locked` と `ty check` が実際に通る**(**正例 B**)',
   '`backend/pyproject.toml` / `backend/uv.lock`', '`uv sync --locked` + `uv run pytest tests/test_packaging.py`', True)
st('**発効の実確認と文書同期**(`BOOT-ACTIVATION`)。**第 4 群の機構・負例・正例、および ステップ 50・51 の整合検査が実 CI で実際に実行されたことを証跡で確認**する。`github-setup.md` の 3 分類 + Ruleset JSON + 設計書 10.1 + 索引',
   '`[機械]` **「接続されている」だけでなく「実行された」ことを証跡で確認する**(§17 是正 `C` — 逐語「存在するだけでは足りない」)/ **◎ ステップ 50・51 の実行証跡が存在する**(**集合差** — 6 周目 `P1`)/ **◎ 要求①〜④が揃ったとき実際に発効する**(**正例 B** — 要求④ (iii) の本体。ステップ 24 から移した)/ **`github-setup.md` の 3 分類と Ruleset JSON の記述が 9 → 11 context へ同期**(**集合差**。**検査できるのは文書の同期のみ** — `required_status_checks` はリモートに存在せず〔個人 Free + private で Rulesets 利用不可〕、**強制は `github-setup.md` 2 章の人間の手続き**)/ `check_docs_status` / `check_doc_coverage` / `check_design_propagation` OK',
   '`docs/development/github-setup.md` / `docs/development/dev-harness-design-2026-08-07.md` / `docs/README.md`', '`uv run pytest tests/test_ci_wiring.py` + `uv run python scripts/check_docs_status.py`', True)
grp(11, '第 11 群 — コア領域の登録(55〜56)',
    '')
st('**`core-guard` の基線機構**(design.md §11-1・§11-2)。`EXPECTED_AREA_PATHS` を**二層方式**(据え置き / 追加分・**領域ごとに分ける**)へ改め、**base 側 commit アンカーに一本化**して基線を外部化',
   '`[機械]` **比較元が PR head ではなく変更不能な merge-base の blob である** / **他 3 領域は据え置き層から導出され、テスト内リテラルの書き換えだけでは green にならない** / 追加層に無い変更が fail / **JSON と期待値を同一コミットで書き換える型が fail する**負例 / **JSON・期待値・アンカーの 3 点を同時変更しても fail する**履歴 fixture / **◎ 据え置き層と追加層に正しく登録された変更が実際に通る**(**正例 B**)',
   '`scripts/core_guard.py` / `tests/test_core_guard.py`', '`uv run pytest tests/test_core_guard.py`', True)
st('**`core-areas.json` の登録**。**`game-state` と `data-migration` の両方**へ該当パスを **glob で**追加(完全列挙にしない — design.md §11-5)',
   '`[機械]` **JSON の両 area 配列に該当 glob が含まれる** / **後から足したファイルが glob に覆われる**ことを負例で示す(**集合差**)/ **他 3 領域は据え置き層のまま** / 新規各パスの変更で core-guard が発火 / **◎ 登録対象外のパスの変更では発火しない**(**正例 B** — 全変更を発火させる実装を排除する) `[手動]` **敵対レビュー + 人間承認(PR 作成者以外の逐行確認)** — 設計書 6.3-⑤',
   '`.claude/core-areas.json`', '`uv run pytest tests/test_core_guard.py::test_area_registration`', True)

def group_of(step_id):
    """ステップ番号から群番号を返す。"""
    for gid, _t, _n, a, b in GROUPS:
        if a <= step_id <= b:
            return gid
    raise KeyError(step_id)


def _fill(text):
    """本文中のプレースホルダを展開する。

    6 周目 `P1`: ステップ 3 の本文が「全 53 ステップ」のまま総数の変更へ追随せず、
    **ステップ 54・55 の授権行を欠いても通る**状態だった。数値リテラルを置かない。
    """
    return text.replace("{N2}", str(136)).replace("{N}", str(EXPECTED_TOTAL))


def emit_steps():
    """§4 の実装ステップ表の本体を返す。"""
    out, cur = [], None
    for s in S:
        if s["g"] != cur:
            if cur is not None:
                out.append("")
            cur = s["g"]
            gid, title, note, _a, _b = next(g for g in GROUPS if g[0] == cur)
            # 見出し(`#### `)にしない — `scripts/feature_status.py` は見出しを見つけると
            # 実装ステップ節を抜けるため、群見出しを入れると表全体が検出されなくなる。
            out.append("**" + title + "**\n")
            if note:
                out.append(note + "\n")
            out.append("| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |")
            out.append("| --- | --- | --- |")
        out.append("| %d | %s | %s |" % (s["id"], _fill(s["t"]), _fill(s["c"])))
    return "\n".join(out)


def emit_dod():
    """§5-1 の DoD 表の本体を返す。"""
    return "\n".join(
        "| %d | %s | %s | %s | %s |" % (s["id"], "✓" if s["pb"] else "—", s["a"], _fill(s["c"]), s["m"])
        for s in S
    )


def check():
    """自己整合を検査する。不整合があれば一覧を返す。

    5 周目 `P1`: 旧版は「ID が 1 からの連番であること」しか見ておらず、
    ID を呼び出し順で採番する以上それは常に成立していた。末尾を 1 件落としても
    エラー 0 件で通った。総数・群の連続性・`pb` の閉じた集合を加える。

    6 周目 `P1`: さらに 群 ID の一意性と昇順・`S[].g` と群範囲の突合・
    見出し範囲が「無い場合も fail」・`artifact` と `command` の重複を加えた。
    負例 10 種のうち 9 種を検出することを実測した。

    **本関数が原理的に検出できないもの(§16-3 — 限界を併記する)**:

    - **`pb` フラグと `PB_FALSE` を同時に書き換える変更。**
      両方とも本ファイル内の自己申告なので、整合したまま一緒に動かせば
      本関数からは正しく見える。**これは自己申告を別の自己申告で検査する形の限界**であり、
      関数の作りでは閉じられない。
      → **ステップ 50 が `PB_FALSE` を承認済み基準に対して封印し**(ステップ 9 の封印機構)、
      **当該 PR からの書き換えを無条件に fail させる**ことで閉じる。
      **比較元は固定 SHA であり当該 PR から変更できない**ため、同時変更は封印側で落ちる。
    - **合格条件の本文が意味として妥当かどうか。** 文字列 "正例 B" の有無しか見ていない。
    """
    import re

    errs = []
    if len(S) != EXPECTED_TOTAL:
        errs.append("ステップ総数が %d 件(EXPECTED_TOTAL = %d)" % (len(S), EXPECTED_TOTAL))
    ids = [s["id"] for s in S]
    if ids != list(range(1, len(S) + 1)):
        errs.append("ステップ番号が 1 からの連番でない")

    # 群: ID が 1..N の一意な昇順であり、隙間なく 1..N を覆い、空でないこと
    gids = [g[0] for g in GROUPS]
    if len(set(gids)) != len(gids):
        errs.append("群 ID が重複している: %s" % gids)
    if gids != sorted(gids):
        errs.append("群 ID が昇順でない: %s" % gids)
    if gids != list(range(1, len(GROUPS) + 1)):
        errs.append("群 ID が 1 からの連番でない: %s" % gids)
    covered = []
    prev_end = 0
    for gid, title, _note, a, b in GROUPS:
        if a is None or b is None or b < a:
            errs.append("群 %s が空" % gid)
            continue
        if a != prev_end + 1:
            errs.append("群 %s の開始が %d で、直前の群の終わり %d と連続しない" % (gid, a, prev_end))
        prev_end = b
        covered.extend(range(a, b + 1))
        m = re.search(r"\((\d+)〜(\d+)\)", title)
        if m is None:
            # 6 周目 `P1`: 見出し範囲を解析不能な表記へ変えると検査が素通りしていた
            errs.append("群 %s の見出しに (a〜b) 形式の範囲が無い: %r" % (gid, title))
        elif (int(m.group(1)), int(m.group(2))) != (a, b):
            errs.append("群 %s の見出しの範囲 (%s〜%s) が実体 (%d〜%d) と一致しない"
                        % (gid, m.group(1), m.group(2), a, b))
    if covered != ids:
        errs.append("群がステップ全体を隙間なく覆っていない")

    # 各ステップの g が、自分が属する群の範囲と一致すること
    for s in S:
        try:
            expected = group_of(s["id"])
        except KeyError:
            continue
        if s["g"] != expected:
            errs.append("ステップ %d の g=%s が、群範囲から導かれる %s と一致しない"
                        % (s["id"], s["g"], expected))

    # artifact と command の重複が無いこと
    for key, label in (("a", "artifact"), ("m", "command")):
        seen = {}
        for s in S:
            seen.setdefault(s[key], []).append(s["id"])
        for value, owners in seen.items():
            if len(owners) > 1:
                errs.append("%s が重複している(ステップ %s): %s" % (label, owners, value))

    # pb: 宣言した閉じた集合と一致すること(両方向)
    actual_false = frozenset(s["id"] for s in S if not s["pb"])
    if actual_false != PB_FALSE:
        errs.append("pb=false の集合が PB_FALSE と一致しない(余分 %s / 不足 %s)"
                    % (sorted(actual_false - PB_FALSE), sorted(PB_FALSE - actual_false)))

    # pb と本文の整合
    for s in S:
        if s["pb"] and "正例 B" not in s["c"]:
            errs.append("ステップ %d: pb=true だが合格条件に正例 B が無い" % s["id"])
        if not s["pb"] and "正例 B" in s["c"]:
            errs.append("ステップ %d: pb=false だが合格条件に正例 B がある" % s["id"])
        try:
            group_of(s["id"])
        except KeyError:
            errs.append("ステップ %d がどの群にも属さない" % s["id"])
    return errs


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "steps":
        print(emit_steps())
    elif mode == "dod":
        print(emit_dod())
    else:
        problems = check()
        if problems:
            for line in problems:
                print(line)
            sys.exit(1)
        print("OK: %d ステップ / pb true %d・false %d / 群 %d"
              % (len(S), sum(1 for s in S if s["pb"]), sum(1 for s in S if not s["pb"]), len(GROUPS)))
