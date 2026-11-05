"""実source集約不足や自己申告でbridge/責任資格を発行しない。"""

import copy

import pytest

from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.repositories.play_prefix import (
    _require_legacy_compatibility,
    _verify_source_evidence,
)


def evidence():
    """全3play/履歴3の仮原本。真正DB証拠ではない。"""
    return {
        "content": {"prefix_ref": {"length": "3"}, "history_depth": "3"},
        "source_evidence": {
            "all_play_count": 3,
            "ordinary_play_count": 3,
            "invalid_count": 0,
            "non_play_count": 0,
            "history_count": 3,
            "pa_change_count": 0,
        },
    }


def test_exact_real_aggregate_needed_for_bridge_and_no_change():
    """ordinary長を全play長へ無言で読み替えず、PA交代を拒否する。"""
    row = evidence()
    _verify_source_evidence(row, bridge=True)
    for field in row["source_evidence"]:
        changed = copy.deepcopy(row)
        changed["source_evidence"][field] += 1
        with pytest.raises(OrdinaryPrefixError):
            _verify_source_evidence(changed, bridge=True)
    with pytest.raises(OrdinaryPrefixError):
        _verify_source_evidence({"content": row["content"]}, bridge=True)
    with pytest.raises(OrdinaryPrefixError):
        _require_legacy_compatibility("0" * 64, "1" * 64)


def _lineup_initial_from_fixture():
    """公開名簿の実ABIを使う試験入力。DB/開始資格を模擬発行しない。"""
    import json
    from datetime import UTC, datetime
    from pathlib import Path
    from types import SimpleNamespace
    from uuid import UUID

    from pitchlog.domainrt.first_pitch import StateSnapshot
    from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection

    root = Path(__file__).resolve().parents[2]
    cases = json.loads(
        (
            root / "contracts/state-transition/lineup_play_prefix_cases_v1.json"
        ).read_text()
    )["cases"]
    first = next(c for c in cases if c["caseId"] == "V3-STARTED-CHAIN-01")["request"]
    raw = {"dh": True}
    for side, team in first["source"]["lineup"].items():
        raw[side] = {
            "team_id": team["teamId"],
            "entries": [
                {
                    "player_id": team["pitcherId"],
                    "batting_order": None,
                    "fielding_position": {"kind": "fielding", "position": "1"},
                },
                *[
                    {
                        "player_id": player,
                        "batting_order": slot,
                        "fielding_position": {"kind": "designated-hitter"}
                        if slot == "1"
                        else {"kind": "fielding", "position": slot},
                    }
                    for slot, player in team["battingOrder"].items()
                ],
            ],
        }
    with open_domain_host() as host:
        roster = json.loads(host.call("validateInitialGameRoster", json.dumps(raw)))
    assert roster["ok"] is True
    snapshot = copy.deepcopy(first["t1"]["before"])
    del snapshot["battingOrderBySide"]
    return SimpleNamespace(
        tenant_id=UUID(first["prefixRef"]["tenantId"]),
        game_id=UUID(first["prefixRef"]["gameId"]),
        generation=1,
        started_at=datetime(2026, 10, 31, tzinfo=UTC),
        roster=InitialRosterProjection.model_validate_json(json.dumps(roster["value"])),
        before=StateSnapshot.model_validate_json(json.dumps(snapshot)),
        rules=SavedRuleWire.model_validate_json(json.dumps(first["rules"])),
    ), cases


def test_lineup_zero_origin_ref_does_not_alias_game_or_private_digest():
    """zeroは成功開始UUID/rev1/history0。wire/full content/物理epochを区別する。"""
    from uuid import UUID

    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.lineup_play_prefix_continuation import SourcePosition
    from pitchlog.repositories.play_prefix import (
        _initial_lineup_document,
        read_lineup_prefix_document,
    )

    initial, _ = _lineup_initial_from_fixture()
    origin = str(UUID(int=9001))
    position = SourcePosition(d1="1", d2="1", appliedWatermark="0")
    with open_domain_host() as host:
        doc, source = _initial_lineup_document(
            initial, origin, "test-d4", 1, host.artifact_sha256, position
        )
    assert doc.prefix_ref.checkpoint.id == origin != str(initial.game_id)
    assert doc.prefix_ref.checkpoint.revision == "1"
    assert doc.prefix_ref.history_version == "0"
    assert doc.history_version == "1"
    assert doc.prefix_ref.checkpoint.digest != doc.content_digest
    assert doc.last_source is None and source.position == position
    assert (
        read_lineup_prefix_document(
            doc.model_dump_json(by_alias=True, exclude_unset=True)
        )
        == doc
    )
    raw = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    for key, value in [
        ("history_version", "2"),
        ("content_digest", "0" * 64),
        ("version", "2"),
        ("projection_snapshot", {}),
    ]:
        bad = copy.deepcopy(raw)
        bad[key] = value
        with pytest.raises(OrdinaryPrefixError):
            read_lineup_prefix_document(_canonical_json(bad))


