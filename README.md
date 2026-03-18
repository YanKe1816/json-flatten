# json-flatten

Minimal MCP-compatible HTTP task app implemented with Python standard library.

## Features
- `GET /health`
- `GET /privacy`
- `GET /terms`
- `GET /support`
- `GET /.well-known/openai-apps-challenge`
- `GET /mcp` (manifest)
- `POST /mcp` (JSON-RPC)

Tool:
- `json_flatten`: Flatten nested JSON dictionaries into dot-notation key paths.

## Run locally
```bash
python server.py
```

Uses `PORT` env var when present (Render-friendly).

## Self-tests
```bash
python server.py --self-test
```

## Example JSON-RPC call
```bash
curl -s http://127.0.0.1:${PORT:-8000}/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "json_flatten",
      "arguments": {
        "data": {"user":{"name":"Tom","profile":{"age":30}}}
      }
    }
  }'
```
