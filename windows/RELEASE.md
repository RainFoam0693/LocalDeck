## 下载

Windows 11 x64 用户下载 **LocalDeck-0.5.1-Windows-x64.exe**，关闭旧版后双击新版即可，无需安装 Python。ZIP 包含使用说明和许可文件。

## 修复

- 修复开启系统代理后，占用信息和端口列表一直为空、底部显示 `Expecting value` 的问题。本机 API 改为直接连接 127.0.0.1，不经过系统代理；不用关闭代理或更改系统设置。
- 改进 API 错误提示，避免把非 JSON 的响应直接显示为难懂的解析错误。
- 已新增代理环境回归测试，验证状态、占用、操作和认证均正常工作。

保留 Windows 11 风格界面、深浅色及跟随系统、文件管理、多终端、日志阅读位置、圆形设置按钮和 GitHub 主页入口。

原有启动项配置会保留在 `%LOCALAPPDATA%\LocalDeck`。退出软件会结束它管理的任务和终端。本版仅支持 Windows 11 x64，未做 Authenticode 签名。

Mac 无需为此问题更新，继续使用 [macOS 0.5.0](https://github.com/RainFoam0693/LocalDeck/releases/tag/v0.5.0)。
