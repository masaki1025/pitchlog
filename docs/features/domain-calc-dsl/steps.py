"""TSK-235 の実装ステップの単一定義から plan.md の 2 つの表を生成する。

データの正は同ディレクトリの ``steps.json``。本ファイルは生成と自己整合検査だけを持つ。
``plan.md`` の §4 実装ステップ表と §5-1 DoD 表は、どちらもここから生成する。
2 つの表を人手で追随させたことが 3 周目 ``P1-6``・4 周目 ``P2`` の原因だったため。

使い方::

    python3 steps.py steps   # §4 のステップ表本体
    python3 steps.py dod     # §5-1 の DoD 表本体
    python3 steps.py check   # 自己整合の検査

**データを JSON へ分けた理由**(2026-09-18): 本文を Python の文字列リテラルで持つと
``ruff`` の ``E501``(行長 100・日本語は全角 1 文字 = 2 桁)に 169 件かかった。
**リポジトリルートの ``uv run ruff check .`` は ``docs/`` 配下の ``.py`` も検査する** —
旧版の docstring は「検査対象に含まれない」と書いていたが、**走らせずに書いた誤りだった**
(design.md §16-14 の 2 例目)。JSON は ``ruff`` の対象外で、本ファイルは短く保てる。

``plan.md`` との一致は ``tests/test_plan_generation.py``(ステップ 50)が検査する。
"""

import json
import re
import sys
from pathlib import Path

DATA_PATH = Path(__file__).with_name("steps.json")


def load():
    """``steps.json`` を読み込む。"""
    with DATA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def fill(text, data):
    """本文中のプレースホルダを展開する。

    6 周目 ``P1``: ステップ 3 の本文が「全 53 ステップ」のまま総数の変更へ追随せず、
    **ステップ 54・55 の授権行を欠いても通る**状態だった。数値リテラルを置かない。
    """
    return text.replace("{N2}", "136").replace("{N}", str(data["expected_total"]))


def emit_steps(data):
    """§4 の実装ステップ表の本体を返す。"""
    out = []
    current = None
    groups = {group["id"]: group for group in data["groups"]}
    for step in data["steps"]:
        if step["group"] != current:
            if current is not None:
                out.append("")
            current = step["group"]
            group = groups[current]
            # 見出し(`#### `)にしない — `scripts/feature_status.py` は見出しを見つけると
            # 実装ステップ節を抜けるため、群見出しを入れると表全体が検出されなくなる。
            out.append("**" + group["title"] + "**\n")
            if group["note"]:
                out.append(group["note"] + "\n")
            out.append("| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |")
            out.append("| --- | --- | --- |")
        out.append(
            "| %d | %s | %s |"
            % (step["id"], fill(step["title"], data), fill(step["criteria"], data))
        )
    return "\n".join(out)


def emit_dod(data):
    """§5-1 の DoD 表の本体を返す。"""
    return "\n".join(
        "| %d | %s | %s | %s | %s |"
        % (
            step["id"],
            "✓" if step["requires_positive_b"] else "—",
            step["artifact"],
            fill(step["criteria"], data),
            step["command"],
        )
        for step in data["steps"]
    )


def group_of(data, step_id):
    """ステップ番号から群番号を返す。"""
    for group in data["groups"]:
        if group["first"] <= step_id <= group["last"]:
            return group["id"]
    raise KeyError(step_id)


