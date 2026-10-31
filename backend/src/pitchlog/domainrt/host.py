"""検証済みの単一 artifact と常駐 Node の寿命を管理する。"""

import hashlib
import json
import os
import re
import resource
import selectors
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

_ARTIFACT_RELATIVE = Path("frontend/public/domain/pitchlog-domain.js")
_DECLARATION_RELATIVE = Path("frontend/public/domain/pitchlog-domain.json")
_NODE_SCRIPT = r"""
// ゲストへ渡すホスト関数は空集合。標準出力は JSON 行プロトコル専用とする。
import vm from 'node:vm'
import readline from 'node:readline'

const HOST_FUNCTIONS = Object.freeze({})
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity })

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`)
}

function errorCode(error) {
  if (error?.code === 'ERR_SCRIPT_EXECUTION_TIMEOUT') return 'TIME_LIMIT'
  if (error?.code === 'ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING') {
    return 'DYNAMIC_IMPORT_DISABLED'
  }
  if (error instanceof SyntaxError) return 'INVALID_ARTIFACT'
  return 'GUEST_ERROR'
}

let context
let timeout
let initialized = false

for await (const line of input) {
  let message
  try {
    message = JSON.parse(line)
  } catch {
    send({ error: { code: 'PROTOCOL_ERROR' } })
    continue
  }

  if (!initialized) {
    try {
      if (message?.type !== 'init' || typeof message.source !== 'string') {
        throw new Error('invalid initialization')
      }
      if (!Number.isInteger(message.vmTimeoutMs) || message.vmTimeoutMs < 1) {
        throw new Error('invalid timeout')
      }
      timeout = message.vmTimeoutMs
      context = vm.createContext(Object.assign(Object.create(null), HOST_FUNCTIONS), {
        codeGeneration: { strings: false, wasm: false },
      })
      // vm の既定 console はホスト能力なので、artifact の評価前に取り除く。
      vm.runInContext('delete globalThis.console', context, { timeout })
      new vm.Script(message.source, { filename: 'pitchlog-domain.js' })
        .runInContext(context, { timeout })
      const valid = vm.runInContext(
        'typeof globalThis.PitchlogDomain === "object" && ' +
          'Object.isFrozen(globalThis.PitchlogDomain)',
        context,
        { timeout },
      )
      if (!valid) throw new Error('missing frozen entry')
      initialized = true
      send({ type: 'ready' })
    } catch (error) {
      process.stderr.write(`domainrt load failed: ${errorCode(error)}\n`)
      send({ type: 'failed', error: { code: errorCode(error) } })
      break
    }
    continue
  }

  const id = message?.id
  try {
    if (
      typeof id !== 'string' ||
      typeof message.operation !== 'string' ||
      typeof message.input !== 'string'
    ) {
      throw new Error('invalid request')
    }
    // JSON.stringify が操作名と入力を JS ソースへ安全に埋め込む。
    const expression =
      `globalThis.PitchlogDomain[${JSON.stringify(message.operation)}]` +
      `(${JSON.stringify(message.input)})`
    const result = new vm.Script(expression, { filename: 'domain-call.js' })
      .runInContext(context, { timeout })
    const settled = await result
    if (typeof settled !== 'string') throw new Error('non-string result')
    JSON.parse(settled)
    send({ id, result: settled })
  } catch (error) {
    const code = errorCode(error)
    process.stderr.write(`domainrt call failed: ${code}\n`)
    send({ id, error: { code } })
    if (code === 'TIME_LIMIT') break
  }
}
"""
_NODE_VERSION = "v24.16.0"
_HEAP_MIB = 16
_VM_TIMEOUT_MS = 100
_REPLY_TIMEOUT_SECONDS = 2.0
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


class DomainRuntimeError(RuntimeError):
    """fail-closed の理由を機械可読なコードで表す。"""

    def __init__(self, code: str, message: str) -> None:
        """エラーを初期化する。

        Args:
            code: 安定した理由コード。
            message: 診断用の説明。
        """
        self.code = code
        super().__init__(message)


