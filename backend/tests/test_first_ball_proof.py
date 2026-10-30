"""V12のcanonical境界を確認する。権利成功を認定しない。"""

import base64
import hashlib

import pytest

from pitchlog.sync.first_ball_proof import FirstBallProofError, proof_digest


def test_raw_digest_matches_issuer() -> None:
    """既issuerと同じraw digestであり復号を要しない。"""
    raw = bytes(range(32))
    proof = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    assert proof_digest(proof) == hashlib.sha256(raw).digest()


@pytest.mark.parametrize(
    "value",
    [
        None,
        b"A" * 43,
        "A" * 42,
        "A" * 44,
        "A" * 43 + "=",
        "/" * 43,
        "A" * 42 + "B",
        "secret-value",
    ],
)
def test_noncanonical_is_rejected_without_disclosure(value: object) -> None:
    """長さ・padding・未使用bitも含めて拒否する。"""
    with pytest.raises(FirstBallProofError) as caught:
        proof_digest(value)
    assert str(caught.value) == "記録権証明の形式が不正"
