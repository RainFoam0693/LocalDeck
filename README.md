# LocalDeck for macOS & Windows

<img src="assets/LocalDeck.png" width="128" alt="LocalDeck 应用图标">

本机 API、前端服务与终端任务的桌面管理软件。Mac 版使用 SwiftUI，Windows 版使用 Qt 6（Windows 11 Fluent 风格）；共用带鉴权的本机 API。

## 下载

安装包见 [GitHub Releases](https://github.com/RainFoam0693/LocalDeck/releases)。当前仓库为私有，仅有权限的账号可以访问。

## 打开

双击 `dist/LocalDeck.app`，可拖到「应用程序」。需要 macOS 13+ 和 Python 3（当前开发机已具备）。本地临时签名，尚未做 Apple 公证；其他机器需自行构建或处理系统信任提示。

- **运行中的服务**：扫描当前用户可访问的 TCP 监听进程，显示 PID、端口、命令和目录；点击端口用 HTTP 打开，点击目录在 Finder 打开。
- **停止**：确认后向现有进程发送 SIGTERM，不提权，不批量停止。
- **我的启动项**：名称、目录、zsh 命令；支持启动、停止、重启、最近 100 KB 日志。
- **终端任务**：可托管脚本和非交互命令，启动项继续保存日志；交互式命令可在「应用内终端」中运行，不读取其他终端软件的历史输出。
- 每 4 秒刷新。已有外部服务只能发现、打开或停止；要重启和收集日志，需要添加启动项。
- 退出应用会停止由它启动的任务；已有外部服务不受影响。配置和日志保存在 `~/Library/Application Support/LocalDeck`。日志当前不自动轮转。

## 构建与验证

```sh
./scripts/build.sh
python3 scripts/test_backend.py
./scripts/package.sh --skip-build
```

构建要求 Xcode Command Line Tools，首次构建会通过 SwiftPM 下载固定版本的 SwiftTerm。编译产物为 `dist/LocalDeck.app`。打包脚本另外生成 DMG（含 Applications 快捷方式）、ZIP 和 SHA-256 校验文件。图标由 `scripts/make-icon.swift` 绘制并生成完整尺寸的 ICNS。

## macOS 原生窗口控件（0.4.1）

Mac 版显式使用当前 Xcode SDK 编译和链接，避免把最低兼容版本误写为链接 SDK。macOS 27 使用系统原生窗口控制按钮及其系统动效；最低运行版本仍为 macOS 13。构建脚本会检查实际链接 SDK 与当前 SDK 的主版本是否一致。

## 性能看板与新界面（0.4.0）

两端采用侧边导航、实时性能卡片、可选择的服务卡片及独立详情面板。搜索名称、端口或命令，切换 CPU 排序后可优先查看占用较高的服务；命令和目录在详情中查看，列表保留关键状态。

- 系统 CPU、物理内存的使用比例与近 2 分钟趋势；性能数据每 2 秒在后台采样。
- LocalDeck 自身的 CPU、驻留内存（MB/GB）和物理内存占比；不合并用户任务或终端 Shell 的占用。
- 服务进程的 CPU、驻留内存及内存占比。托管启动项合并其进程树的占用。
- CPU 按整机逻辑核心总容量归一化为 0–100%，与单核心可以达到 100% 的显示方式不同。
- 内存比例以物理内存为分母。Windows 使用系统可用内存，Mac 可用内存按 free + inactive 计算，包含可回收缓存；与系统活动监视器的统计口径可能不同。进程内存是 RSS，共享页面可能重复计入。
- 首次 CPU 采样、受保护进程或采集失败显示“—”，不会用虚构数值填补。

验证：`python scripts/test_performance.py`，覆盖 CPU 归一化、PID 重用、无权限数据、进程树汇总和真实系统采样。

## 应用内终端（0.3.0）

Mac 和 Windows 都提供独立的终端工作区，可同时打开多个终端标签。切换终端标签或切到服务列表、启动项页面，只改变可见界面；会话、当前目录、环境变量、运行中的命令和输出都保留。终端会话仅在当前应用运行期间存在，不会在退出后恢复。

- Mac：原生 SwiftTerm + zsh 伪终端，支持 ANSI/VT 输出、方向键、Tab、Ctrl+C、⌘C/⌘V 和滚动历史。
- Windows：pywinpty 伪终端 + pyte VT 屏幕，支持 CMD、PowerShell、方向键、Tab、Ctrl+C、Ctrl+Shift+C/V、颜色和窗口尺寸变化。
- 可在指定目录新建终端；关闭标签会确认并停止该会话，其他终端继续运行。退出应用会清理全部终端。
- 退出应用前检查终端任务：有前台或后台任务时默认取消，并提供“结束任务并退出”；空闲 Shell 或没有终端时直接退出。Mac 关闭最后一个窗口和 Cmd+Q 都遵循同一检查。
- 内置终端不提供 SSH 自动重连、分屏或跨应用退出恢复。Windows 的 VT 实现与 Mac 的完整 xterm 仿真存在差异，复杂全屏程序的兼容性可能不同。

Mac 终端烟雾测试：`dist/LocalDeck.app/Contents/MacOS/LocalDeck --terminal-smoke-test`，结果写入 `/tmp/localdeck-mac-terminal-smoke.json`。Windows 的 `--terminal-smoke-test` 会检查双标签隔离、切换页面继续输出、缩放、Ctrl+C、单标签关闭和退出清理；源码和打包 EXE 都会在 CI 中执行。

## 终端文件与设置

两端终端均提供可收起的文件面板，支持目录导航、隐藏文件、新建、重命名、复制路径和移到废纸篓／回收站。右键可以在当前终端 cd 到目录，或在该目录新建终端；正在执行命令时不会发送 cd。PowerShell 支持特殊字符路径，CMD 对含 `%`、`!` 或 UNC 的路径提示改用 PowerShell。文件面板显示状态会保存。

向上翻阅日志后，新输出保留阅读位置；回到底部才恢复跟随。Windows 在历史缓存淘汰旧行时按日志行保持位置；Mac 构建时为固定版本 SwiftTerm 应用 `scripts/patch-swiftterm.py` 中的滚动修复，请使用 `scripts/build.sh` 构建。

圆形齿轮打开设置，可切换外观、文件面板及隐藏文件，关于页提供开发者 GitHub 主页卡片。Mac 提供“完全磁盘访问权限”的系统设置入口，权限需用户在系统中手动授予；Windows 使用当前账户权限及 Windows 11 风格控件。液态玻璃仅用于 Mac。Mac 文件列表采用原生表格，目录选择使用非阻塞窗口。

## Mac 原生玻璃

macOS 26 及以上的操作按钮使用 SwiftUI 原生 `.glass` / `.glassProminent` 样式。顶部主导航与主题胶囊使用原生 `Picker`：macOS 27 及以上采用 `.tabs`，旧系统采用 `.segmented`。顶栏使用系统 bar 材质，列表、性能数据和终端正文保留实色背景。支持深浅色与跟随系统；透明度和动态效果遵循系统辅助功能设置。不使用自绘折射、手动玻璃珠动画或私有 API。

## 外观切换

Mac 顶栏右侧、Windows 侧栏底部提供三段小胶囊：太阳（浅色）、月亮（深色）、显示器（跟随系统）。图标使用 SF Symbols / 单色矢量绘制，不使用 emoji。默认跟随系统，手动选择会保存；界面、日志及终端一起换色，切换外观不会重建或停止终端会话。Mac 的主导航已移至顶部：服务概览、启动项、终端工作区共用原生页签，左侧不再保留重复导航；品牌位于顶栏左侧，主题胶囊位于右侧。Mac 胶囊的布局空间为 165×44 点，使用系统大尺寸选择器，macOS 27 及以上采用原生 `.tabs` 样式；外观、选中滑块及交互全部交由 SwiftUI 处理，不包含自定义玻璃珠、放大、拖动或弹簧动画。Liquid Glass 材质从 macOS 26 起提供；macOS 27 起提供新版原生 tabs 选择交互，旧系统使用自身支持的普通分段控件。

## Windows 版

0.5.0 重写 Windows 界面：统一深色控件、圆角面板、Windows UI 字体、高 DPI 缩放与轻量滚动条。保留系统原生标题栏及 Snap Layouts，通过公开 DWM API 请求深色标题栏、圆角和 Mica；Mica 需要 22H2 及以上，并服从系统设置。界面由 Qt 实现，并非 WinUI。macOS 界面与构建不受影响。

最新安装包放在 [Releases](https://github.com/RainFoam0693/LocalDeck/releases)。Windows 选择 `LocalDeck-0.7.0-Windows-x64.exe`，双击运行；也可选择包含说明和第三方许可的 ZIP。适用于 Windows 11 x64（内部版本 22000 及以上），不再支持 Windows 10，无需安装 Python 或 Qt。macOS Apple Silicon 选择 DMG 或 macOS ZIP。当前包未做 Apple 公证或 Windows Authenticode 签名。

功能包括 TCP 监听进程扫描、搜索、打开浏览器和目录、确认后停止进程、命令启动项、启停/重启和最近 100 KB 日志。Windows 命令通过 `cmd.exe /d /s /c` 执行；配置与日志在 `%LOCALAPPDATA%\LocalDeck`。受保护进程可能无法读取信息或停止，程序不会请求提权。Windows 停止操作会终止目标进程；托管任务会同时停止其子进程。使用 `start` 等脱离管理 shell 的任务可能继续运行。「应用内终端」支持独立的 CMD / PowerShell 会话。

开发和打包（在 Windows PowerShell 中）：

```powershell
python -m pip install -r windows/requirements.txt
python windows/app.py
python scripts/test_backend.py
./windows/build.ps1
```

GitHub Actions 会在 Windows runner 上执行真实 TCP 服务测试、桌面 UI 冒烟测试、PyInstaller 打包以及打包后的 EXE 冒烟测试。推送 `windows-v*` 标签会自动发布 Windows 版本。输出为 `dist/LocalDeck-0.7.0-Windows-x64.exe`、ZIP 和 SHA-256 校验文件。

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

Windows 本机 API 始终直连 127.0.0.1，不使用系统代理；回归验证：`python windows/test_api_client.py`。

终端标签会自动显示正在运行的进程或入口脚本名称（如 Yunzai、Vite、server.py），保留会话编号；悬停查看 PID 和工作目录，任务结束后恢复原标签。识别不到具体项目时显示进程名称。


### 应用内更新

设置中提供手动检查、自动检查开关和下载入口。默认每周一、三、五，在应用运行时按本地日期每天检查一次；关闭应用时不会启动后台定时任务。发现新版后，页面顶部显示提示，用户确认后才下载，稍后处理不会结束终端任务。

更新按当前系统与架构选择 GitHub Releases 中的正式安装包，忽略预发布、草稿和旧版本。下载到系统“下载”目录的 `LocalDeck Updates` 文件夹，并校验 SHA-256。macOS 打开 DMG 后退出旧版并替换应用；Windows 打开下载位置，退出旧版后用新 EXE 替换原文件。现有配置保留，运行中的终端任务不会迁移。

公开仓库无需配置。私有仓库可在设置中保存 GitHub fine-grained 访问令牌，限定 LocalDeck 仓库的 **Contents → Read-only** 权限；macOS 使用系统钥匙串，Windows 使用凭据管理器，令牌不会写入普通配置文件或打包进软件。无法授权时仍可通过“GitHub 发行页”登录下载。

发布时，版本标签使用 `vX.Y.Z`、`macos-vX.Y.Z` 或 `windows-vX.Y.Z`；安装包名称为 `LocalDeck-X.Y.Z-macOS-arm64.dmg` 或 `LocalDeck-X.Y.Z-Windows-x64.exe`（其他架构相应替换）。校验使用 GitHub 资产的 `sha256` digest；旧资产需同时上传 `SHA256SUMS-macOS.txt` / `SHA256SUMS-Windows.txt`。未发布到 Releases 的 Actions 构建不会被当作正式更新。

### SSH 服务器

顶部的「SSH 服务器」可添加、编辑、删除和保存服务器名称、主机、端口、用户名及可选私钥路径。点击连接后，在终端工作区建立独立 SSH 标签；切换页面不会断开连接，退出应用前会提醒仍在运行的 SSH 会话。

使用系统 OpenSSH 客户端，支持交互式密码、密钥口令与 SSH Agent，不在配置中保存密码或复制私钥。首次连接由 OpenSSH 提示核对主机指纹，后续沿用系统 known_hosts。Windows 需要安装「OpenSSH 客户端」可选功能。文件浏览器仍管理本机文件，不提供远程 SFTP。
