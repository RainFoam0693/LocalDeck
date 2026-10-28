#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
if [[ "${1:-}" != "--skip-build" ]]; then ./scripts/build.sh; fi
APP="$PWD/dist/LocalDeck.app"
NAME="LocalDeck-0.6.0-macOS-arm64"
STAGING=$(mktemp -d /tmp/localdeck-package.XXXXXX)
ditto "$APP" "$STAGING/LocalDeck.app"
ln -s /Applications "$STAGING/Applications"
cat > "$STAGING/安装说明.txt" <<'TXT'
LocalDeck 0.6.0 · macOS Apple Silicon

将 LocalDeck.app 拖到 Applications，即可安装。
需要 macOS 13+ 和已安装的 Python 3。
本版本仅本地签名，尚未经过 Apple 公证。

退出应用会停止由应用启动的任务。
配置和日志位于 ~/Library/Application Support/LocalDeck。
TXT
hdiutil create -volname LocalDeck -srcfolder "$STAGING" -ov -format UDZO "$PWD/dist/$NAME.dmg"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$PWD/dist/$NAME.zip"
(cd dist && shasum -a 256 "$NAME.dmg" "$NAME.zip" > SHA256SUMS-macOS.txt)
echo "安装包输出到 $PWD/dist"
