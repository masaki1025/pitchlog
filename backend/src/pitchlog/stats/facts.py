"""native原本の値をコピーし、唯一の生成T5核へ有限射影する。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH

_GENERATED_FACTS_SHA256 = (
    "d39e5caf86a44bd8a52bc9b7cdb61f4707376aac9b797de36530abd5fb3e9e9f"
)


def _generated_module():
    """配置済み共通生成物だけをwrapper名で読み込む。"""
    path = Path(__file__).parent / "generated/facts.py"
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("T5生成物を読み込めません") from exc
    if (
        type(source) is not bytes
        or hashlib.sha256(source).hexdigest() != _GENERATED_FACTS_SHA256
    ):
        raise RuntimeError("T5生成物の固定SHA256が一致しません")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("T5生成物がUTF-8ではありません") from exc
    module = ModuleType("__pitchlog_generated_wrapper__")
    exec(compile(text, str(path), "exec"), module.__dict__)
    if module.__dict__["SOURCE_MODEL_HASH"] != SOURCE_MODEL_HASH:
        raise RuntimeError("T5/typed receiverのモデル版が一致しません")
    return module.__dict__


def _generated_api():
    """旧native入口は同じ検証済みmoduleの確定計算だけを返す。"""
    return _generated_module()["_pitchlog_generated"]


_EVENT_FACTS = _generated_api()


def derive_rates(metrics):
    """同じ生成核のOPS表示率を返す。率の式をこのmoduleへ複製しない。"""
    return _generated_module()["derive_rates"](metrics)


def derive_rates_with_components(metrics):
    """T5の同一評価でOPSと独立状態付きcomponentを返す。"""
    return _generated_module()["derive_rates_with_components"](metrics)


def _native_runner_scores(payload, value):
    """真正artifactの到達と打点判定を写す。不足観測の結果は作らない。"""
    try:
        request = payload["calculation"]["request"]
        t1 = value["t1"]
        flags = t1["statFlags"]
        before = request["t1"]["before"]["stateFields"]
        after = t1["after"]["stateFields"]
        advances = t1["runnerDefaultAdvance"]
        batter = t1["batterDestination"]
        out_effect = t1["outEffect"]
        if (
            out_effect["count"] not in ("0", "1", "2", "3")
            or type(out_effect["targets"]) is not list
        ):
            return None
        if set(advances) != {"first", "second", "third"}:
            return None
        for advance in advances.values():
            if (
                advance["modality"]
                not in ("not-applicable", "hold", "optional", "forced")
                or advance["destination"] not in (None, "1", "2", "3", "4")
                or (
                    advance["modality"] in ("not-applicable", "hold")
                    and advance["destination"] is not None
                )
            ):
                return None
        score_before, score_after = before["state.score"], after["state.score"]
        for score in (score_before, score_after):
            if set(score) != {"home", "away"} or any(
                type(v) is not str or re.fullmatch(r"0|[1-9][0-9]{0,19}", v) is None
                for v in score.values()
            ):
                return None
        # 確定した非生還・非得点結果の空集合であり、欠測の0補完ではない。
        if (
            batter["kind"] in ("continue", "reach", "out")
            and all(a["destination"] != "4" for a in advances.values())
            and all(flags[key] is False for key in ("得点", "打点", "失点"))
            and score_before == score_after
        ):
            return []
        if out_effect != {"count": "0", "targets": []}:
            return None
        if payload["formatVersion"] != "play-prefix-play-v3":
            return None
        observed = payload["observations"]
        chosen = request["t1"]
        # この閉範囲だけはRBI-06/08の既判定を全生還者へ写せる。
        # resultIdは供給範囲を閉じるだけで、打点真偽を計算しない。
        if (
            chosen["resultId"]
            not in (
                "batting-result.single",
                "batting-result.double",
                "batting-result.triple",
                "batting-result.home-run",
            )
            or observed["resultId"] != chosen["resultId"]
            or chosen["officialScoringPayload"] != "no-error"
            or observed["officialScoringPayload"]
            != {"kind": "no-error", "errorCount": "0", "fielders": []}
            or chosen["interferenceRuling"] != "not-required"
            or observed["interferenceRuling"] != {"kind": "not-required"}
            or chosen["thirdOutObservation"] != "none"
            or observed["thirdOutObservation"] != {"kind": "none"}
            or observed["thirdOutTimingByRunner"] != {}
            or flags["失策"] is not False
            or flags["打撃妨害出塁"] is not False
            or flags["走塁妨害出塁"] is not False
        ):
            return None
        source = request["source"]
        runners = source["runners"]
        if type(runners) is not list or len(runners) > 3:
            return None
        by_base = {runner["base"]: runner for runner in runners}
        if len(by_base) != len(runners) or set(by_base) - {"1", "2", "3"}:
            return None
        people = payload["participants"]
        identities = [r["runnerId"] for r in runners]
        if len(set(identities)) != len(runners) or people["batterId"] in identities:
            return None
        observed_overrides = observed["runnerAdvanceOverridesByRunner"]
        if runners:
            if (
                observed_overrides["kind"] != "applied"
                or chosen["runnerAdvanceOverrides"] != observed_overrides
            ):
                return None
            overrides = observed_overrides["overrides"]
            if type(overrides) is not list or len(overrides) != len(runners):
                return None
            selected = {o["runnerBase"]: o["destination"] for o in overrides}
            if len(selected) != len(overrides) or set(selected) != set(by_base):
                return None
            for base, name in (("1", "first"), ("2", "second"), ("3", "third")):
                if base in selected and selected[base] != advances[name]["destination"]:
                    return None
        elif (
            observed_overrides != {"kind": "not-applied", "overrides": []}
            or chosen["runnerAdvanceOverrides"] != "not-applied"
        ):
            return None
        scores = []

        def append_score(runner_id, pitcher_id):
            # 現在投手/打者への欠測ID補完をしない。
            for identity in (runner_id, pitcher_id, people["batterId"]):
                if type(identity) is not str or str(UUID(identity)) != identity:
                    raise ValueError("生還者の原本識別子が不正です")
            scores.append(
                {
                    "runner_id": runner_id,
                    "responsible_pitcher_id": pitcher_id,
                    "valid_run": flags["得点"],
                    "rbi_credited": flags["打点"],
                    "rbi_batter_id": people["batterId"],
                }
            )

        for base, name in (("1", "first"), ("2", "second"), ("3", "third")):
            advance = advances[name]
            if (base in by_base) == (advance["modality"] == "not-applicable"):
                return None
            if advance["destination"] == "4":
                runner = by_base[base]
                append_score(runner["runnerId"], runner["responsiblePitcherId"])
        if batter["kind"] == "score":
            append_score(people["batterId"], people["pitcherId"])
        elif batter["kind"] != "reach":
            return None
        # 人数は到達結果の列挙から。score差は不整合の拒否にのみ使用する。
        if not scores or any(
            flags[key] is not True for key in ("得点", "打点", "失点")
        ):
            return None
        side = {"top": "away", "bottom": "home"}[before["state.half"]]
        other = "home" if side == "away" else "away"
        if (
            score_after[side] != str(int(score_before[side]) + len(scores))
            or score_after[other] != score_before[other]
        ):
            return None
        return scores
    except (KeyError, TypeError, ValueError):
        return None


def native_projection(payload, *, source_event_id):
    """保存原本から既観測だけを写す。戻り値は保存資格/receiptではない。

    Args:
        payload: rootの真正frame/ledger照合を通す対象のV7原本辞書。
        source_event_id: 同TX受理ledgerが供給するevent識別子。

    Returns:
        共通modelの入力射影。欠測fieldを仮値で補完しない。

    Raises:
        ValueError: native variant/閉sourceの外である場合。
    """
    if type(payload) is not dict or type(source_event_id) is not UUID:
        raise ValueError("native sourceの閉入力が必要です")
    variant = payload["formatVersion"]
    if variant not in (
        "first-ball-play-v1",
        "ordinary-pitch-play-v1",
        "play-prefix-play-v2",
        "play-prefix-play-v3",
    ):
        raise ValueError("未対応native sourceです")
    calc = payload["calculation"]
    if calc["response"]["ok"] is not True:
        raise ValueError("native数学の非成功はT5入力になりません")
    value = calc["response"]["value"]
    t1 = value["t1"]
    request_kind = calc["request"]["t1"]["pitchEventKind"]
    if request_kind not in ("pitch-event", "non-pitch-event"):
        raise ValueError("native event区分が未対応です")
    event_kind = {"pitch-event": "pitch", "non-pitch-event": "non_pitch"}[request_kind]
    before = calc["request"]["t1"]["before"]["stateFields"]
    people = payload["participants"]
    # v3のbefore側を使用する。次打者/交代後守備者を今回のcreditに使わない。
    if variant == "play-prefix-play-v3" and value["beforeParticipants"] != people:
        raise ValueError("before参加者の原本が不一致です")
    participants = {
        "actual_pitcher_id": people["pitcherId"],
        "actual_batter_id": people["batterId"],
        "credited_batter_id": people["batterId"],
    }
    pa = {"ended_here": t1["plateAppearanceEnded"]}
    completeness = {
        "participants": "complete",
        "pa": "unavailable",
        "outs": "complete",
        "runs_rbi": "unavailable",
        "steals": "unavailable",
    }
    # 明示された未完PAは欠測ではない。count射影には終了済PAのID/表示を要求しない。
    # PA行生成はこの入口で無効であり、欠測IDやordinalを補うこともない。
    if t1["plateAppearanceEnded"] is False:
        completeness["pa"] = "complete"
    if variant in ("play-prefix-play-v2", "play-prefix-play-v3"):
        native_source = calc["request"]["source"]
        if calc["formatVersion"] == "nonplay-prefix-calculation-v1":
            if (
                variant != "play-prefix-play-v3"
                or native_source.get("formatVersion") != "nonplay-prefix-source-v1"
            ):
                raise ValueError("NP native sourceの閉profile不一致")
            responsibility = native_source["checkpoint"]["content"]["restored"][
                "responsibility"
            ]
        else:
            responsibility = native_source["responsibility"]
        if responsibility["kind"] not in (
            "no-change",
            "changed-mid-plate-appearance",
        ):
            raise ValueError("native責任variantが未対応です")
        if (
            variant == "play-prefix-play-v3"
            and value["responsibility"] != responsibility
        ):
            raise ValueError("今回責任の原本が不一致です")
        pa["pa_id"] = responsibility["paStartSource"]["id"]
        completeness["pa"] = "complete"
        # 打席途中の交代でも今回の実投球者・非四球帰属は今回の参加者に従う。
        # 四球時は唯一artifactが出した打者走者の保存責任IDをそのまま写す。
        walk_owner = people["pitcherId"]
        if (
            responsibility["kind"] == "changed-mid-plate-appearance"
            and t1["statFlags"]["四球"] is True
        ):
            runner_matches = [
                runner
                for runner in value["runners"]
                if runner["runnerId"] == people["batterId"]
            ]
            walk_owner = (
                runner_matches[0]["responsiblePitcherId"]
                if len(runner_matches) == 1
                else None
            )
        participants["walk_pitcher_id"] = walk_owner
        for name in (
            "strikeout_pitcher_id",
            "hbp_pitcher_id",
            "hit_pitcher_id",
            "home_run_pitcher_id",
            "outs_pitcher_id",
        ):
            participants[name] = people["pitcherId"]
    runner_scores = _native_runner_scores(payload, value)
    if runner_scores is not None:
        completeness["runs_rbi"] = "complete"
    projection = {
        "event_kind": event_kind,
        "source": {"lifecycle": "effective", "source_event_id": str(source_event_id)},
        "before": {"inning": before["state.inning"], "half": before["state.half"]},
        "stat_flags": t1["statFlags"],
        "out_effect": {"effective_count": t1["outEffect"]["count"]},
        "pa": pa,
        "participants": participants,
        "completeness": completeness,
    }
    if runner_scores is not None:
        projection["runner_scores"] = runner_scores
    return projection


def evaluate_native_projection(payload, *, source_event_id):
    """全27群を同じ生成核で評価する。認可/保存成功は発行しない。"""
    projection = native_projection(payload, source_event_id=source_event_id)
    # PA表示のordinal/語彙等を仮生成せず、count/creditだけを有限射影する。
    return _EVENT_FACTS(projection, METRIC_IDS)


def evaluate_closed_projection(projection, *, requested_metrics):
    """正式providerが閉じた他variantも同じ生成入口へ渡す。"""
    return _EVENT_FACTS(projection, requested_metrics)


@dataclass(frozen=True, slots=True)
class SavePrimitiveSourceToken(TenantOperationToken):
    """rootの実同TX frame資格と評価bindingを要する保存命令。"""

    attempt_id: UUID
    phase_id: UUID
    source_event_id: UUID
    model_sha256: str
    expected_revision: int
    expected_source_set_sha256: str | None
    evaluation_json: str

    @property
    def capability_id(self):
        """呼出者のboolを資格とせず固定能力を宣言する。"""
        return "CAP:stats_primitives:save_source"


def prepare_native_evaluation(
    payload,
    *,
    attempt_id,
    phase_id,
    source_event_id,
    expected_revision,
    expected_source_set_sha256,
):
    """同frame hookが渡す評価を閉tokenへ写す。token自身は保存権限ではない。

    rootのtransaction/登録関数が既消費frame/ledger/play/checkpointと評価を
    同TXで独立照合するまで、自由UUID/JSONは受理済みreceiptにならない。
    """
    if any(type(x) is not UUID for x in (attempt_id, phase_id, source_event_id)):
        raise ValueError("同frame識別子の型が不正です")
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("期待系列revisionの型が不正です")
    if expected_revision == 0:
        if expected_source_set_sha256 is not None:
            raise ValueError("初回系列の期待Sが不正です")
    elif (
        type(expected_source_set_sha256) is not str
        or re.fullmatch(r"[a-f0-9]{64}", expected_source_set_sha256) is None
    ):
        raise ValueError("期待系列Sの型が不正です")
    evaluation = evaluate_native_projection(payload, source_event_id=source_event_id)
    return SavePrimitiveSourceToken(
        attempt_id,
        phase_id,
        source_event_id,
        SOURCE_MODEL_HASH,
        expected_revision,
        expected_source_set_sha256,
        json.dumps(
            evaluation,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    )
