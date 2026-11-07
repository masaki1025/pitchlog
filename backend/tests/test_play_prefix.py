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

    current_root = Path(__file__).resolve().parents[2]
    root = _historical_v3_context(current_root, tmp_path / "historical")
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
def test_current_identity_registration_proof_rejects_changed_material(
    mutation, tmp_path
):
    """証拠整合の拒否であり、既readerにwitnessファイル検査を追加したとはしない。"""
    import json
    from pathlib import Path

    current_root = Path(__file__).resolve().parents[2]
    root = _historical_v3_context(current_root, tmp_path / "historical")
    base = root / "contracts/state-transition"
    raw = (base / "batted_current_identity_witness_v1.json").read_bytes()
    witness = json.loads(raw)
    registry_raw = (base / "play_prefix_v2_source_compatibility_v1.json").read_bytes()
    registry = json.loads(registry_raw)
    _assert_current_identity_rows(
        raw,
        witness,
        registry,
        (root / "frontend/public/domain/pitchlog-domain.js").read_bytes(),
    )
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


def _historical_v3_context(root, destination):
    """旧57/51dを真正Git commitの物理checkoutで検査し、現在値へ書き換えない。"""
    import json
    import re
    import subprocess

    witness = json.loads(
        (
            root / "contracts/state-transition/nonplay_v3_compatibility_witness_v1.json"
        ).read_bytes()
    )
    revision = witness["historicalContext"]["revision"]
    assert type(revision) is str and re.fullmatch(r"[a-f0-9]{40}", revision)
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            "--no-checkout",
            str(root),
            str(destination),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--quiet", "--detach", revision],
        check=True,
        capture_output=True,
        timeout=30,
    )
    assert (
        subprocess.check_output(
            ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True
        ).strip()
        == revision
    )
    return destination


def _v3_compatibility_root(tmp_path):
    """旧v1実checker用の固定asset全組を物理copyする。"""
    import hashlib
    import json
    import shutil
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    paths = [
        "contracts/state-transition/play_prefix_v2_source_compatibility_v1.json",
        "contracts/state-transition/nonplay_v3_compatibility_witness_v1.json",
        "contracts/state-transition/batted_current_identity_witness_v1.json",
        "frontend/public/domain/pitchlog-domain.js",
        "frontend/public/domain/pitchlog-domain.json",
    ]
    for name in paths:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if name.startswith("frontend/public/domain/"):
            v2 = json.loads(
                (
                    root
                    / "contracts/state-transition"
                    / "nonplay_v3_compatibility_witness_v2.json"
                ).read_bytes()
            )
            revision = v2["historicalArtifactCommit"]
            assert revision == "177de16a31df723c69595bc659839f46b3fc71ac"
            raw = subprocess.check_output(
                ["git", "show", f"{revision}:{name}"], cwd=root
            )
            if name.endswith(".js"):
                assert hashlib.sha256(raw).hexdigest() == v2["historicalArtifactSha256"]
            dest.write_bytes(raw)
        else:
            shutil.copyfile(root / name, dest)
    module = tmp_path / "backend/src/pitchlog/repositories/play_prefix.py"
    module.parent.mkdir(parents=True)
    module.write_text("# test-only root, no implementation stub\n")
    return tmp_path, module


