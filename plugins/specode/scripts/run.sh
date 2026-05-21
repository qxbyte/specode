#!/bin/sh
# specode plugin python launcher (POSIX / Git Bash / MSYS).
# 依次探测 python3 / python / py，找到就 exec 并透传所有参数。
#
# Windows 注意：PATH 上的 python.exe / python3.exe 可能是 Microsoft Store 的
# App Execution Alias stub（路径形如 .../WindowsApps/python3.exe，跑起来只会
# 打印 "Python was not found" 并 exit 49）。这里通过路径模式跳过这种 stub，
# 继续探测真实解释器（通常落在 py launcher 上）。

set -u

_specode_is_alias_stub() {
  case "$1" in
    */WindowsApps/python.exe|*/WindowsApps/python3.exe) return 0 ;;
    */WindowsApps/python|*/WindowsApps/python3) return 0 ;;
  esac
  return 1
}

p3="$(command -v python3 2>/dev/null || true)"
if [ -n "$p3" ] && ! _specode_is_alias_stub "$p3"; then
  exec "$p3" "$@"
fi

p="$(command -v python 2>/dev/null || true)"
if [ -n "$p" ] && ! _specode_is_alias_stub "$p"; then
  exec "$p" "$@"
fi

if command -v py >/dev/null 2>&1; then
  exec py -3 "$@"
fi

printf '%s\n' "specode: 未找到可用的 Python 解释器（已尝试 python3 / python / py）。" >&2
printf '%s\n' "        请安装 Python 3.8+ 并确保其位于 PATH 中后再次重试。" >&2
printf '%s\n' "        Windows 用户：若提示 \"Python was not found\"，多半是命中了 Microsoft" >&2
printf '%s\n' "        Store 的 python.exe 别名 stub。请从 python.org 安装真 Python，或在" >&2
printf '%s\n' "        「设置 > 应用 > 高级应用设置 > 应用执行别名」中关闭 python.exe /" >&2
printf '%s\n' "        python3.exe 的 Microsoft Store 别名。" >&2
exit 127
