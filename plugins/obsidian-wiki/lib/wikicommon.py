# wikicommon.py
import os, re, json

def read_text(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")

def load_config(vault):
    p = os.path.join(vault, ".wiki", "config.json")
    if not os.path.isfile(p):
        raise SystemExit("错误：未找到配置 %s。请参考 obsidian-wiki/config.example.json 写一份。" % p)
    try:
        return json.loads(read_text(p))
    except json.JSONDecodeError as e:
        raise SystemExit("错误：配置 JSON 解析失败 %s：%s" % (p, e))

def require_vault(vault):
    if not vault:
        raise SystemExit("错误：必须用 --vault 指定 vault 根（外置代码不再从脚本位置推断）。")
    if not os.path.isdir(vault):
        raise SystemExit("错误：--vault 路径不存在：%s" % vault)
    return vault

def rel(vault, p):
    return os.path.relpath(p, vault).replace(os.sep, "/")

def iter_md(vault, dirs, skip_dirs):
    skip = set(skip_dirs or [])
    roots = [os.path.join(vault, d) for d in dirs] if dirs else [vault]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for cur, ds, files in os.walk(root):
            ds[:] = [d for d in ds if not d.startswith(".") and d not in skip]
            for f in files:
                if f.endswith(".md"):
                    yield os.path.join(cur, f)

_FENCE_RE = re.compile(r"(?:```|~~~).*?(?:```|~~~)", re.S)
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

def strip_fences(text):
    return _FENCE_RE.sub("", text)

def link_target(raw):
    return raw.split("|")[0].split("#")[0].rstrip("\\").strip()

def link_targets(text):
    out = []
    for raw in _LINK_RE.findall(strip_fences(text)):
        t = link_target(raw)
        if t and "<" not in t and "`" not in t and "..." not in t:
            out.append(t)
    return out

def frontmatter_keys(text):
    if not text.startswith("---"):
        return set()
    m = re.search(r"^---\s*$", text[3:], re.M)
    if m is None:
        return set()
    block = text[3:3 + m.start()]
    keys = set()
    for ln in block.split("\n"):
        if ln and not ln.startswith((" ", "\t", "-")) and ":" in ln:
            keys.add(ln.split(":", 1)[0].strip())
    return keys
