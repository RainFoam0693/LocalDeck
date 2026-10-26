# LocalDeck for macOS & Windows

<img src="assets/LocalDeck.png" width="128" alt="LocalDeck 应用图标">

本机 API、前端服务与终端任务的桌面管理软件。Mac 版使用 SwiftUI，Windows 版使用 Tk；共用带鉴权的本机 API。

## 下载

安装包见 [GitHub Releases](https://github.com/RainFoam0693/LocalDeck/releases)。当前仓库为私有，仅有权限的账号可以访问。

## 打开

双击 `dist/LocalDeck.app`，可拖到「应用程序」。需要 macOS 13+ 和 Python 3（当前开发机已具备）。本地临时签名，尚未做 Apple 公证；其他机器需自行构建或处理系统信任提示。

- **运行中的服务**：扫描当前用户可访问的 TCP 监听进程，显示 PID、端口、命令和目录；点击端口用 HTTP 打开，点击目录在 Finder 打开。
- **停止**：确认后向现有进程发送 SIGTERM，不提权，不批量停止。
- **我的启动项**：名称、目录、zsh 命令；支持启动、停止、重启、最近 100 KB 日志。
- **终端任务**：可托管脚本和非交互命令，目前没有完整交互式终端/TTY，也不读取其他终端软件的历史输出。
- 每 4 秒刷新。已有外部服务只能发现、打开或停止；要重启和收集日志，需要添加启动项。
- 退出应用会停止由它启动的任务；已有外部服务不受影响。配置和日志保存在 `~/Library/Application Support/LocalDeck`。日志当前不自动轮转。

## 构建与验证

```sh
./scripts/build.sh
python3 scripts/test_backend.py
./scripts/package.sh --skip-build
```

构建要求 Xcode Command Line Tools。编译产物为 `dist/LocalDeck.app`。打包脚本另外生成 DMG（含 Applications 快捷方式）、ZIP 和 SHA-256 校验文件。图标由 `scripts/make-icon.swift` 绘制并生成完整尺寸的 ICNS。

## Windows 版

适用于 Windows 10/11 x64。下载 [Windows Release](https://github.com/RainFoam0693/LocalDeck/releases/tag/windows-v0.2.0) 中的 EXE 或 ZIP，双击运行；可以放在桌面，内置 Python 与 Tcl/Tk，无需另外安装运行时。当前 Windows 包未做 Authenticode 签名。

功能包括 TCP 监听进程扫描、搜索、打开浏览器和目录、确认后停止进程、命令启动项、启停/重启和最近 100 KB 日志。Windows 命令通过 `cmd.exe /d /s /c` 执行；配置与日志在 `%LOCALAPPDATA%\LocalDeck`。受保护进程可能无法读取信息或停止，程序不会请求提权。Windows 停止操作会终止目标进程；托管任务会同时停止其子进程。使用 `start` 等脱离管理 shell 的任务可能继续运行。暂不支持交互式终端。

开发和打包（在 Windows PowerShell 中）：

```powershell
python -m pip install -r windows/requirements.txt
python windows/app.py
python scripts/test_backend.py
./windows/build.ps1
```

GitHub Actions 会在 Windows runner 上执行真实 TCP 服务测试、桌面 UI 冒烟测试、PyInstaller 打包以及打包后的 EXE 冒烟测试。推送 `windows-v*` 标签会自动发布 Windows 版本。输出为 `dist/LocalDeck-0.2.0-Windows-x64.exe`、ZIP 和 SHA-256 校验文件。

## 后端 API

应用自动启动后端，绑定 `127.0.0.1` 随机端口，使用每次启动生成的 Bearer Token，不向局域网暴露。可以独立启动：

```sh
python3 backend/server.py --port 8765
```

第一行 JSON 返回端口和 token，请求须带 `Authorization: Bearer <token>`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/state` | 服务配置、运行状态、监听进程 |
| POST | `/services` | 创建；JSON: name, command, directory |
| POST | `/services/{id}/start` | 启动 |
| POST | `/services/{id}/stop` | 停止任务进程组 |
| POST | `/services/{id}/restart` | 重启 |
| POST | `/services/{id}/delete` | 停止并删除 |
| GET | `/logs/{id}` | 最近 100 KB 日志 |
| POST | `/processes/stop` | 停止外部监听进程；JSON: pid, command，校验进程命令仍匹配 |

配置支持 `LOCALDECK_DATA_DIR` 环境变量覆盖，便于隔离测试。Mac 启动项通过当前用户的 `/bin/zsh -lc` 执行，Windows 使用 `cmd.exe`，适用于自己信任的本机命令。守护进程化或主动脱离进程组的命令不保证退出时被回收。
