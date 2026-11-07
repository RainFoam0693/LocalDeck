# LocalDeck 0.7.2 · macOS 修复版

包含 0.7.1 的逐像素平滑滚动、边缘拖选、终端右键菜单、原生中文菜单和标签整块点击修复。

本次额外修复：后端和更新检查使用 Python 禁用字节码缓存选项，避免应用运行后向包内写入缓存、破坏签名完整性。构建时清理历史生成缓存。

macOS Apple Silicon 下载 **LocalDeck-0.7.2-macOS-arm64.dmg** 或 ZIP。需要 macOS 13+ 和 Python 3。退出当前应用后替换，现有配置保留。终端任务不会迁移。

Windows 本次功能更新为 **0.7.1**，安装包见 [0.7.1 发行页](https://github.com/RainFoam0693/LocalDeck/releases/tag/v0.7.1)。Windows 无需此缓存修复。

本包仅本地签名，未做 Apple 公证；提供 SHA-256 校验文件。
