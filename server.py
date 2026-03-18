#!/usr/bin/env python3
"""json-flatten MCP HTTP server using only Python standard library."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse


HOST = "0.0.0.0"
PORT = 8000

# --- OpenAI domain verification challenge block (isolated for easy updates) ---
OPENAI_APPS_CHALLENGE_RESPONSE = "challenge-ok"


JSONRPC_VERSION = "2.0"
TOOL_NAME = "json_flatten"


def flatten_object(data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dictionaries using dot-notation keys.

    Rules:
    - Only dictionaries are flattened.
    - Lists/arrays are preserved as-is.
    - Empty dictionaries that are values are preserved as {}.
    """
    flattened: Dict[str, Any] = {}
    for key in data:
        value = data[key]
        path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            if value:
                flattened.update(flatten_object(value, path))
            else:
                flattened[path] = {}
        else:
            flattened[path] = value
    return flattened


def jsonrpc_error_response(
    request_id: Any,
    code: int,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def jsonrpc_result_response(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def handle_jsonrpc(payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    request_id = payload.get("id")

    if payload.get("jsonrpc") != JSONRPC_VERSION:
        return 400, jsonrpc_error_response(request_id, -32600, "Invalid Request", {"reason": "jsonrpc must be '2.0'"})

    method = payload.get("method")
    if not isinstance(method, str):
        return 400, jsonrpc_error_response(request_id, -32600, "Invalid Request", {"reason": "method must be a string"})

    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return 400, jsonrpc_error_response(request_id, -32602, "Invalid params", {"reason": "params must be an object"})

    if method == "initialize":
        return 200, jsonrpc_result_response(
            request_id,
            {
                "serverInfo": {"name": "json-flatten", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return 200, jsonrpc_result_response(
            request_id,
            {
                "tools": [
                    {
                        "name": TOOL_NAME,
                        "description": "Flatten nested JSON objects into dot-notation key paths.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"data": {"type": "object"}},
                            "required": ["data"],
                            "additionalProperties": False,
                        },
                    }
                ]
            },
        )

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})

        if name != TOOL_NAME:
            return 400, jsonrpc_error_response(request_id, -32602, "Invalid params", {"reason": "unknown tool name"})

        if not isinstance(arguments, dict):
            return 400, jsonrpc_error_response(request_id, -32602, "Invalid params", {"reason": "arguments must be an object"})

        if "data" not in arguments:
            return 400, jsonrpc_error_response(request_id, -32602, "Invalid params", {"reason": "missing required field: data"})

        data = arguments.get("data")
        if not isinstance(data, dict):
            return 400, jsonrpc_error_response(request_id, -32602, "Invalid params", {"reason": "data must be a JSON object"})

        flattened = flatten_object(data)
        return 200, jsonrpc_result_response(request_id, {"flattened": flattened})

    return 400, jsonrpc_error_response(request_id, -32601, "Method not found")


class AppHandler(BaseHTTPRequestHandler):
    server_version = "json-flatten/1.0"

    def _send_json(self, status: int, body: Dict[str, Any]) -> None:
        data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, status: int, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        if path == "/.well-known/openai-apps-challenge":
            self._send_text(200, OPENAI_APPS_CHALLENGE_RESPONSE)
            return

        self._send_json(404, {"error": "Not Found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/mcp":
            self._send_json(404, {"error": "Not Found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, jsonrpc_error_response(None, -32700, "Parse error", {"reason": "invalid content-length"}))
            return

        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, jsonrpc_error_response(None, -32700, "Parse error", {"reason": "invalid JSON body"}))
            return

        if not isinstance(payload, dict):
            self._send_json(400, jsonrpc_error_response(None, -32600, "Invalid Request", {"reason": "request body must be an object"}))
            return

        status, response_body = handle_jsonrpc(payload)
        self._send_json(status, response_body)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep output clean and deterministic.
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), AppHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
