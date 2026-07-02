#!/bin/sh
# RagKit runner: prefer uv (resolves PEP 723 inline deps automatically),
# fall back to bare python3/python/py (user must have numpy installed).
script="$1"; shift
if command -v uv >/dev/null 2>&1; then
  exec uv run --quiet "$script" "$@"
fi
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1; then
    exec "$py" "$script" "$@"
  fi
done
echo "RagKit: 未找到 uv 或 Python。推荐安装 uv：brew install uv（或 pip install uv）" >&2
exit 1