def test_real_v3_fixed_witness_two_pairs_and_full_normative_vm(tmp_path, monkeypatch):
    """旧53規範と現自己の実VM全応答、正規化だけの期待、真のgate成立を確認する。"""
    import hashlib
    import json
    import subprocess
    from pathlib import Path

    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixRequest,
        LineupPrefixSuccess,
        decode_lineup_prefix_response,
        lineup_wire_digest,
        verify_lineup_wire_seal,
    )

    root = Path(__file__).resolve().parents[2]
    base = root / "contracts/state-transition"
    v1_root, v1_module = _v3_compatibility_root(tmp_path / "v1-execution")
    witness = json.loads(
        (base / "nonplay_v3_compatibility_witness_v1.json").read_bytes()
    )
    historical = _historical_v3_context(root, tmp_path / "historical")
    for source in witness["normativeSources"]:
        raw = (historical / source["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source["sha256"]
        original = json.loads(raw)["cases"]
        selected = [s for s in witness["samples"] if s["sourcePath"] == source["path"]]
        assert len(original) == len(selected) == source["caseCount"]
        for case, sample in zip(original, selected, strict=True):
            assert sample["caseId"] == case["caseId"]
            assert _canonical_json(sample["originalRequest"]) == _canonical_json(
                case["request"]
            )
            assert _canonical_json(sample["oldExpected"]) == _canonical_json(
                case["expected"]
            )
            current_request = copy.deepcopy(case["request"])
            current_expected = copy.deepcopy(case["expected"])
            current_request["source"]["executionArtifactSha256"] = witness[
                "executionArtifactSha256"
            ]
            current_expected["value"]["executionArtifactSha256"] = witness[
                "executionArtifactSha256"
            ]
            decoded_expected = decode_lineup_prefix_response(
                _canonical_json(current_expected)
            )
            assert type(decoded_expected) is LineupPrefixSuccess
            digest = lineup_wire_digest(
                LineupPrefixRequest.model_validate_json(
                    _canonical_json(current_request), by_alias=True, by_name=False
                ),
                decoded_expected,
            )
            current_request["nextCheckpoint"]["digest"] = digest
            current_expected["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
            assert _canonical_json(current_request) == _canonical_json(
                sample["currentRequest"]
            )
            assert _canonical_json(current_expected) == _canonical_json(
                sample["currentExpected"]
            )
            sealed_expected = decode_lineup_prefix_response(
                _canonical_json(current_expected)
            )
            assert type(sealed_expected) is LineupPrefixSuccess
            verify_lineup_wire_seal(
                LineupPrefixRequest.model_validate_json(
                    _canonical_json(current_request), by_alias=True, by_name=False
                ),
                sealed_expected,
            )
    data = tmp_path / "vm-input.json"
    data.write_text(
        json.dumps(
            {
                "oldArtifact": str(
                    historical / "frontend/public/domain/pitchlog-domain.js"
                ),
                "currentArtifact": str(
                    v1_root / "frontend/public/domain/pitchlog-domain.js"
                ),
                "samples": witness["samples"],
            }
        )
    )
    script = r"""
const fs=require('fs'),vm=require('vm');
const p=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
function load(path){
  const c=vm.createContext({});
  new vm.Script(fs.readFileSync(path,'utf8')).runInContext(c);
  return c.PitchlogDomain;
}
const old=load(p.oldArtifact),now=load(p.currentArtifact),self=load(p.currentArtifact);
process.stdout.write(JSON.stringify(p.samples.map(s=>({oldActual:JSON.parse(old.deriveLineupPlayPrefixWithContinuation(JSON.stringify(s.originalRequest))),currentActual:JSON.parse(now.deriveLineupPlayPrefixWithContinuation(JSON.stringify(s.currentRequest))),selfActual:JSON.parse(self.deriveLineupPlayPrefixWithContinuation(JSON.stringify(s.currentRequest)))}))));
"""
    measured = json.loads(
        subprocess.check_output(["node", "-e", script, str(data)], timeout=60)
    )
    assert len(measured) == 53
    for sample, result in zip(witness["samples"], measured, strict=True):
        for name in ("oldActual", "currentActual", "selfActual"):
            assert _canonical_json(result[name]) == _canonical_json(sample[name]), (
                sample["caseId"]
            )
    for prior in witness["priorArtifacts"]:
        from pitchlog.repositories import play_prefix as reader

        monkeypatch.setattr(reader, "__file__", str(v1_module))
        _require_legacy_compatibility(
            prior,
            witness["executionArtifactSha256"],
            source_format="play-prefix-play-v3",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "unknown-prior",
        "unknown-execution",
        "old4f-not-declared",
        "unknown-format",
        "missing-row",
        "extra-row",
        "duplicate-row",
        "changed-order",
        "missing-operation",
        "extra-operation",
        "wrong-witness",
        "missing-witness",
        "changed-witness-bytes",
        "changed-format-follow-hash",
        "changed-math-follow-hash",
        "unknown-pair-follow-hash",
        "scope-bool-int-follow-hash",
        "changed-old-row-follow-hash",
        "wrong-source-format-follow-hash",
        "metadata-follow-hash",
        "join-input-mismatch-follow-hash",
    ],
)
def test_v3_real_runtime_gate_uses_fixed_bytes_and_closed_metadata(
    tmp_path, monkeypatch, mutation
):
    """正常baseline成立後に実checkerへ変異し、hash追随でも閉条件を崩さない。"""
    import hashlib
    import json

    from pitchlog.repositories import play_prefix as reader

    root, module = _v3_compatibility_root(tmp_path)
    monkeypatch.setattr(reader, "__file__", str(module))
    base = root / "contracts/state-transition"
    path = base / "play_prefix_v2_source_compatibility_v1.json"
    witness_path = base / "nonplay_v3_compatibility_witness_v1.json"
    data = json.loads(path.read_bytes())
    w = json.loads(witness_path.read_bytes())
    prior = w["priorArtifacts"][0]
    execution = w["executionArtifactSha256"]
    for permitted in w["priorArtifacts"]:
        reader._require_legacy_compatibility(
            permitted, execution, source_format="play-prefix-play-v3"
        )
    if mutation == "none":
        return
    rows = data["cases"]
    row = rows[-2]
    fmt = "play-prefix-play-v3"
    if mutation == "unknown-prior":
        prior = "0" * 64
    elif mutation == "unknown-execution":
        execution = "0" * 64
    elif mutation == "old4f-not-declared":
        # 未統合4fは運用保存/互換宣言としない。既手例の参照からだけ取得する。
        from pathlib import Path

        contract = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "contracts/state-transition/nonplay_prefix_bridge_cases_v1.json"
            ).read_bytes()
        )
        prior = contract["steps"][0]["source"]["checkpoint"]["content"][
            "executionArtifactSha256"
        ]
    elif mutation == "unknown-format":
        fmt = "unknown"
    elif mutation == "missing-row":
        rows.pop(-2)
    elif mutation == "extra-row":
        rows.append({**row, "priorArtifactSha256": "0" * 64})
    elif mutation == "duplicate-row":
        rows.append(copy.deepcopy(row))
    elif mutation == "changed-order":
        rows[-2:] = reversed(rows[-2:])
    elif mutation == "missing-operation":
        row["compatibleOperations"] = []
    elif mutation == "extra-operation":
        row["compatibleOperations"].append("applyUndo")
    elif mutation == "wrong-witness":
        row["witnessSha256"] = "0" * 64
    elif mutation == "missing-witness":
        witness_path.unlink()
    elif mutation == "changed-witness-bytes":
        witness_path.write_bytes(witness_path.read_bytes() + b" ")
    else:
        if mutation == "changed-math-follow-hash":
            w["samples"][0]["currentActual"]["value"]["t1"]["after"]["stateFields"][
                "state.outs"
            ] = "2"
        elif mutation == "unknown-pair-follow-hash":
            w["priorArtifacts"][0] = "0" * 64
            row["priorArtifactSha256"] = "0" * 64
            prior = "0" * 64
        elif mutation == "scope-bool-int-follow-hash":
            w["scope"]["HTTPorDB"] = 0
        elif mutation == "changed-old-row-follow-hash":
            rows[0]["compatibleOperations"] = []
        elif mutation == "wrong-source-format-follow-hash":
            w["sourceFormat"] = "ordinary-pitch-play-v1"
        elif mutation == "join-input-mismatch-follow-hash":
            w["fourOperationJoinEvidence"]["rawInputSha256"] = "0" * 64
        elif mutation != "changed-format-follow-hash":
            w["normalization"]["requestPointers"].append("/source/after")
        new = (json.dumps(w, ensure_ascii=False, indent=2) + "\n").encode()
        if mutation == "changed-format-follow-hash":
            new += b" "
        witness_path.write_bytes(new)
        for declared in rows[57:]:
            declared["witnessSha256"] = hashlib.sha256(new).hexdigest()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    with pytest.raises(OrdinaryPrefixError):
        reader._require_legacy_compatibility(prior, execution, source_format=fmt)


