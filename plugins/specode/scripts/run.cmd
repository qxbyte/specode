@echo off
REM specode plugin python launcher (Windows).
REM 优先用 py.exe Launcher——避开 Microsoft Store 的 App Execution Alias stub
REM （%LOCALAPPDATA%\Microsoft\WindowsApps\python{,3}.exe，跑起来只会打印
REM "Python was not found"），py launcher 不受 alias 影响。

where py >NUL 2>&1
if %ERRORLEVEL%==0 (
  py -3 %*
  exit /B %ERRORLEVEL%
)

where python3 >NUL 2>&1
if %ERRORLEVEL%==0 (
  python3 %*
  exit /B %ERRORLEVEL%
)

where python >NUL 2>&1
if %ERRORLEVEL%==0 (
  python %*
  exit /B %ERRORLEVEL%
)

echo specode: 未找到可用的 Python 解释器（已尝试 py / python3 / python）。 1>&2
echo         请从 python.org 安装 Python 3.8+，或在「设置 ^> 应用 ^> 高级应用设置 1>&2
echo         ^> 应用执行别名」中关闭 python.exe / python3.exe 的 Microsoft Store 别名。 1>&2
exit /B 127
