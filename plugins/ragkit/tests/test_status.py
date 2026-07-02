import json


def _dummy_index(kb, run_cli):
    (kb / ".ragkit").mkdir(exist_ok=True)
    (kb / ".ragkit" / "config.json").write_text('{"backend": "dummy"}', encoding="utf-8")
    run_cli("embed", "--kb", str(kb))


def test_status_healthy(kb, run_cli):
    _dummy_index(kb, run_cli)
    res = run_cli("status", "--kb", str(kb), "--json")
    assert res.returncode == 0
    s = json.loads(res.stdout)
    assert s["index_exists"] is True
    assert s["n_docs_on_disk"] == 3 and s["n_docs_indexed"] == 3
    assert s["model_id"] == "dummy::dummy"
    assert s["backend_resolved"] == "dummy"
    assert s["drift"] == {"missing_from_index": [], "deleted_on_disk": []}


def test_status_detects_drift_and_staleness(kb, run_cli):
    _dummy_index(kb, run_cli)
    (kb / "cases" / "999-new-doc.md").write_text(
        "---\n标题: 新\n类型: case\ntags: [x]\n描述: d\n---\n\n## a\nb\n", encoding="utf-8")
    (kb / "navigation" / "cod-receipt-page.md").unlink()
    res = run_cli("status", "--kb", str(kb), "--json")
    s = json.loads(res.stdout)
    assert s["drift"]["missing_from_index"] == ["999-new-doc"]
    assert s["drift"]["deleted_on_disk"] == ["cod-receipt-page"]
    assert s["index_stale"] is True


def test_status_no_backend_prints_block(kb, run_cli):
    res = run_cli("status", "--kb", str(kb))
    assert res.returncode == 0
    assert "未检测到可用的向量后端" in res.stderr


def test_status_json_is_pure_json_even_without_backend(kb, run_cli):
    import json as _json
    res = run_cli("status", "--kb", str(kb), "--json")
    assert res.returncode == 0
    payload = _json.loads(res.stdout)   # must not raise
    assert payload["backend_resolved"] == "none"
    assert "未检测到可用的向量后端" in res.stderr
