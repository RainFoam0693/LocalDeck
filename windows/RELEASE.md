# LocalDeck 0.6.0 · macOS 与 Windows 11

Windows 11 x64 下载 **LocalDeck-0.6.0-Windows-x64.exe**，退出旧版后运行新版；也可下载含说明和许可的 ZIP，无需安装 Python 或 Qt。

macOS Apple Silicon 下载 **LocalDeck-0.6.0-macOS-arm64.dmg**，退出旧版后拖动 LocalDeck.app 替换原应用；也提供 ZIP。需要 macOS 13+ 和 Python 3，原生液态玻璃需要 macOS 26+。

## 新功能

- 退出保护：终端有前台或后台任务时询问，默认取消；只有空闲 Shell 时直接退出。取消会保留窗口与任务。
- 终端进程名称：标签自动显示 Yunzai、Vite 等项目或脚本名称，保留编号；悬停查看 PID 和目录，任务结束后恢复标签。
- 应用内更新：设置中手动检查，每周一、三、五在应用运行时每天自动检查一次，发现新版在顶部提示；由用户确认下载，校验 SHA-256 后引导替换安装。
- 私有更新源授权：可选只读 GitHub 令牌，保存在 macOS 钥匙串或 Windows 凭据管理器中；公开仓库无需授权。

配置保留，正在运行的终端任务不会迁移到新版。macOS 保留原生玻璃控件，Windows 使用 Windows 11 风格。

当前安装包未做 Apple 公证或 Windows Authenticode 签名。SHA-256 校验文件随安装包提供。