def test_native_outer_identity_revision_epoch_digest_and_state_before_ready():
    """実外側列の欠落/型/値変更を後段SQLまで持ち越さない。DB資格試験ではない。"""
    from uuid import UUID

    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.lineup_play_prefix_continuation import SourcePosition
    from pitchlog.repositories.play_prefix import (
        _check_native_lineup_row,
        _initial_lineup_document,
    )

    initial, _ = _lineup_initial_from_fixture()
    with open_domain_host() as host:
        doc, _ = _initial_lineup_document(
            initial,
            str(UUID(int=9001)),
            "test-d4",
            1,
            host.artifact_sha256,
            SourcePosition(d1="1", d2="1", appliedWatermark="0"),
        )
    row = {
        "tenant_id": str(initial.tenant_id),
        "game_id": str(initial.game_id),
        "internal_generation": initial.generation,
        "id": doc.id,
        "revision": int(doc.revision),
        "history_version": int(doc.history_version),
        "recovery_generation": 1,
        "confirmed_watermark": 0,
        "applied_watermark": 0,
        "content_digest": doc.content_digest,
        "state": "current",
        "saved_at": "2026-10-31T00:00:00Z",
    }
    arguments = {
        "tenant": initial.tenant_id,
        "game": initial.game_id,
        "generation": initial.generation,
        "epoch": 1,
        "watermark": 0,
    }
    _check_native_lineup_row(row, doc, **arguments)
    for field in row:
        for member in (None, True, "unknown", -1):
            changed = copy.deepcopy(row)
            changed[field] = member
            if field == "saved_at" and member is not None:
                continue
            with pytest.raises(OrdinaryPrefixError):
                _check_native_lineup_row(changed, doc, **arguments)
        changed = copy.deepcopy(row)
        del changed[field]
        with pytest.raises(OrdinaryPrefixError):
            _check_native_lineup_row(changed, doc, **arguments)


