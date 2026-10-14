"""B0 experiments 4-6: a logging pass-through proxy for the Anthropic API.

Run it, point ANTHROPIC_BASE_URL at it, and every /v1/messages call is forwarded unchanged. One JSON line per call
goes to --log: model, token usage (input, output, cache read and write) and the tool calls in the response.
"""

from __future__ import annotations

import argparse
import http.client
import http.server
import json
import ssl
import sys
import threading
import time

UPSTREAM = "api.anthropic.com"
LOCK = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    log_path = ""

    def log_message(self, *_):  # quiet
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
        conn = http.client.HTTPSConnection(UPSTREAM, context=ssl.create_default_context(), timeout=600)
        started = time.time()
        conn.request("POST", self.path, body=body, headers=headers)
        resp = conn.getresponse()
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in ("transfer-encoding", "content-length", "connection", "content-encoding"):
                self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        captured = bytearray()
        while True:
            chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
            if not chunk:
                break
            captured += chunk
            self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()
        self.record(body, bytes(captured), resp.status, time.time() - started)
        self.close_connection = True

    def record(self, request: bytes, response: bytes, status: int, seconds: float):
        entry = {"t": time.time(), "path": self.path, "status": status, "seconds": round(seconds, 2), "usage": {}, "tools": []}
        try:
            req = json.loads(request)
            entry["model"] = req.get("model")
            entry["messages"] = len(req.get("messages", []))
        except ValueError:
            pass
        text = response.decode("utf-8", "replace")
        events = []
        if text.lstrip().startswith("{"):
            try:
                events = [{"type": "message", "message": json.loads(text)}]
            except ValueError:
                pass
        else:
            for line in text.splitlines():
                if line.startswith("data:"):
                    try:
                        events.append(json.loads(line[5:]))
                    except ValueError:
                        pass
        tools: dict[int, dict] = {}
        for e in events:
            msg = e.get("message") or {}
            for k, v in (msg.get("usage") or {}).items():
                if isinstance(v, int):
                    entry["usage"][k] = entry["usage"].get(k, 0) + v
            for block in msg.get("content") or []:
                if block.get("type") == "tool_use":
                    entry["tools"].append({"name": block["name"], "input": block.get("input")})
            if e.get("type") == "message_delta":
                for k, v in (e.get("usage") or {}).items():
                    if isinstance(v, int):
                        entry["usage"][k] = v  # cumulative in the final delta
            if e.get("type") == "content_block_start" and e["content_block"].get("type") == "tool_use":
                tools[e["index"]] = {"name": e["content_block"]["name"], "json": ""}
            if e.get("type") == "content_block_delta" and e["delta"].get("type") == "input_json_delta" and e["index"] in tools:
                tools[e["index"]]["json"] += e["delta"]["partial_json"]
        for t in tools.values():
            try:
                entry["tools"].append({"name": t["name"], "input": json.loads(t["json"] or "{}")})
            except ValueError:
                entry["tools"].append({"name": t["name"], "input": t["json"]})
        with LOCK, open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    Handler.log_path = a.log
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"proxy on http://127.0.0.1:{a.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
