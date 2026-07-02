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

from rag import backend  # noqa: E402
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