# witnessはreaderの動作変更ではなく、採用する有限2行の検証証拠である。
_CURRENT_IDENTITY_PROBE = r"""
const fs = require("fs"),
  vm = require("vm"),
  crypto = require("crypto"),
  assert = require("assert");
const root = process.argv[1],
  cache = process.argv[2];
const read = (p) =>
  JSON.parse(fs.readFileSync(root + "/" + p, "utf8"));
const hash = (b) =>
  crypto.createHash("sha256").update(b).digest("hex");
const load = (p) => {
  const raw = fs.readFileSync(p);
  const c = vm.createContext({});
  new vm.Script(raw.toString()).runInContext(c);
  return { api: c.PitchlogDomain, sha: hash(raw) };
};
const candidate = load(
    root + "/frontend/public/domain/pitchlog-domain.js",
  ),
  trusted = load(cache + "/prior-0755.js");
const table = JSON.parse(
  fs.readFileSync(cache + "/before-compat.json", "utf8"),
);
const first = read(
  "contracts/state-transition/t2_first_pitch_continuation_cases_v1.json",
).cases;
const ordinaryDoc = read(
  "contracts/state-transition/ordinary_pitch_vectors_v1.json",
);
const ordinary = ordinaryDoc.cases;
const continuation = read(
  "contracts/state-transition/ordinary37_continuation_candidate_v1.json",
).cases;
const general = [
  ...read(
    "contracts/state-transition/recording_continuation_scope_v1.json",
  ).generalStateCases,
  ...read(
    "contracts/state-transition/ordinary_two_strike_foul_candidate_v1.json",
  ).generalStateCases,
];
const firstInputs = first.flatMap((r) => [
  { id: r.caseId, operation: "deriveState", request: r.request.t1 },
  {
    id: r.caseId,
    operation: "deriveFirstPitchWithContinuation",
    request: r.request,
  },
]);
const ordinaryInputs = [
  ...firstInputs,
  ...ordinary.map((r) => ({
    id: r.caseId,
    operation: "deriveOrdinaryPitch",
    request: r.request,
  })),
  ...continuation.map((r) => ({
    id: r.caseId,
    operation: "deriveOrdinaryPitchWithContinuation",
    request: r.request,
  })),
  ...general.map((r) => {
    const q = structuredClone(continuation[2].request);
    q.t1 = {
      ...structuredClone(r.event),
      before: structuredClone(r.before),
    };
    q.prior.after = structuredClone(r.before);
    return {
      id: r.caseId,
      operation: "deriveOrdinaryPitchWithContinuation",
      request: q,
    };
  }),
];
ordinaryInputs.push(
  ...ordinaryDoc.historyTailCases.map((r) => ({
    id: r.caseId,
    operation: "deriveOrdinaryPitch",
    request: r.second.request,
  })),
  ...general.map((r) => ({
    id: r.caseId,
    operation: "deriveOrdinaryPitch",
    request: {
      ...structuredClone(r.event),
      before: structuredClone(r.before),
      history: { stack: [] },
    },
  })),
);

const canonical = (v) => JSON.stringify(v);
const digest = (v) => hash(canonical(v));
const sources = [
  "t2_first_pitch_continuation_cases_v1.json",
  "ordinary_pitch_vectors_v1.json",
  "ordinary37_continuation_candidate_v1.json",
  "recording_continuation_scope_v1.json",
  "ordinary_two_strike_foul_candidate_v1.json",
  "batted_hit_prefix_cases_v1.json",
].map((f) => ({
  path: "contracts/state-transition/" + f,
  sha256: hash(
    fs.readFileSync(root + "/contracts/state-transition/" + f),
  ),
}));
const groups = [],
  full = [];
for (const sourceFormat of [
  "first-ball-play-v1",
  "ordinary-pitch-play-v1",
]) {
  const records = [];
  const inputs =
    sourceFormat === "first-ball-play-v1"
      ? firstInputs
      : ordinaryInputs;
  for (const t of inputs) {
    const a = JSON.parse(
        trusted.api[t.operation](canonical(t.request)),
      ),
      b = JSON.parse(
        candidate.api[t.operation](canonical(t.request)),
      );
    assert.deepStrictEqual(b, a);
    records.push({
      caseId: t.id,
      operation: t.operation,
      requestSha256: digest(t.request),
      comparisonOutputSha256: digest(a),
      executionOutputSha256: digest(b),
    });
    full.push({
      sourceFormat,
      ...t,
      comparisonOutput: a,
      executionOutput: b,
    });
  }
  groups.push({
    sourceFormat,
    compatibleOperations:
      sourceFormat === "first-ball-play-v1"
        ? ["deriveState", "deriveFirstPitchWithContinuation"]
        : [
            "deriveState",
            "deriveFirstPitchWithContinuation",
            "deriveOrdinaryPitch",
            "deriveOrdinaryPitchWithContinuation",
          ],
    caseCount: records.length,
    records,
  });
}
const normative = [];
const check = (path, rows, operation, expected) => {
  for (const r of rows) {
    const actual = JSON.parse(
      candidate.api[operation](canonical(r.request)),
    );
    assert.deepStrictEqual(actual, expected(r));
    normative.push({
      sourcePath: path,
      caseId: r.caseId,
      operation,
      requestSha256: digest(r.request),
      expectedSha256: digest(expected(r)),
      executionOutputSha256: digest(actual),
    });
  }
};
check(
  sources[0].path,
  first,
  "deriveFirstPitchWithContinuation",
  (r) => r.expected,
);
check(
  sources[1].path,
  ordinary,
  "deriveOrdinaryPitch",
  (r) => r.expected,
);
check(
  sources[2].path,
  continuation,
  "deriveOrdinaryPitchWithContinuation",
  (r) => r.expected.response,
);
const batted = read(sources[5].path).cases;
check(
  sources[5].path,
  batted,
  "deriveLineupPlayPrefixWithContinuation",
  (r) => r.expected,
);
const c = batted.find((r) => r.caseId === "BHP-HR-D01-B");
const prior = JSON.parse(
    trusted.api.deriveLineupPlayPrefixWithContinuation(
      canonical(c.request),
    ),
  ),
  current = JSON.parse(
    candidate.api.deriveLineupPlayPrefixWithContinuation(
      canonical(c.request),
    ),
  );
assert.deepStrictEqual(prior, {
  ok: false,
  error: { code: "INVALID_REQUEST" },
});
assert.deepStrictEqual(current, c.expected);
assert.equal(current.value.t2.decision.outcome, "walk-off");
const metadata = JSON.parse(
  fs.readFileSync(cache + "/origin.json", "utf8"),
);
const witness = {
  version: "1",
  kind: "current-artifact-identity-with-independent-git-and-normative-witness",
  ...metadata,
  comparisonArtifactSha256: trusted.sha,
  executionArtifactSha256: candidate.sha,
  oldRegistryCaseCount: table.cases.length,
  oldRegistryCasesSha256: digest(table.cases),
  sources,
  groups,
  normative,
  d01: {
    sourcePath: sources[5].path,
    caseId: c.caseId,
    operation: "deriveLineupPlayPrefixWithContinuation",
    request: c.request,
    comparisonOutput: prior,
    executionOutput: current,
    normativeExpected: c.expected,
    priorPublicAbiRejected: true,
    noLegacyToCurrentCompatibilityClaim: true,
  },
  scope: {
    onlyCurrentToCurrent: true,
    legacyToCurrentRowsAdded: 0,
    HTTPorDB: false,
    P6Blind: false,
  },
};
fs.writeFileSync(
  cache + "/computed-witness.json",
  JSON.stringify(witness, null, 2) + "\n",
);
console.log(
  JSON.stringify({
    groups: groups.map((x) => [x.sourceFormat, x.caseCount]),
    normative: normative.length,
    d01: current.value.t2.decision.outcome,
  }),
);
"""


