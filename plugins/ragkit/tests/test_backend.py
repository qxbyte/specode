import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from rag import backend


def test_resolve_none_when_nothing_available(kb):
    kind, _ = backend.resolve({})
    assert kind == "none"


def test_resolve_prefers_local_when_cached(kb, tmp_path, monkeypatch):
    snap = (tmp_path / "hf" / "hub" /
            "models--Qwen--Qwen3-Embedding-0.6B" / "snapshots" / "abc")
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    cfg = {"cloud": {"provider": "qwen",
                     "base_url": "https://example.com/v1",
                     "model": "text-embedding-v4",
                     "key_env": "DASHSCOPE_API_KEY"}}
    kind, opts = backend.resolve(cfg)   # both available -> local wins (固定默认本地)
    assert kind == "local"
    assert opts["model"] == "Qwen/Qwen3-Embedding-0.6B"


def test_resolve_cloud_when_no_local(kb, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    cfg = {"cloud": {"provider": "qwen", "base_url": "https://example.com/v1",
                     "model": "text-embedding-v4", "key_env": "DASHSCOPE_API_KEY"}}
    kind, _ = backend.resolve(cfg)
    assert kind == "cloud"


def test_cloud_not_configured_without_key_env(kb, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    cfg = {"cloud": {"provider": "qwen", "base_url": "https://example.com/v1",
                     "model": "text-embedding-v4", "key_env": "DASHSCOPE_API_KEY"}}
    assert backend.resolve(cfg)[0] == "none"


def test_no_backend_block_contains_both_paths(kb):
    block = backend.no_backend_block()
    assert "ragkit_local_embed.py install" in block
    assert "backend set" in block
    assert "HF_ENDPOINT" in block
    assert "{root}" not in block


def test_dummy_encode_similarity_ordering():
    vecs = backend.encode("dummy", {}, ["银行账号脱敏规则", "银行账号脱敏", "见费出单收款"])
    sim_close = float(vecs[0] @ vecs[1])
    sim_far = float(vecs[0] @ vecs[2])
    assert sim_close > sim_far
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-5)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["Authorization"] == "Bearer sk-test"
        data = [{"index": i, "embedding": [1.0, float(i)]} for i in range(len(body["input"]))]
        payload = json.dumps({"data": data}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


def test_cloud_encode_openai_compat(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("TEST_RAGKIT_KEY", "sk-test")
    opts = {"base_url": f"http://127.0.0.1:{server.server_port}",
            "model": "m", "key_env": "TEST_RAGKIT_KEY"}
    vecs = backend.encode("cloud", opts, ["a", "b"])
    server.shutdown()
    assert vecs.shape == (2, 2)
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-5)
