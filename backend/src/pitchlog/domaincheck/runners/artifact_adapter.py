"""検証済み常駐 Node ホストをベクタ runner の二つの境界へ接続する。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pitchlog.domainrt.host import NodeDomainHost


@dataclass(frozen=True, slots=True)
class ArtifactCall:
    """一つの操作で送受信した JSON 文字列を保持する。"""

    operation: str
    request_json: str
    response_json: str


@dataclass(slots=True)
class NodeArtifactAdapter:
    """常駐 Node の同一 artifact を正規化・計算 adapter として呼ぶ。

    Attributes:
        host: hash と Node 版の検査を終えた常駐ホスト。
        generated_id: 正規化生成物の宣言 ID。
        source_hash: 正規化生成物の SHA-256 宣言。
        calls: 比較試験で使う生の要求・応答。実行順を保持する。
    """

    host: NodeDomainHost
    generated_id: str
    source_hash: str
    calls: list[ArtifactCall] = field(default_factory=list)

    def _invoke(self, operation: str, request: object) -> object:
        """JSON 文字列の境界だけを通して操作を呼び出す。"""
        request_json = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        response_json = self.host.call(operation, request_json)
        self.calls.append(ArtifactCall(operation, request_json, response_json))
        return json.loads(response_json)

    def normalize(self, raw: object) -> object:
        """合成 artifact の正規化操作を呼ぶ。"""
        return self._invoke("normalize", raw)

    def execute(self, case_id: str, normalized: object) -> object:
        """合成 artifact の計算操作へ case ID と正規化値を渡す。"""
        return self._invoke("calculate", {"caseId": case_id, "normalized": normalized})


__all__ = ["ArtifactCall", "NodeArtifactAdapter"]