def _current_identity_materials(root, directory):
    """旧Git実体と現artifactを分け、期待は規範原典から独立に読む。"""
    import hashlib
    import json
    import subprocess

    base = root / "contracts/state-transition"
    witness_bytes = (base / "batted_current_identity_witness_v1.json").read_bytes()
    witness = json.loads(witness_bytes)
    old_revision = witness["oldRegistryRevision"]
    comparison_revision = witness["comparisonArtifactRevision"]
    for revision in (old_revision, comparison_revision):
        assert len(revision) == 40
        assert all(x in "0123456789abcdef" for x in revision)
        subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", revision, "HEAD"],
            check=True,
            capture_output=True,
        )

    def git_bytes(revision, path):
        return subprocess.check_output(
            ["git", "-C", str(root), "show", revision + ":" + path], timeout=30
        )

    old_bytes = git_bytes(
        old_revision,
        "contracts/state-transition/play_prefix_v2_source_compatibility_v1.json",
    )
    old = json.loads(old_bytes)
    assert len(old["cases"]) == 55
    registry_raw = (base / "play_prefix_v2_source_compatibility_v1.json").read_bytes()
    assert registry_raw.startswith(old_bytes.rsplit(b"\n  ]", 1)[0] + b",")
    registry = json.loads(registry_raw)
    assert registry["cases"][:55] == old["cases"]
    assert len(registry["cases"]) == 57
    assert set(registry) == set(old)
    assert all(registry[k] == old[k] for k in old if k != "cases")
    prior = git_bytes(comparison_revision, "frontend/public/domain/pitchlog-domain.js")
    assert hashlib.sha256(prior).hexdigest() == old["cases"][-1]["priorArtifactSha256"]
    (directory / "prior-0755.js").write_bytes(prior)
    (directory / "before-compat.json").write_bytes(old_bytes)
    (directory / "origin.json").write_text(
        json.dumps(
            {
                "comparisonArtifactRevision": comparison_revision,
                "oldRegistryRevision": old_revision,
            }
        )
    )
    return witness_bytes, witness, registry


