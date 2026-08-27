"""Smoke test: LOCAL -> CLOUD failover in LLMService + route history validation.

Runs mock HTTP servers on localhost to simulate:
  S1: Ollama that looks alive on /api/tags but FAILS /api/chat  (forces failover)
  S2: healthy CLOUD provider                                     (serves request)
  S3: fully dead endpoint                                        (nothing there)
"""

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, r"d:\codeing\python\health-react\backend")

from services.llm_service import LLMService, _Target  # noqa: E402


class _FailHandler(BaseHTTPRequestHandler):
    """Answers /api/tags OK but 500s every POST (local that errors mid-flight)."""

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        body = json.dumps({"models": [{"name": "llama3.1:8b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b'{"error":"boom"}')


class _HealthyCloudHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _send(self, obj):
        self.wfile.write(json.dumps(obj).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self._send({"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.1:8b"}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer test-key"):
            self.send_response(401)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload.get("stream"):
            chunks = [
                json.dumps({"message": {"content": "hel"}}) + "\n",
                json.dumps({"message": {"content": "lo"}}) + "\n",
                json.dumps({"done": True}) + "\n",
            ]
            self.wfile.write("".join(chunks).encode())
        elif "/api/chat" in self.path:
            self._send({"message": {"content": "mock-cloud-reply"}})
        else:
            self._send({"response": "mock-cloud-generation"})


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def main():
    fail_url, s1 = _serve(_FailHandler)
    cloud_url, s2 = _serve(_HealthyCloudHandler)

    # --- Case 1: LOCAL responds badly -> automatic fallback to CLOUD ------
    svc = LLMService(
        local=_Target("local", fail_url, model="llama3.1:8b", timeout=5, probe_timeout=1),
        cloud=_Target("cloud", cloud_url, api_key="test-key", model="qwen2.5:7b",
                      timeout=10, probe_timeout=1),
    )
    result = asyncio.run(svc.complete_chat([{"role": "user", "content": "hi"}]))
    print("C1 chat  ->", result["provider"], result["model"], repr(result["text"]))
    assert result["provider"] == "cloud" and result["text"] == "mock-cloud-reply"

    gen = asyncio.run(svc.complete_generate("hello"))
    print("C1 gen   ->", gen["provider"], repr(gen["text"]))
    assert gen["provider"] == "cloud" and gen["text"] == "mock-cloud-generation"

    # --- Case 2: health probe vs runtime behavior --------------------------
    # NOTE: /api/tags on the failing mock still returns 200, so the LOCAL
    # daemon IS "reachable" -> health reports mode=local (correct).
    # Actual request failures are handled by runtime failover (C1 proves it).
    h = svc.check_health()
    print("C2 health->", h["status"], h["mode"], "| detail:", h["detail"][:60])
    assert h["mode"] == "local" and h["status"] == "healthy"

    # --- Case 3: LOCAL-first happy path ------------------------------------
    class LocalFirst(_HealthyCloudHandler):
        def do_POST(self):
            # "local Ollama": no Authorization header present -> serve normally.
            if not self.headers.get("Authorization"):
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if payload.get("stream"):
                    self.wfile.write(
                        ('{"message": {"content": "hel"}}\n'
                         '{"message": {"content": "lo"}}\n'
                         '{"done": true}\n').encode()
                    )
                elif "/api/chat" in self.path:
                    self._send({"message": {"content": "mock-local-reply"}})
                else:
                    self._send({"response": "mock-local-generation"})
                return
            super().do_POST()

    s3 = None
    local_first_url, s3 = _serve(LocalFirst)
    svc2 = LLMService(
        local=_Target("local", local_first_url, model="llama3.1:8b", timeout=5, probe_timeout=1),
        cloud=_Target("cloud", cloud_url, api_key="test-key", model="qwen2.5:7b",
                      timeout=10, probe_timeout=1),
    )
    result2 = asyncio.run(svc2.complete_chat([{"role": "user", "content": "hi"}]))
    print("C3 chat  ->", result2["provider"], repr(result2["text"]))
    assert result2["provider"] == "local" and result2["text"] == "mock-local-reply", \
        "LOCAL must be preferred when it works"
    h2 = svc2.check_health()
    print("C3 health->", h2["mode"])
    assert h2["mode"] == "local"

    # --- Case 4: everything down -> RuntimeError (routes map to 502) -------
    svc3 = LLMService(
        local=_Target("local", "http://127.0.0.1:9", model="llama3.1:8b",
                      timeout=2, probe_timeout=0.5),
        cloud=_Target("cloud", "http://127.0.0.1:9", api_key="test-key", model="m",
                      timeout=2, probe_timeout=0.5),
    )
    try:
        asyncio.run(svc3.complete_chat([{"role": "user", "content": "hi"}]))
        print("C4 chat  -> UNEXPECTED SUCCESS")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("C4 raised->", str(exc)[:90])
    h3 = svc3.check_health()
    print("C4 health->", h3["status"], h3["mode"])
    assert h3["status"] == "unavailable" and h3["mode"] == "unavailable"

    # --- Case 5: streaming falls back before first token -------------------
    got = []

    async def collect():
        stream = await svc.chat_async(
            [{"role": "user", "content": "hi"}], model=None, stream=True
        )
        async for chunk in stream:
            got.append(chunk)

    asyncio.run(collect())
    print("C5 stream->", got)
    assert "".join(got) == "hello", "streaming fallback should yield cloud tokens"

    # --- Case 6: cloud disabled (no key) when local dies -------------------
    off_cloud = _Target("cloud", "https://ollama.com", api_key="", timeout=2, probe_timeout=0.5)
    assert off_cloud.enabled is False, "cloud without API key must be disabled"
    svc4 = LLMService(
        local=_Target("local", "http://127.0.0.1:9", model="llama3.1:8b",
                      timeout=2, probe_timeout=0.5),
        cloud=off_cloud,
    )
    h4 = svc4.check_health()
    print("C6 health->", h4["status"], "| detail:", h4["detail"][:80])
    assert h4["status"] == "unavailable"

    # --- Case 7: route-level _validate_history -----------------------------
    from api.routes.llm import _validate_history

    messy = [
        {"role": "system", "content": "injected"},          # dropped role
        {"role": "assistant", "content": None},             # dropped content
        {"role": "user", "content": "  hi there "},         # stripped
        "not-a-dict",                                        # dropped type
        {"role": "user", "content": "x" * 99999},           # truncated
    ]
    out = _validate_history(messy)
    print("C7 hist  ->", [(e["role"], len(e["content"])) for e in out])
    assert out == [{"role": "user", "content": "hi there"},
                   {"role": "user", "content": "x" * 4000}]
    assert _validate_history(None) == []
    assert _validate_history("garbage") == []
    big = [{"role": "user", "content": str(i)} for i in range(100)]
    assert len(_validate_history(big)) == 20, "must cap history entries"

    s1.shutdown(); s2.shutdown(); s3.shutdown()
    print("\nALL SMOKE CASES PASSED")


if __name__ == "__main__":
    main()