def _reject_json_numbers(value: Any) -> None:
    """境界の JSON に数値型が紛れた場合に拒否する。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        raise DomainRuntimeError("INVALID_BOUNDARY", "整数は十進文字列で渡す")
    if isinstance(value, list):
        for item in value:
            _reject_json_numbers(item)
    elif isinstance(value, dict):
        for item in value.values():
            _reject_json_numbers(item)


def _verified_source(artifact: Path, declaration: Path) -> str:
    """宣言と artifact を検証してソースを返す。"""
    try:
        declaration_text = declaration.read_text(encoding="utf-8")
        payload = artifact.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise DomainRuntimeError(
            "ARTIFACT_UNAVAILABLE", "artifact または宣言を読めない"
        ) from exc
    try:
        manifest = json.loads(declaration_text)
    except json.JSONDecodeError as exc:
        raise DomainRuntimeError(
            "INVALID_DECLARATION", "artifact の宣言が不正"
        ) from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schemaVersion", "fileName", "sha256"}
        or type(manifest["schemaVersion"]) is not int
        or manifest["schemaVersion"] != 1
        or manifest["fileName"] != _ARTIFACT_RELATIVE.name
        or not isinstance(manifest["sha256"], str)
        or _SHA256_PATTERN.fullmatch(manifest["sha256"]) is None
    ):
        raise DomainRuntimeError("INVALID_DECLARATION", "artifact の宣言が不正")
    if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
        raise DomainRuntimeError("HASH_MISMATCH", "artifact の SHA-256 が一致しない")
    try:
        return payload.decode("utf-8")
    except UnicodeError as exc:
        raise DomainRuntimeError(
            "INVALID_ARTIFACT", "artifact が UTF-8 ではない"
        ) from exc


def _product_root() -> Path:
    """ソース配置と実行環境の固定配置から配布ルートを選ぶ。"""
    installed = Path(__file__).resolve()
    if installed.is_relative_to(Path("/app/backend/.venv")):
        return Path("/app")
    if installed.parents[2].name == "src" and installed.parents[3].name == "backend":
        return installed.parents[4]
    # 一時コピーを読み込む試験でも、実行中の backend 仮想環境を基準にする。
    runtime = Path(sys.prefix).resolve()
    if runtime.name == ".venv" and runtime.parent.name == "backend":
        return runtime.parent.parent
    return installed.parents[4]


def _product_artifact_paths() -> tuple[Path, Path]:
    """製品の固定基準から artifact と宣言のパスを返す。"""
    root = _product_root()
    return root / _ARTIFACT_RELATIVE, root / _DECLARATION_RELATIVE


def verify_domain_artifact() -> None:
    """製品の artifact と宣言を照合し、不一致なら例外を出す。

    Raises:
        DomainRuntimeError: ファイル不在、宣言の不正、ハッシュ不一致。
    """
    _verified_source(*_product_artifact_paths())


def open_domain_host() -> "NodeDomainHost":
    """製品の固定パスから検証して常駐ホストを起動する。"""
    return NodeDomainHost(*_product_artifact_paths())


class NodeDomainHost:
    """試験用にだけ artifact パスを差し込める下位ホスト。"""

    def __init__(
        self,
        artifact: Path,
        declaration: Path,
        *,
        heap_mib: int = _HEAP_MIB,
        vm_timeout_ms: int = _VM_TIMEOUT_MS,
        reply_timeout_seconds: float = _REPLY_TIMEOUT_SECONDS,
    ) -> None:
        """ハッシュと Node 版を確認して起動する。

        Args:
            artifact: 試験用の artifact パス。
            declaration: 対応する SHA-256 宣言。
            heap_mib: Node の old-space 上限 MiB。
            vm_timeout_ms: VM 内の同期実行上限ミリ秒。
            reply_timeout_seconds: Python 側の応答待ち上限秒。
        """
        self._source = _verified_source(artifact, declaration)
        self._heap_mib = heap_mib
        self._vm_timeout_ms = vm_timeout_ms
        self._reply_timeout_seconds = reply_timeout_seconds
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._buffer = bytearray()
        self._next_id = 0
        self._start()

    @property
    def artifact_sha256(self) -> str:
        """検証済みの実loaded不変sourceのhashを返す。ファイルを再読込しない。"""
        return hashlib.sha256(self._source.encode("utf-8")).hexdigest()

    def __enter__(self) -> "NodeDomainHost":
        """ホストをコンテキストへ渡す。"""
        return self

    def __exit__(self, *_args: object) -> None:
        """コンテキスト終了時にプロセスを止める。"""
        self.close()

    def close(self) -> None:
        """常駐プロセスを停止する。"""
        with self._lock:
            self._stop()

    def call(self, operation: str, request_json: str) -> str:
        """JSON 文字列の要求を送り、JSON 文字列の結果を返す。

        Args:
            operation: 凍結された公開口の操作名。
            request_json: 整数を十進文字列で持つ JSON 文字列。

        Returns:
            ゲストが返した JSON 文字列。

        Raises:
            DomainRuntimeError: 境界違反、ゲスト例外、プロセス障害。
        """
        if (
            not isinstance(operation, str)
            or _OPERATION_PATTERN.fullmatch(operation) is None
        ):
            raise DomainRuntimeError("INVALID_OPERATION", "操作名が不正")
        if not isinstance(request_json, str):
            raise DomainRuntimeError("INVALID_BOUNDARY", "入力は JSON 文字列で渡す")
        try:
            _reject_json_numbers(json.loads(request_json))
        except json.JSONDecodeError as exc:
            raise DomainRuntimeError(
                "INVALID_BOUNDARY", "入力が JSON ではない"
            ) from exc
        with self._lock:
            if self._process is None:
                raise DomainRuntimeError("CLOSED", "ホストは停止済み")
            self._next_id += 1
            request_id = str(self._next_id)
            deadline = time.monotonic() + self._reply_timeout_seconds
            try:
                self._send(
                    {"id": request_id, "operation": operation, "input": request_json},
                    deadline,
                )
                response = self._read_response(deadline)
                if response.get("id") != request_id:
                    raise DomainRuntimeError("PROTOCOL_ERROR", "応答 ID が一致しない")
                error = response.get("error")
                if isinstance(error, dict):
                    code = error.get("code")
                    if not isinstance(code, str):
                        raise DomainRuntimeError("PROTOCOL_ERROR", "エラー応答が不正")
                    if code == "TIME_LIMIT":
                        self._restart()
                    raise DomainRuntimeError(code, "ゲストの実行に失敗")
                result = response.get("result")
                if not isinstance(result, str):
                    raise DomainRuntimeError(
                        "PROTOCOL_ERROR", "結果が JSON 文字列ではない"
                    )
                _reject_json_numbers(json.loads(result))
                return result
            except (
                BrokenPipeError,
                OSError,
                EOFError,
                TimeoutError,
                json.JSONDecodeError,
            ) as exc:
                self._restart()
                raise DomainRuntimeError(
                    "PROCESS_FAILURE", "Node から有効な応答がない"
                ) from exc
            except DomainRuntimeError as exc:
                if exc.code == "PROTOCOL_ERROR":
                    self._restart()
                raise

    def _start(self) -> None:
        """Node の版を検査し、検証済みソースをロードする。"""
        try:
            version = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=2,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise DomainRuntimeError(
                "NODE_UNAVAILABLE", "Node の版を確認できない"
            ) from exc
        if version != _NODE_VERSION:
            raise DomainRuntimeError("NODE_VERSION", f"Node {_NODE_VERSION} が必要")
        self._buffer.clear()
        self._process = subprocess.Popen(
            [
                "node",
                "--disallow-code-generation-from-strings",
                f"--max-old-space-size={self._heap_mib}",
                "--input-type=module",
                "--eval",
                _NODE_SCRIPT,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            preexec_fn=_disable_core_dump,
        )
        try:
            deadline = time.monotonic() + self._reply_timeout_seconds
            self._send(
                {
                    "type": "init",
                    "source": self._source,
                    "vmTimeoutMs": self._vm_timeout_ms,
                },
                deadline,
            )
            ready = self._read_response(deadline)
            if ready != {"type": "ready"}:
                raise DomainRuntimeError("LOAD_FAILED", "artifact をロードできない")
        except (OSError, EOFError, TimeoutError, json.JSONDecodeError) as exc:
            self._stop()
            raise DomainRuntimeError("LOAD_FAILED", "Node の初期化に失敗") from exc
        except DomainRuntimeError:
            self._stop()
            raise

    def _stop(self) -> None:
        """既存のプロセスを確実に回収する。"""
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=2)

    def _restart(self) -> None:
        """異常なコンテキストを捨て、新しいプロセスを起動する。"""
        self._stop()
        self._start()

    def _send(self, message: dict[str, Any], deadline: float) -> None:
        """期限内にプロトコル専用の標準入力へ 1 行送る。"""
        process = self._process
        if process is None or process.stdin is None:
            raise EOFError
        line = (
            json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
            + b"\n"
        )
        descriptor = process.stdin.fileno()
        os.set_blocking(descriptor, False)
        pending = memoryview(line)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdin, selectors.EVENT_WRITE)
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError
                try:
                    written = os.write(descriptor, pending)
                except BlockingIOError:
                    continue
                pending = pending[written:]

    def _read_response(self, deadline: float) -> dict[str, Any]:
        """期限内に標準出力の 1 行を読み取る。"""
        process = self._process
        if process is None or process.stdout is None:
            raise EOFError
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                newline = self._buffer.find(b"\n")
                if newline >= 0:
                    line = bytes(self._buffer[:newline])
                    del self._buffer[: newline + 1]
                    parsed = json.loads(line)
                    if not isinstance(parsed, dict):
                        raise DomainRuntimeError(
                            "PROTOCOL_ERROR", "応答がオブジェクトではない"
                        )
                    return parsed
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise EOFError
                self._buffer.extend(chunk)
                if len(self._buffer) > 8 * 1024 * 1024:
                    raise DomainRuntimeError("PROTOCOL_ERROR", "応答が大きすぎる")


def _disable_core_dump() -> None:
    """メモリ制限時にも core ファイルを生成しない。"""
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
