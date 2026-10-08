"""MCP stdio taşıması: satır başına bir JSON-RPC 2.0 iletisi (stdin → stdout), log stderr'e.

Kaynak: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports (stdio) ve
https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle (sürüm müzakeresi).
Toplu (batch) istekler 2025-06-18'de kaldırıldığı için reddedilir. Desteklenmeyen daha yeni bir
sürüm istenirse desteklenen en yeni sürüm önerilir; istemci kabul etmezse bağlantıyı kapatır.
"""
from __future__ import annotations

import json
import sys

from . import SERVER_NAME, __version__
from .errors import KitError

MAX_MESSAGE = 512 * 1024
SUPPORTED_PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18")
INSTRUCTIONS = (
    "press-ai reads Press state with the user's own Press authority and plans Frappe app changes inside a "
    "configured workspace. Start with kit_status and contract_search. Reads are direct. Every mutation is a "
    "proposal (press_propose / app_propose_change) that a human approves in a separate terminal; this server "
    "has no approve tool and ignores confirm flags. A Press enqueue or HTTP 200 is not success: use press_track. "
    "If an outcome is unknown, stop and report; do not retry blindly. Shell, SSH and server work are out of scope."
)


def _error(message_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


class Server:
    def __init__(self, toolbox, stdin=None, stdout=None, stderr=None):
        self.toolbox = toolbox
        self.stdin = stdin or sys.stdin.buffer
        # Çıktı yerel ayardan bağımsız UTF-8 bayttır (`-I` ile PYTHONIOENCODING yok sayılır).
        self.stdout = stdout or sys.stdout.buffer
        self.stderr = stderr or sys.stderr
        self.initialized = False
        self.ready = False
        self.protocol = None

    def _send(self, payload: dict) -> None:
        self.stdout.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        self.stdout.flush()

    def serve(self) -> None:
        while True:
            line = self.stdin.readline(MAX_MESSAGE + 1)
            if not line:
                return
            if len(line) > MAX_MESSAGE:
                self._send(_error(None, -32600, "Message too large; transport closed"))
                return
            if not line.strip():
                continue
            response = self.handle_line(line)
            if response is not None:
                self._send(response)

    def handle_line(self, line) -> dict | None:
        try:
            message = json.loads(line)
        except ValueError:
            return _error(None, -32700, "Parse error")
        if not isinstance(message, dict):
            return _error(None, -32600, "Batch or non-object requests are not supported")
        if message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "Expected JSON-RPC 2.0")
        has_id = "id" in message
        message_id = message.get("id")
        if has_id and (isinstance(message_id, bool) or not isinstance(message_id, (str, int))):
            return _error(None, -32600, "Invalid request id")
        method = message.get("method")
        if not isinstance(method, str):
            return _error(message_id if has_id else None, -32600, "Method must be a string") if has_id else None
        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _error(message_id, -32602, "Params must be an object") if has_id else None
        if not has_id:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        try:
            result = self.dispatch(method, params)
        except _RpcError as error:
            return _error(message_id, error.code, error.message)
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    def dispatch(self, method: str, params: dict) -> dict:
        if method == "initialize":
            if self.initialized:
                raise _RpcError(-32600, "Already initialized")
            requested = params.get("protocolVersion")
            if not isinstance(requested, str):
                raise _RpcError(-32602, "protocolVersion must be a string")
            self.protocol = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[-1]
            self.initialized = True
            result = {"protocolVersion": self.protocol, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": SERVER_NAME, "version": __version__}}
            if self.protocol != "2024-11-05":
                result["instructions"] = INSTRUCTIONS
            return result
        if method == "ping":
            return {}
        if method in ("tools/list", "tools/call"):
            if not self.ready:
                raise _RpcError(-32002, "Initialization handshake incomplete")
            if method == "tools/list":
                return {"tools": self.toolbox.describe(self.protocol)}
            name = params.get("name")
            arguments = params.get("arguments", {})
            if arguments is None:
                arguments = {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise _RpcError(-32602, "Tool name must be a string and arguments an object")
            if not self.toolbox.has(name):
                raise _RpcError(-32602, "Unknown tool: " + name)
            return self.call_tool(name, arguments)
        raise _RpcError(-32601, "Method not found")

    def call_tool(self, name: str, arguments: dict) -> dict:
        try:
            output = self.toolbox.call(name, arguments)
            return {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, indent=1)}],
                    "isError": False}
        except KitError as error:
            return {"content": [{"type": "text", "text": json.dumps(error.as_dict(), ensure_ascii=False)}],
                    "isError": True}
        except Exception as error:  # noqa: BLE001 - araç hatası istemciye genel iletiyle döner, süreç yaşar
            self.stderr.write("press-ai: unexpected {} in {}\n".format(type(error).__name__, name))
            self.stderr.flush()
            payload = {"error": "internal", "message": "Unexpected server error ({})".format(type(error).__name__)}
            return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": True}


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
