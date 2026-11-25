# LocalDeck 1.0.0 · macOS 与 Windows 11

Windows 11 x64 下载 **LocalDeck-1.0.0-Windows-x64.exe**，退出旧版后运行新版；也可下载含说明和许可的 ZIP，无需安装 Python 或 Qt。

macOS Apple Silicon 安装包需要 macOS 13+ 和 Python 3，原生 Liquid Glass 需要 macOS 26+。

关闭窗口会将 LocalDeck 收到系统托盘/菜单栏，服务和终端继续运行。通过状态栏菜单重新打开窗口；选择“退出 LocalDeck”会结束应用管理的任务，仍有终端任务时会先确认。

## 本次改进

- Mac 终端逐像素平滑滚动，滚轮使用短缓动，触控板保留系统惯性；macOS 14+ 跟随屏幕刷新率，实际帧率取决于屏幕和运行负载。遵循系统减少动态效果设置。
- Windows 终端滚轮改为细粒度滚动，累计处理高精度输入，减少轻滚时的大幅跳动。
- 两端支持拖选到上下边缘时自动滚动，保护拖选不被新输出打断。Windows 在松开拖选后补齐输出。
- 终端右键菜单提供复制、粘贴、全选、取消选择、复制全部文本、回到最新输出；多行粘贴先询问确认。
- Mac 顶部原生菜单栏改为简体中文，终端标签背景的空白处也可点击切换，关闭按钮保持独立点击区域。

配置保留，正在运行的终端任务不会迁移到新版。macOS 保留原生 Liquid Glass 控件，Windows 使用 Windows 11 风格。

当前安装包未做 Apple 公证或 Windows Authenticode 签名。SHA-256 校验文件随安装包提供。