def test_four_operation_join_declares_only_measured_pairs_and_groups(tmp_path):
    """初版v3根拠を保持し、別1878群の正確self/旧51d joinだけを確認する。"""
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    base = root / "contracts/state-transition"
    raw = (base / "nonplay_v3_compatibility_witness_v1.json").read_bytes()
    w = json.loads(raw)
    registry = json.loads(
        (base / "play_prefix_v2_source_compatibility_v1.json").read_bytes()
    )
    join = w["fourOperationJoinEvidence"]
    assert join["comparisonArtifactSha256"] == w["priorArtifacts"][0]
    assert join["executionArtifactSha256"] == w["executionArtifactSha256"]
    assert join["fullCaseCount"] == 1878 and join["normalizationPointers"] == []
    assert [g["caseCount"] for g in join["groups"]] == [24, 1854]
    for g in join["groups"]:
        assert (
            g["priorFullResponsesSha256"]
            == g["currentFullResponsesSha256"]
            == g["selfFullResponsesSha256"]
        )
    operations = ["deriveState", "deriveFirstPitchWithContinuation"]
    expected = []
    for prior in (w["executionArtifactSha256"], w["priorArtifacts"][0]):
        for fmt, ops in [
            ("first-ball-play-v1", operations),
            (
                "ordinary-pitch-play-v1",
                operations
                + ["deriveOrdinaryPitch", "deriveOrdinaryPitchWithContinuation"],
            ),
        ]:
            expected.append(
                {
                    "priorArtifactSha256": prior,
                    "executionArtifactSha256": w["executionArtifactSha256"],
                    "sourceFormat": fmt,
                    "compatibleOperations": ops,
                    "witnessSha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    assert registry["cases"][59:] == expected
    assert len(registry["cases"]) == 63
    for row in expected:
        prior = row["priorArtifactSha256"]
        execution = row["executionArtifactSha256"]
        fmt = row["sourceFormat"]
        assert type(prior) is str and type(execution) is str and type(fmt) is str
        _require_legacy_compatibility(prior, execution, source_format=fmt)


@pytest.mark.parametrize("fmt", ["first-ball-play-v1", "ordinary-pitch-play-v1"])
@pytest.mark.parametrize("prior_kind", ["current", "legacy"])
@pytest.mark.parametrize(
    "fault", ["missing-row", "missing-operation", "extra-operation", "unknown-prior"]
)
def test_current_four_operation_join_real_checker_rejects_missing_rows(
    tmp_path, monkeypatch, fmt, prior_kind, fault
):
    """新current正常成立を先に確認し、旧checkerのまま未宣言joinを拒否する。"""
    import json

    from pitchlog.repositories import play_prefix as reader

    root, module = _v3_compatibility_root(tmp_path)
    monkeypatch.setattr(reader, "__file__", str(module))
    base = root / "contracts/state-transition"
    path = base / "play_prefix_v2_source_compatibility_v1.json"
    data = json.loads(path.read_bytes())
    w = json.loads((base / "nonplay_v3_compatibility_witness_v1.json").read_bytes())
    prior = (
        w["executionArtifactSha256"]
        if prior_kind == "current"
        else w["priorArtifacts"][0]
    )
    execution = w["executionArtifactSha256"]
    reader._require_legacy_compatibility(prior, execution, source_format=fmt)
    index = next(
        i
        for i, r in enumerate(data["cases"])
        if r["sourceFormat"] == fmt
        and r["priorArtifactSha256"] == prior
        and r["executionArtifactSha256"] == execution
    )
    if fault == "missing-row":
        data["cases"].pop(index)
    elif fault == "missing-operation":
        data["cases"][index]["compatibleOperations"].pop()
    elif fault == "extra-operation":
        data["cases"][index]["compatibleOperations"].append("applyUndo")
    else:
        prior = "0" * 64
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    with pytest.raises(OrdinaryPrefixError):
        reader._require_legacy_compatibility(prior, execution, source_format=fmt)


def test_v3_v2_unloaded_execution_is_not_qualified_by_historical_witness():
    """旧witnessを保存しても現在未loadedの旧実行版を成功へ格上げしない。"""
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    witness = json.loads(
        (
            root / "contracts/state-transition/nonplay_v3_compatibility_witness_v2.json"
        ).read_bytes()
    )
    current = witness["executionArtifactSha256"]
    actual = hashlib.sha256(
        (root / "frontend/public/domain/pitchlog-domain.js").read_bytes()
    ).hexdigest()
    assert current != actual
    for prior in (witness["historicalArtifactSha256"], current):
        with pytest.raises(OrdinaryPrefixError):
            _require_legacy_compatibility(
                prior, current, source_format="play-prefix-play-v3"
            )
    for prior, execution in (("0" * 64, current), (current, "0" * 64)):
        with pytest.raises(OrdinaryPrefixError):
            _require_legacy_compatibility(
                prior, execution, source_format="play-prefix-play-v3"
            )


def test_v3_v2_followed_hash_still_rejects_changed_old_value():
    """witnessとregistryを同時追随させても旧53値の改変を拒否する。"""
    import hashlib
    import json
    from pathlib import Path

    from pitchlog.repositories.play_prefix import _validated_v3_witness_v2

    root = Path(__file__).resolve().parents[2]
    base = root / "contracts/state-transition"
    data = json.loads((base / "nonplay_v3_compatibility_witness_v2.json").read_bytes())
    registry = json.loads(
        (base / "play_prefix_v3_source_compatibility_v2.json").read_bytes()
    )
    old = (base / "nonplay_v3_compatibility_witness_v1.json").read_bytes()
    current = data["executionArtifactSha256"]
    data["samples"][0]["priorActual"]["value"]["t1"]["after"]["stateFields"][
        "state.outs"
    ] = "2"
    data["samplesSha256"] = hashlib.sha256(
        json.dumps(
            data["samples"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    registry["currentWitnessSha256"] = digest
    for row in registry["cases"]:
        row["witnessSha256"] = digest
    registry_raw = (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode()
    with pytest.raises(ValueError):
        _validated_v3_witness_v2(raw, registry_raw, old, current)
