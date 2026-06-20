# wikicommon.py
import os, re, json

def read_text(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")

def config_home():
    """家目录配置根：$OBSIDIAN_WIKI_CONFIG_DIR 优先，否则 ${XDG_CONFIG_HOME:-~/.config}/obsidian-wiki。"""
    base = os.environ.get("OBSIDIAN_WIKI_CONFIG_DIR")
    if base:
        return base
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(xdg, "obsidian-wiki")

def registry_path():
    return os.path.join(config_home(), "vaults.json")

def load_registry():
    """读多库注册表 {active, vaults:{<名>:{path}}}；不存在则返回空壳。"""
    p = registry_path()
    if not os.path.isfile(p):
        return {"active": None, "vaults": {}}
    try:
        d = json.loads(read_text(p))
    except json.JSONDecodeError as e:
        raise SystemExit("错误：注册表 JSON 解析失败 %s：%s" % (p, e))
    d.setdefault("active", None)
    d.setdefault("vaults", {})
    return d

def _registry_config_for(vault):
    """按 vault 绝对路径在注册表里匹配库，返回其家目录配置路径；找不到返回 None。"""
    want = os.path.realpath(vault)
    for name, meta in load_registry()["vaults"].items():
        p = meta.get("path")
        if p and os.path.realpath(p) == want:
            return os.path.join(config_home(), "configs", name + ".json")
    return None

def load_config(vault):
    """优先家目录注册表 configs/<名>.json（按 --vault 路径匹配）；未注册则回退库内 <vault>/.wiki/config.json。"""
    p = _registry_config_for(vault)
    if p is None:
        p = os.path.join(vault, ".wiki", "config.json")
    if not os.path.isfile(p):
        raise SystemExit(
            "错误：未找到配置 %s。\n"
            "  · 家目录注册表：%s（用 registry.py register 注册本库，并把 config.example.json 抄到 configs/<名>.json）\n"
            "  · 或库内回退：<vault>/.wiki/config.json\n"
            "  模板见插件根 config.example.json。" % (p, registry_path()))
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
