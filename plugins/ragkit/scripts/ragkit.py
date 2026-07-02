# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""RagKit CLI — standalone knowledge-base RAG.

Verbs: embed / query / status / eval / backend (embed & others land in later tasks).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag import backend, chunker, store  # noqa: E402
from rag.pipeline import DEFAULT_TOP, query_pipeline  # noqa: E402

_VECTOR_NOTES = {
    "ok": "",
    "no_index": "RagKit：索引不存在，请先运行 embed。",
    "no_vectors": "RagKit：索引缺向量（上次 embed 无可用后端），已降级词汇+元数据路；补好后端后重跑 embed。",
    "no_backend": "RagKit：无可用向量后端，已降级词汇+元数据路。",
    "model_mismatch": "RagKit：当前后端与索引向量模型不一致，向量路已跳过；请 embed --rebuild。",
    "skipped": "",
}


def cmd_query(args: argparse.Namespace) -> int:
    kb = Path(args.kb).resolve()
    channels_filter = args.channels.split(",") if args.channels else None
    out = query_pipeline(kb, args.text, top=args.top, channels_filter=channels_filter)
    note = _VECTOR_NOTES.get(out["vector_channel"], "")
    if note:
        print(note, file=sys.stderr)
        if out["vector_channel"] == "no_backend":
            print(backend.no_backend_block(), file=sys.stderr)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(_render_cards(out))
    return 0


def _render_cards(out: dict) -> str:
    lines = ["## RagKit 召回（供模型取舍，非事实来源）", ""]
    if out.get("index_stale"):
        lines.append("> ⚠️ 知识库比索引新，结果可能过时：建议重跑 embed。")
    if not out["results"]:
        lines.append("（无命中）")
    for i, r in enumerate(out["results"], 1):
        lines.append(
            f"{i}. [{r['category']} | {r['source']}] {r['title']} "
            f"(rrf {r['rrf_score']}, ranked_by: {'+'.join(r['ranked_by'])})"
        )
        if r["description"]:
            lines.append(f"   描述：{r['description']}")
        lines.append(f"   路径：{r['source_path']}")
    lines.append("")
    lines.append("> 以上为定位指针，事实以真实代码/文档为准；读全文请打开「路径」对应文件。")
    return "\n".join(lines)