def check_groups(data, ids, errs):
    """群 ID の一意性・昇順・連番と、見出し範囲の一致を検査する。"""
    gids = [group["id"] for group in data["groups"]]
    if len(set(gids)) != len(gids):
        errs.append("群 ID が重複している: %s" % gids)
    if gids != sorted(gids):
        errs.append("群 ID が昇順でない: %s" % gids)
    if gids != list(range(1, len(gids) + 1)):
        errs.append("群 ID が 1 からの連番でない: %s" % gids)
    covered = []
    prev_end = 0
    for group in data["groups"]:
        first, last = group["first"], group["last"]
        if first is None or last is None or last < first:
            errs.append("群 %s が空" % group["id"])
            continue
        if first != prev_end + 1:
            errs.append(
                "群 %s の開始が %d で、直前の群の終わり %d と連続しない"
                % (group["id"], first, prev_end)
            )
        prev_end = last
        covered.extend(range(first, last + 1))
        matched = re.search(r"\((\d+)〜(\d+)\)", group["title"])
        if matched is None:
            # 6 周目 `P1`: 見出し範囲を解析不能な表記へ変えると検査が素通りしていた
            errs.append("群 %s の見出しに (a〜b) 形式の範囲が無い" % group["id"])
        elif (int(matched.group(1)), int(matched.group(2))) != (first, last):
            errs.append(
                "群 %s の見出しの範囲 (%s〜%s) が実体 (%d〜%d) と一致しない"
                % (group["id"], matched.group(1), matched.group(2), first, last)
            )
    if covered != ids:
        errs.append("群がステップ全体を隙間なく覆っていない")

STEP_REF = re.compile(r"ステップ\s*(\d+(?:\s*[〜~・、]\s*\d+)*)")
DEADLINE_REF = re.compile(r"トリガー\s*(\d+)\s*の評価期限はステップ\s*(\d+)")
TRIGGERS = Path(__file__).resolve().parents[3] / "backend/domain/review-triggers.json"


def step_refs(text):
    """本文中の「ステップ N」参照を (番号, 表記) の一覧で返す。"""
    out = []
    for m in STEP_REF.finditer(text):
        for token in re.split(r"[〜~・、]", m.group(1)):
            out.append((int(token.strip()), m.group(0)))
    return out


def check_crossrefs(data, errs):
    """ステップ相互参照の宛先が実在し、自己参照でないことを検査する。

    2026-09-19 の再発(§16 型 A)への機構。ステップ 13 を挿入した際、
    挿入前に書かれた「ステップ N」参照 14 箇所を人手で数え落とした。

    **本検査が捕まえるのは範囲外参照と自己参照だけである。**
    当該 14 箇所のうち本検査で検出できたのは自己参照 1 件のみで、
    残り 13 件は「実在する別のステップを指している」ため通過する。
    意味として正しい宛先かは、参照を番号ではなく記号で持たない限り機械では
    決まらない(§16 に記号参照化を真の是正として記録した)。
    """
    total = len(data["steps"])
    for step in data["steps"]:
        for key in ("title", "criteria"):
            for num, token in step_refs(step[key]):
                if not 1 <= num <= total:
                    errs.append(
                        "ステップ %d の %s: 参照先 %d が存在しない(総数 %d・%s)"
                        % (step["id"], key, num, total, token)
                    )
                elif num == step["id"]:
                    errs.append(
                        "ステップ %d の %s: 自己参照(「本ステップ」と書く・%s)"
                        % (step["id"], key, token)
                    )


def check_trigger_deadlines(data, errs):
    """本文が書くトリガー評価期限を review-triggers.json と突合する。

    期限の正は資産側であり、計画書本文はその写しにすぎない。
    ステップ 1 が書く「トリガー 1 の評価期限はステップ N」は、
    挿入で N がずれても範囲内に留まるため check_crossrefs では捕まらない。
    """
    if not TRIGGERS.exists():
        errs.append("review-triggers.json が見つからない: %s" % TRIGGERS)
        return
    payload = json.loads(TRIGGERS.read_text(encoding="utf-8"))
    deadlines = {str(t["id"]): str(t["evaluationDeadline"]) for t in payload["triggers"]}
    for step in data["steps"]:
        for key in ("title", "criteria"):
            for tid, said in DEADLINE_REF.findall(step[key]):
                want = deadlines.get(tid)
                if want is None:
                    errs.append("ステップ %d: トリガー %s が資産に無い" % (step["id"], tid))
                elif want != said:
                    errs.append(
                        "ステップ %d: トリガー %s の評価期限が本文 %s・資産 %s で食い違う"
                        % (step["id"], tid, said, want)
                    )


