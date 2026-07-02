import json

import numpy as np

from rag import store


def test_embed_no_backend_builds_lexical_index_and_exits_3(kb, run_cli):
    res = run_cli("embed", "--kb", str(kb))
    assert res.returncode == 3
    assert "未检测到可用的向量后端" in res.stdout
    assert "ragkit_local_embed.py install" in res.stdout
    assert store.load_chunks(kb)          # chunks.json built anyway
    assert store.load_vectors(kb) is None


def test_embed_zero_chunks_explained(tmp_path, run_cli, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    missing = tmp_path / "nope" / "knowledge-base"
    res = run_cli("embed", "--kb", str(missing))
    assert res.returncode == 1
    assert "不存在" in res.stdout


def test_embed_dummy_backend_full_and_incremental(kb, run_cli):
    run_cli("backend", "set", "--provider", "qwen", "--kb", str(kb))  # writes .ragkit/config.json
    cfg = json.loads((kb / ".ragkit" / "config.json").read_text(encoding="utf-8"))
    cfg["backend"] = "dummy"
    (kb / ".ragkit" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    res = run_cli("embed", "--kb", str(kb))
    assert res.returncode == 0, res.stderr
    n = len(store.load_chunks(kb))
    assert store.load_vectors(kb).shape[0] == n
    assert store.load_model_id(kb) == "dummy::dummy"

    # incremental: touch one doc, only its chunks re-embed (reused count in output)
    doc = kb / "cases" / "114371-mask-rule.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\n补充一行。\n", encoding="utf-8")
    res2 = run_cli("embed", "--kb", str(kb))
    assert res2.returncode == 0
    assert "reused" in res2.stdout
    vecs = store.load_vectors(kb)
    assert vecs.shape[0] == len(store.load_chunks(kb))
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-4)


def test_backend_show_and_reset(kb, run_cli):
    run_cli("backend", "set", "--provider", "zhipu", "--kb", str(kb))
    res = run_cli("backend", "show", "--kb", str(kb))
    assert "bigmodel.cn" in res.stdout and "ZHIPUAI_API_KEY" in res.stdout
    run_cli("backend", "reset", "--kb", str(kb))
    res2 = run_cli("backend", "show", "--kb", str(kb))
    assert "bigmodel.cn" not in res2.stdout


def test_embed_lexical_index_survives_encode_failure(kb, run_cli, monkeypatch):
    (kb / ".ragkit").mkdir(exist_ok=True)
    (kb / ".ragkit" / "config.json").write_text(
        '{"cloud": {"provider": "qwen", "base_url": "http://127.0.0.1:1",'
        ' "model": "m", "key_env": "TEST_RAGKIT_KEY"}}', encoding="utf-8")
    monkeypatch.setenv("TEST_RAGKIT_KEY", "sk-test")
    res = run_cli("embed", "--kb", str(kb))
    assert res.returncode != 0          # encode against 127.0.0.1:1 fails fast
    assert store.load_chunks(kb)        # lexical index survived
    assert store.load_vectors(kb) is None
