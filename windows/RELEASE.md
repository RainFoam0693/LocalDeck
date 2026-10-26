Windows 桌面版，适用于 Windows 10/11 x64。

- 自动发现本机 TCP 监听进程，显示名称、PID、端口、命令和工作目录。
- 支持浏览器打开服务、打开目录、确认后停止外部进程。
- 支持添加命令启动项，以及启动、停止、重启、查看日志。
- 深色界面，沿用 LocalDeck 图标。
- 内置 Python 与 Tcl/Tk，下载 EXE 后双击运行，也可以直接放到桌面。

下载 `.exe` 或包含说明文件的 `.zip`。校验值见 `SHA256SUMS-Windows.txt`。

命令通过 `cmd.exe` 执行。暂不支持交互式终端；退出软件会停止它启动的任务。配置与日志保存在 `%LOCALAPPDATA%\LocalDeck`。受保护进程可能无法读取或停止；应用不要求管理员权限。

该版本没有 Authenticode 签名，Windows 可能显示未知发布者提示。请先保存工作，Windows 的停止操作会终止目标进程。
