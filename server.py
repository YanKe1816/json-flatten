#!/usr/bin/env python3
"""json-flatten MCP task app (stdlib only)."""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

APP_NAME = "json-flatten"
APP_VERSION = "1.0.0"
SUPPORT_EMAIL = "support@example.com"
PROTOCOL_VERSION = "2024-11-05"

TASK_NAME = "json_flatten"
TASK_ROLE = "JSON structure transformer"
TASK_GOAL = "Flatten nested JSON objects into dot-notation key paths."

JSONRPC_VERSION = "2.0"


def get_openai_apps_challenge_response() -> str:
    return os.environ.get("OPENAI_APPS_CHALLENGE", "PLACEHOLDER")


def flatten_object(data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Recursively flatten nested dicts to dot-notation keys.

    Rules:
    - only dict values are flattened
    - arrays are preserved as-is
    - empty dict values are preserved as {}
    """
    out: Dict[str, Any] = {}
    for key in sorted(data.keys()):
        value = data[key]
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            if value:
                out.update(flatten_object(value, path))
            else:
                out[path] = {}
        else:
            out[path] = value
    return out


def jsonrpc_result(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def jsonrpc_error(request_id: Any, code: int, message: str, reason: str) -> Dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message, "data": {"reason": reason}},
    }


def build_tool_definition() -> Dict[str, Any]:
    return {
        "name": TASK_NAME,
        "description": "Flatten nested JSON into dot-notation keys",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"}
            },
            "required": ["data"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
    }


def build_manifest() -> Dict[str, Any]:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "task": TASK_NAME,
        "tools": [build_tool_definition()],
    }


def handle_rpc(payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    request_id = payload.get("id")

    if payload.get("jsonrpc") != JSONRPC_VERSION:
        return 400, jsonrpc_error(request_id, -32600, "Invalid Request", "jsonrpc must be '2.0'")

    method = payload.get("method")
    if not isinstance(method, str):
        return 400, jsonrpc_error(request_id, -32600, "Invalid Request", "method must be a string")

    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return 400, jsonrpc_error(request_id, -32602, "Invalid params", "params must be an object")

    if method == "initialize":
        protocol_version = payload.get("protocolVersion")
        if not isinstance(protocol_version, str) or not protocol_version.strip():
            protocol_version = PROTOCOL_VERSION

        return 200, jsonrpc_result(
            request_id,
            {
                "protocolVersion": protocol_version,
                "serverInfo": {"name": APP_NAME, "version": APP_VERSION},
                "capabilities": {"tools": {}},
            },
        )

    if method == "notifications/initialized":
        return 200, jsonrpc_result(request_id, {})

    if method == "tools/list":
        return 200, jsonrpc_result(
            request_id,
            {
                "tools": [build_tool_definition()]
            },
        )

    if method == "tools/call":
        if params.get("name") != TASK_NAME:
            return 400, jsonrpc_error(request_id, -32602, "Invalid params", "unknown tool name")

        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return 400, jsonrpc_error(request_id, -32602, "Invalid params", "arguments must be an object")

        if "data" not in arguments:
            return 400, jsonrpc_error(request_id, -32602, "Invalid params", "missing required field: data")

        data = arguments.get("data")
        if not isinstance(data, dict):
            return 400, jsonrpc_error(request_id, -32602, "Invalid params", "data must be a JSON object")

        flattened = flatten_object(data)
        result = {
            "content": [
                {
                    "type": "text",
                    "text": "Flattened nested JSON object into dot-notation key paths.",
                }
            ],
            "structuredContent": {"flattened": flattened},
        }
        return 200, jsonrpc_result(request_id, result)

    return 400, jsonrpc_error(request_id, -32601, "Method not found", "unsupported method")


class AppHandler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    def _send_json(self, status: int, body: Dict[str, Any]) -> None:
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_text(self, status: int, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        if path == "/privacy":
            self._send_text(
                200,
                f"{APP_NAME} processes requests in real time, does not store user data, "
                f"does not track users, does not run analytics, and does not share data with third parties.",
            )
            return

        if path == "/terms":
            self._send_text(
                200,
                f"{APP_NAME} is provided as-is for deterministic JSON transformation use only.",
            )
            return

        if path == "/support":
            self._send_text(200, f"Support: {SUPPORT_EMAIL}")
            return

        if path == "/.well-known/openai-apps-challenge":
            self._send_text(200, get_openai_apps_challenge_response())
            return

        if path == "/mcp":
            self._send_json(200, build_manifest())
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
            self._send_json(400, jsonrpc_error(None, -32700, "Parse error", "invalid content-length"))
            return

        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, jsonrpc_error(None, -32700, "Parse error", "invalid JSON body"))
            return

        if not isinstance(payload, dict):
            self._send_json(400, jsonrpc_error(None, -32600, "Invalid Request", "request body must be an object"))
            return

        status, response = handle_rpc(payload)
        self._send_json(status, response)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), AppHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _http_get(url: str) -> Tuple[int, Dict[str, str], str]:
    with urllib.request.urlopen(url, timeout=3) as resp:
        body = resp.read().decode("utf-8")
        headers = {k: v for k, v in resp.headers.items()}
        return resp.status, headers, body


def _http_post_json(url: str, body: Dict[str, Any]) -> Tuple[int, Dict[str, str], str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        text = resp.read().decode("utf-8")
        headers = {k: v for k, v in resp.headers.items()}
        return resp.status, headers, text


def run_self_tests() -> None:
    test_port = 8765
    thread = threading.Thread(
        target=run_server,
        kwargs={"host": "127.0.0.1", "port": test_port},
        daemon=True,
    )
    thread.start()

    base = f"http://127.0.0.1:{test_port}"

    source = open(__file__, "r", encoding="utf-8").read()
    assert '"0.0.0.0"' in source, 'source must contain "0.0.0.0"'
    assert 'os.environ.get("PORT"' in source, 'source must contain os.environ.get("PORT"'

    status, headers, body = _http_get(base + "/health")
    assert status == 200, "health status code must be 200"
    assert headers.get("Content-Type", "").startswith("application/json"), "health must return json"
    assert json.loads(body) == {"status": "ok"}, "health response body mismatch"

    status, _, body = _http_post_json(
        base + "/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    init_res = json.loads(body)
    assert status == 200, "initialize should return 200"
    assert init_res["result"]["protocolVersion"] == PROTOCOL_VERSION, "protocol version mismatch"
    assert init_res["result"]["serverInfo"]["name"] == APP_NAME, "serverInfo name mismatch"

    status, _, body = _http_post_json(
        base + "/mcp",
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    list_res = json.loads(body)
    assert status == 200, "tools/list should return 200"
    tool = list_res["result"]["tools"][0]
    assert tool["name"] == TASK_NAME, "tool name mismatch"

    status, _, body = _http_post_json(
        base + "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": TASK_NAME,
                "arguments": {
                    "data": {
                        "user": {"name": "Tom", "profile": {"age": 30}},
                        "tags": [1, 2],
                        "empty": {},
                    }
                },
            },
        },
    )
    call_res = json.loads(body)
    assert status == 200, "tools/call should return 200"
    assert isinstance(call_res["result"]["content"], list), "content must be present"
    assert "structuredContent" in call_res["result"], "structuredContent must be present"
    flattened = call_res["result"]["structuredContent"]["flattened"]
    assert flattened == {
        "empty": {},
        "tags": [1, 2],
        "user.name": "Tom",
        "user.profile.age": 30,
    }, "flattened payload mismatch"

    print("SELF-TESTS PASSED")


if __name__ == "__main__":
    if "--self-test" in os.sys.argv:
        run_self_tests()
    else:
        port = int(os.environ.get("PORT", "8000"))
        run_server(port=port)