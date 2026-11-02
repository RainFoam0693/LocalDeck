# LocalDeck 0.7.0 · macOS 与 Windows 11

Windows 11 x64 下载 **LocalDeck-0.7.0-Windows-x64.exe**，退出旧版后运行新版；也可下载含说明和许可的 ZIP，无需安装 Python 或 Qt。

macOS Apple Silicon 下载 **LocalDeck-0.7.0-macOS-arm64.dmg**，退出旧版后拖动 LocalDeck.app 替换原应用；也提供 ZIP。需要 macOS 13+ 和 Python 3，原生液态玻璃需要 macOS 26+。

## 新功能

- SSH 服务器入口：保存、编辑和删除服务器名称、主机、用户名、端口及可选私钥路径，下次一键连接 Linux 终端。
- 多连接标签：每个 SSH 会话独立运行，切换页面不中断；标签显示服务器名称。退出应用前提醒仍在运行的连接。
- 系统 OpenSSH：支持交互式密码、私钥口令和 SSH Agent，保留服务器指纹校验；配置不保存密码或复制私钥。Windows 需要安装 OpenSSH 客户端可选功能。

文件浏览器继续管理本机文件；本版不包含远程 SFTP、自动重连或退出后恢复会话。

配置保留，正在运行的终端任务不会迁移到新版。macOS 保留原生玻璃控件，Windows 使用 Windows 11 风格。

当前安装包未做 Apple 公证或 Windows Authenticode 签名。SHA-256 校验文件随安装包提供。
