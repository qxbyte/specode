#!/usr/bin/env python3
# registry.py —— 家目录多库注册表（~/.config/obsidian-wiki/vaults.json）
# 维护「哪些 vault、各自路径、当前 active」，并为每个库在 configs/<名>.json 存其结构配置。
import os, sys, json, argparse, shutil
sys.path.insert(0, os.path.dirname(__file__))
import wikicommon as wc

def _save(reg):
    home = wc.config_home()
    os.makedirs(os.path.join(home, "configs"), exist_ok=True)
    with open(wc.registry_path(), "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write("\n")

def cmd_list(args):
    print(json.dumps(wc.load_registry(), ensure_ascii=False, indent=2))

def cmd_resolve(args):
    reg = wc.load_registry()
    name = args.name or reg.get("active")
    if not name or name not in reg["vaults"]:
        sys.stderr.write("未配置：无 active 库或指定库不存在。先 registry.py register。\n")
        raise SystemExit(3)
    cfg = os.path.join(wc.config_home(), "configs", name + ".json")
    print(json.dumps({
        "name": name,
        "path": reg["vaults"][name].get("path"),
        "config": cfg,
        "config_exists": os.path.isfile(cfg),
    }, ensure_ascii=False))

def cmd_register(args):
    if not os.path.isdir(args.path):
        raise SystemExit("错误：路径不存在：%s" % args.path)
    reg = wc.load_registry()
    reg["vaults"][args.name] = {"path": os.path.abspath(args.path)}
    if args.activate or not reg.get("active"):
        reg["active"] = args.name
    _save(reg)
    cfg = os.path.join(wc.config_home(), "configs", args.name + ".json")
    if args.config_from and not os.path.isfile(cfg):
        shutil.copyfile(args.config_from, cfg)
    print("已注册 %s -> %s（active=%s）；配置 %s%s" % (
        args.name, reg["vaults"][args.name]["path"], reg["active"], cfg,
        "" if os.path.isfile(cfg) else " [缺：把 config.example.json 抄过来]"))

def cmd_set_active(args):
    reg = wc.load_registry()
    if args.name not in reg["vaults"]:
        raise SystemExit("错误：未注册的库：%s" % args.name)
    reg["active"] = args.name
    _save(reg)
    print("active = %s" % args.name)

def main():
    ap = argparse.ArgumentParser(prog="registry", description="obsidian-wiki 家目录多库注册表")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="打印整个注册表")
    r = sub.add_parser("resolve", help="解析 active（或 --name）库的 path/config；未配置 exit 3")
    r.add_argument("--name")
    g = sub.add_parser("register", help="注册/更新一个库")
    g.add_argument("--name", required=True)
    g.add_argument("--path", required=True)
    g.add_argument("--activate", action="store_true", help="设为 active（首个库自动 active）")
    g.add_argument("--config-from", help="把该模板复制为 configs/<名>.json（已存在则跳过）")
    s = sub.add_parser("set-active", help="切换 active 库")
    s.add_argument("--name", required=True)
    args = ap.parse_args()
    {"list": cmd_list, "resolve": cmd_resolve,
     "register": cmd_register, "set-active": cmd_set_active}[args.cmd](args)

if __name__ == "__main__":
    main()