def cmd_embed(args: argparse.Namespace) -> int:
    import numpy as np

    kb = Path(args.kb).resolve()
    if not kb.is_dir():
        print(f"RagKit：知识库目录不存在：{kb}（fresh 项目属正常，先产出 knowledge-base 再来）")
        return 1
    chunks = chunker.chunk_kb(kb)
    if not chunks:
        n_md = sum(len(list((kb / s).glob("*.md"))) for s in ("cases", "navigation") if (kb / s).is_dir())
        if n_md == 0:
            print(f"RagKit：{kb} 下没有任何 cases/navigation md 文件，0 chunks（fresh 项目属正常）。")
        else:
            print(f"RagKit：发现 {n_md} 个 md 但切出 0 chunks——请检查文档是否有正文/标题结构。")
        return 1

    cfg = backend.load_config(kb)
    kind, opts = backend.resolve(cfg)
    if kind == "none":
        store.save_index(kb, chunks, None, "")
        print(f"RagKit：已构建词汇/元数据索引（{len(chunks)} chunks，无向量）。")
        print(backend.no_backend_block())
        return backend.EXIT_NO_BACKEND

    mid = backend.model_id(kind, opts)
    old_hashes = store.load_manifest(kb).get("hashes", {})
    old_chunks = store.load_chunks(kb)
    old_vecs = store.load_vectors(kb)
    old_row = {c["chunk_id"]: i for i, c in enumerate(old_chunks)}
    can_reuse = (not args.rebuild and old_vecs is not None
                 and store.load_model_id(kb) == mid and len(old_chunks) == len(old_vecs))

    todo = [c for c in chunks
            if not (can_reuse and old_hashes.get(c.chunk_id) == c.text_hash and c.chunk_id in old_row)]
    store.save_index(kb, chunks, None, "")   # lexical-first: survive encode failure
    new_vecs = backend.encode(kind, opts, [c.text for c in todo]) if todo else None
    dim = (new_vecs.shape[1] if new_vecs is not None else old_vecs.shape[1])
    vectors = np.zeros((len(chunks), dim), dtype="float32")
    todo_ids = {c.chunk_id for c in todo}
    j = 0
    for i, c in enumerate(chunks):
        if c.chunk_id in todo_ids:
            vectors[i] = new_vecs[j]
            j += 1
        else:
            vectors[i] = old_vecs[old_row[c.chunk_id]]
    store.save_index(kb, chunks, vectors, mid)
    print(f"RagKit embed 完成：{len(chunks)} chunks（new {len(todo)} / reused {len(chunks) - len(todo)}），backend = {mid}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from rag.pipeline import index_stale

    kb = Path(args.kb).resolve()
    chunks = store.load_chunks(kb)
    disk_ids = sorted(
        p.stem for s in ("cases", "navigation") if (kb / s).is_dir()
        for p in (kb / s).glob("*.md")
    )
    indexed_ids = sorted({c["knowledge_id"] for c in chunks})
    kind, _opts = backend.resolve(backend.load_config(kb))
    s = {
        "kb": str(kb),
        "index_exists": bool(chunks),
        "n_docs_on_disk": len(disk_ids),
        "n_docs_indexed": len(indexed_ids),
        "n_chunks": len(chunks),
        "model_id": store.load_model_id(kb),
        "backend_resolved": kind,
        "index_stale": index_stale(kb) if chunks else False,
        "drift": {
            "missing_from_index": [i for i in disk_ids if i not in indexed_ids],
            "deleted_on_disk": [i for i in indexed_ids if i not in disk_ids],
        },
    }
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
    else:
        for k, v in s.items():
            print(f"{k}: {v}")
    if kind == "none":
        print(backend.no_backend_block())
    return 0


def cmd_backend(args: argparse.Namespace) -> int:
    kb = Path(args.kb).resolve()
    if args.action == "set":
        preset = backend.PRESETS.get(args.provider)
        if preset is None:
            print(f"未知 provider：{args.provider}。可选：{', '.join(backend.PRESETS)}")
            return 1
        cloud = {"provider": args.provider,
                 "base_url": args.base_url or preset["base_url"],
                 "model": args.model or preset["model"],
                 "key_env": args.key_env or preset["key_env"]}
        if not cloud["base_url"]:
            print("azure 需要显式 --base-url")
            return 1
        cfg = backend.load_config(kb)
        cfg["cloud"] = cloud
        backend.save_config(kb, cfg)
        print(json.dumps(cloud, ensure_ascii=False))
        print(f"已写入 {backend.config_path(kb)}。请确保环境变量 {cloud['key_env']} 已设置（密钥不落盘）。")
        return 0
    if args.action == "show":
        print(json.dumps(backend.load_config(kb), ensure_ascii=False, indent=2))
        return 0
    if args.action == "reset":
        cfg = backend.load_config(kb)
        cfg.pop("cloud", None)
        cfg.pop("backend", None)
        backend.save_config(kb, cfg)
        print("已清除后端配置，回到默认解析顺序（本地优先）。")
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ragkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="multi-channel recall")
    q.add_argument("text")
    q.add_argument("--kb", default="./knowledge-base")
    q.add_argument("--top", type=int, default=DEFAULT_TOP)
    q.add_argument("--json", action="store_true")
    q.add_argument("--channels", default="")
    q.set_defaults(func=cmd_query)

    e = sub.add_parser("embed", help="chunk + vectorize knowledge-base")
    e.add_argument("--kb", default="./knowledge-base")
    e.add_argument("--rebuild", action="store_true")
    e.set_defaults(func=cmd_embed)

    st = sub.add_parser("status", help="index health / drift")
    st.add_argument("--kb", default="./knowledge-base")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    b = sub.add_parser("backend", help="cloud backend config")
    b.add_argument("action", choices=["set", "show", "reset"])
    b.add_argument("--kb", default="./knowledge-base")
    b.add_argument("--provider", default="")
    b.add_argument("--model", default="")
    b.add_argument("--base-url", default="")
    b.add_argument("--key-env", default="")
    b.set_defaults(func=cmd_backend)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