def _assert_current_identity_rows(witness_bytes, witness, registry, artifact_bytes):
    """未知SHA・形式・不足操作・別witnessを有限登録の証拠として拒む。"""
    import hashlib

    digest = hashlib.sha256(artifact_bytes).hexdigest()
    assert witness["executionArtifactSha256"] == digest
    formats = ["first-ball-play-v1", "ordinary-pitch-play-v1"]
    operations = ["deriveState", "deriveFirstPitchWithContinuation"]
    expected_rows = []
    for index, source_format in enumerate(formats):
        declared = (
            operations
            if index == 0
            else operations
            + ["deriveOrdinaryPitch", "deriveOrdinaryPitchWithContinuation"]
        )
        expected_rows.append(
            {
                "priorArtifactSha256": digest,
                "executionArtifactSha256": digest,
                "sourceFormat": source_format,
                "compatibleOperations": declared,
                "witnessSha256": hashlib.sha256(witness_bytes).hexdigest(),
            }
        )
    assert registry["cases"][55:] == expected_rows
    assert witness["scope"] == {
        "onlyCurrentToCurrent": True,
        "legacyToCurrentRowsAdded": 0,
        "HTTPorDB": False,
        "P6Blind": False,
    }


def test_current_identity_has_actual_git_full_response_and_normative_witness(tmp_path):
    """1878旧新全応答と84規範、D01実差でself2だけを独立に裏付ける。"""
    import json
    import shutil
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    witness_bytes, witness, registry = _current_identity_materials(root, tmp_path)
    artifact = (root / "frontend/public/domain/pitchlog-domain.js").read_bytes()
    _assert_current_identity_rows(witness_bytes, witness, registry, artifact)
    subprocess.run(
        [
            shutil.which("node") or "node",
            "-e",
            _CURRENT_IDENTITY_PROBE,
            str(root),
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    measured = json.loads((tmp_path / "computed-witness.json").read_bytes())
    assert measured == witness
    assert [g["caseCount"] for g in witness["groups"]] == [24, 1854]
    assert len(witness["normative"]) == 84
    assert witness["d01"]["comparisonOutput"] == {
        "ok": False,
        "error": {"code": "INVALID_REQUEST"},
    }
    assert witness["d01"]["executionOutput"] == witness["d01"]["normativeExpected"]
    assert (
        witness["d01"]["executionOutput"]["value"]["t2"]["decision"]["outcome"]
        == "walk-off"
    )
    for row in registry["cases"][55:]:
        _require_legacy_compatibility(
            row["priorArtifactSha256"],
            row["executionArtifactSha256"],
            source_format=row["sourceFormat"],
        )
    # この修復で旧→現互換を暗黙に認めていないことを実readerで確認する。
    for source_format in ("first-ball-play-v1", "ordinary-pitch-play-v1", "unknown"):
        with pytest.raises(OrdinaryPrefixError):
            _require_legacy_compatibility(
                witness["comparisonArtifactSha256"],
                witness["executionArtifactSha256"],
                source_format=source_format,
            )
    with pytest.raises(OrdinaryPrefixError):
        _require_legacy_compatibility(
            witness["executionArtifactSha256"],
            witness["executionArtifactSha256"],
            source_format="unknown",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-prior",
        "unknown-execution",
        "unknown-format",
        "missing-operation",
        "extra-operation",
        "wrong-witness",
        "changed-witness-bytes",
        "extra-row",
    ],
)
def test_current_identity_registration_proof_rejects_changed_material(mutation):
    """証拠整合の拒否であり、既readerにwitnessファイル検査を追加したとはしない。"""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    base = root / "contracts/state-transition"
    raw = (base / "batted_current_identity_witness_v1.json").read_bytes()
    witness = json.loads(raw)
    registry_raw = (base / "play_prefix_v2_source_compatibility_v1.json").read_bytes()
    registry = json.loads(registry_raw)
    row = registry["cases"][-1]
    if mutation == "unknown-prior":
        row["priorArtifactSha256"] = "0" * 64
    elif mutation == "unknown-execution":
        row["executionArtifactSha256"] = "0" * 64
    elif mutation == "unknown-format":
        row["sourceFormat"] = "unknown"
    elif mutation == "missing-operation":
        row["compatibleOperations"].pop()
    elif mutation == "extra-operation":
        row["compatibleOperations"].append("unknown")
    elif mutation == "wrong-witness":
        row["witnessSha256"] = "0" * 64
    elif mutation == "changed-witness-bytes":
        raw += b" "
    elif mutation == "extra-row":
        registry["cases"].append(copy.deepcopy(row))
    with pytest.raises(AssertionError):
        _assert_current_identity_rows(
            raw,
            witness,
            registry,
            (root / "frontend/public/domain/pitchlog-domain.js").read_bytes(),
        )