def check_duplicates(data, errs):
    """``artifact`` と ``command`` の重複を検査する。"""
    for key, label in (("artifact", "artifact"), ("command", "command")):
        seen = {}
        for step in data["steps"]:
            seen.setdefault(step[key], []).append(step["id"])
        for value, owners in seen.items():
            if len(owners) > 1:
                errs.append("%s が重複している(ステップ %s): %s" % (label, owners, value))


def check(data):
    """自己整合を検査する。不整合があれば一覧を返す。

    5 周目 ``P1``: 旧版は「ID が 1 からの連番であること」しか見ておらず、
    ID を呼び出し順で採番する以上それは常に成立していた。末尾を 1 件落としても
    エラー 0 件で通った。総数・群の連続性・``pb`` の閉じた集合を加える。

    6 周目 ``P1``: さらに 群 ID の一意性と昇順・群範囲の突合・見出し範囲が
    「無い場合も fail」・``artifact`` と ``command`` の重複を加えた。
    負例 10 種のうち 9 種を検出することを実測した。

    **本関数が原理的に検出できないもの**(§16-3 — 限界を併記する):

    - **``requires_positive_b`` と ``pb_false`` を同時に書き換える変更。**
      どちらも同じ資産内の自己申告なので、整合したまま一緒に動かせば正しく見える。
      → **ステップ 51 が ``pb_false`` を承認済み基準に対して封印し**(ステップ 9 の封印機構)、
      **当該 PR からの書き換えを無条件に fail させる**ことで閉じる。
      **比較元は固定 SHA であり当該 PR から変更できない。**
    - **合格条件の本文が意味として妥当かどうか。** 文字列 "正例 B" の有無しか見ていない。
    """
    errs = []
    steps = data["steps"]
    if len(steps) != data["expected_total"]:
        errs.append(
            "ステップ総数が %d 件(expected_total = %d)" % (len(steps), data["expected_total"])
        )
    ids = [step["id"] for step in steps]
    if ids != list(range(1, len(steps) + 1)):
        errs.append("ステップ番号が 1 からの連番でない")
    check_groups(data, ids, errs)
    pb_false = frozenset(data["pb_false"])
    actual = frozenset(step["id"] for step in steps if not step["requires_positive_b"])
    if actual != pb_false:
        errs.append(
            "pb=false の集合が pb_false と一致しない(余分 %s / 不足 %s)"
            % (sorted(actual - pb_false), sorted(pb_false - actual))
        )
    for step in steps:
        has_text = "正例 B" in step["criteria"]
        if step["requires_positive_b"] and not has_text:
            errs.append("ステップ %d: pb=true だが合格条件に正例 B が無い" % step["id"])
        if not step["requires_positive_b"] and has_text:
            errs.append("ステップ %d: pb=false だが合格条件に正例 B がある" % step["id"])
        try:
            expected = group_of(data, step["id"])
        except KeyError:
            errs.append("ステップ %d がどの群にも属さない" % step["id"])
        else:
            if step["group"] != expected:
                errs.append(
                    "ステップ %d の group=%s が、群範囲から導かれる %s と一致しない"
                    % (step["id"], step["group"], expected)
                )
    check_duplicates(data, errs)
    check_crossrefs(data, errs)
    check_trigger_deadlines(data, errs)
    return errs


def main():
    """コマンドラインから生成・検査を実行する。"""
    data = load()
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "steps":
        print(emit_steps(data))
        return 0
    if mode == "dod":
        print(emit_dod(data))
        return 0
    problems = check(data)
    for line in problems:
        print(line)
    if problems:
        return 1
    true_count = sum(1 for step in data["steps"] if step["requires_positive_b"])
    print(
        "OK: %d ステップ / pb true %d・false %d / 群 %d"
        % (len(data["steps"]), true_count, len(data["pb_false"]), len(data["groups"]))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
