"""Embedding backend resolution (fixed priority), fixed no-backend prompt block,
cloud (OpenAI-compatible, stdlib urllib), dummy (hermetic tests), local (uv sidecar)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

DEFAULT_LOCAL_MODEL = "Qwen/Qwen3-Embedding-0.6B"
EXIT_NO_BACKEND = 3
_BATCH = 16

PRESETS = {
    "openai": {"base_url": "https://api.openai.com/v1",
               "model": "text-embedding-3-small", "key_env": "OPENAI_API_KEY"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "model": "text-embedding-v4", "key_env": "DASHSCOPE_API_KEY"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4",
              "model": "embedding-3", "key_env": "ZHIPUAI_API_KEY"},
    "voyage": {"base_url": "https://api.voyageai.com/v1",
               "model": "voyage-3", "key_env": "VOYAGE_API_KEY"},
    "azure": {"base_url": "", "model": "text-embedding-3-small",
              "key_env": "AZURE_OPENAI_API_KEY"},
}

_NO_BACKEND_BLOCK = """╭─ RagKit：未检测到可用的向量后端 ─────────────────────────────╮
│ 本地 embedding 模型未安装，也未配置第三方 embedding API。     │
│ 任选其一完成配置后重跑本命令：                                │
│                                                              │
│ ① 安装本地模型（推荐：离线可用、零费用，下载约 1.2GB）        │
│    uv run {root}/scripts/ragkit_local_embed.py install       │
│    # 国内网络请先设置镜像：                                   │
│    export HF_ENDPOINT=https://hf-mirror.com                  │
│                                                              │
│ ② 配置第三方 embedding API（OpenAI 兼容，示例为通义）         │
│    uv run {root}/scripts/ragkit.py backend set \\
│        --provider qwen --kb <知识库路径>                      │
│    export DASHSCOPE_API_KEY=<你的密钥>                       │
│    # 其他 preset：openai / zhipu / voyage / azure，           │
│    # 或 --base-url 自定义任意 OpenAI 兼容端点；               │
│    # backend show 查看当前配置，backend reset 清除。          │
│                                                              │
│ 词汇路 + 元数据路检索不受影响，当前仍可降级使用。             │
╰──────────────────────────────────────────────────────────────╯"""


def plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def no_backend_block() -> str:
    return _NO_BACKEND_BLOCK.replace("{root}", str(plugin_root()))


def config_path(kb_root: Path) -> Path:
    return kb_root / ".ragkit" / "config.json"


def load_config(kb_root: Path) -> dict:
    p = config_path(kb_root)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save_config(kb_root: Path, cfg: dict) -> None:
    p = config_path(kb_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def hf_cache_dir() -> Path:
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def local_model_cached(model: str = DEFAULT_LOCAL_MODEL) -> bool:
    snap = hf_cache_dir() / ("models--" + model.replace("/", "--")) / "snapshots"
    return snap.is_dir() and any(snap.iterdir())


def cloud_configured(cfg: dict) -> bool:
    c = cfg.get("cloud") or {}
    return bool(c.get("base_url")) and bool(os.environ.get(c.get("key_env", ""), ""))


def resolve(cfg: dict) -> tuple[str, dict]:
    """Fixed priority: explicit cfg["backend"] > local cached > cloud configured > none."""
    local_model = cfg.get("local_model", DEFAULT_LOCAL_MODEL)
    explicit = cfg.get("backend", "")
    if explicit == "dummy":
        return "dummy", {}
    if explicit == "local":
        return ("local", {"model": local_model}) if local_model_cached(local_model) else ("none", {})
    if explicit == "cloud":
        return ("cloud", dict(cfg["cloud"])) if cloud_configured(cfg) else ("none", {})
    if local_model_cached(local_model):
        return "local", {"model": local_model}
    if cloud_configured(cfg):
        return "cloud", dict(cfg["cloud"])
    return "none", {}


def model_id(kind: str, opts: dict) -> str:
    if kind == "local":
        return f"local::{opts['model']}"
    if kind == "cloud":
        return f"cloud:{opts.get('provider', 'custom')}:{opts.get('model', '')}"
    if kind == "dummy":
        return "dummy::dummy"
    return ""


def encode(kind: str, opts: dict, texts: list[str]):
    if kind == "dummy":
        return _encode_dummy(texts)
    if kind == "cloud":
        return _encode_cloud(opts, texts)
    if kind == "local":
        return _encode_local(opts, texts)
    raise ValueError(f"no encode for backend kind {kind!r}")


def _normalize(arr):
    import numpy as np

    arr = np.asarray(arr, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _encode_dummy(texts: list[str]):
    """Deterministic bag-of-hashed-token vectors — hermetic offline test backend."""
    import numpy as np

    from .tokenizer import tokenize

    dim = 256
    out = np.zeros((len(texts), dim), dtype="float32")
    for i, t in enumerate(texts):
        for tok in tokenize(t):
            bucket = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % dim
            out[i, bucket] += 1.0
    return _normalize(out)


def _encode_cloud(opts: dict, texts: list[str]):
    url = opts["base_url"].rstrip("/") + "/embeddings"
    key = os.environ[opts["key_env"]]
    vecs: list = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start:start + _BATCH]
        req = urllib.request.Request(
            url, method="POST",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            data=json.dumps({"model": opts["model"], "input": batch}).encode("utf-8"),
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        rows = sorted(payload["data"], key=lambda r: r["index"])
        vecs.extend(r["embedding"] for r in rows)
    return _normalize(vecs)


def _encode_local(opts: dict, texts: list[str]):
    """Delegate to the sentence-transformers sidecar in its own uv env."""
    import numpy as np

    script = plugin_root() / "scripts" / "ragkit_local_embed.py"
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "texts.json"
        outp = Path(td) / "vecs.npy"
        inp.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
        res = subprocess.run(
            ["uv", "run", "--quiet", str(script), "encode",
             "--model", opts["model"], "--in", str(inp), "--out", str(outp)],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"local embed failed: {res.stderr.strip()[:500]}")
        return np.load(outp)
