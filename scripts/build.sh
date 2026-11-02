#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
APP="$PWD/dist/LocalDeck.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" /tmp/localdeck-module-cache
# Pass the active SDK through both compilation and linking for native AppKit appearance.
SDK_PATH=$(xcrun --sdk macosx --show-sdk-path)
GITHUB_ACTIONS=true swift package --disable-sandbox resolve
python3 scripts/patch-swiftterm.py
GITHUB_ACTIONS=true swift build --build-system native -c release --product LocalDeck --sdk "$SDK_PATH" --disable-sandbox
BIN_DIR=$(swift build --build-system native -c release --sdk "$SDK_PATH" --show-bin-path)
cp "$BIN_DIR/LocalDeck" "$APP/Contents/MacOS/LocalDeck"
SDK_VERSION=$(xcrun --sdk macosx --show-sdk-version)
LINKED_SDK=$(xcrun vtool -show-build "$APP/Contents/MacOS/LocalDeck" | awk '$1 == "sdk" { print $2; exit }')
if [[ "${LINKED_SDK%%.*}" != "${SDK_VERSION%%.*}" ]]; then
    print -u2 "Linked SDK $LINKED_SDK does not match active SDK $SDK_VERSION"
    exit 1
fi
for bundle in "$BIN_DIR/"*.bundle(N); do
    ditto "$bundle" "$APP/Contents/Resources/${bundle:t}"
done
swiftc scripts/make-icon.swift -module-cache-path /tmp/localdeck-module-cache -o /tmp/localdeck-make-icon -framework AppKit
/tmp/localdeck-make-icon "$PWD"
iconutil -c icns assets/LocalDeck.iconset -o assets/LocalDeck.icns
cp assets/LocalDeck.icns "$APP/Contents/Resources/LocalDeck.icns"
cp -f licenses/SwiftTerm-LICENSE.txt "$APP/Contents/Resources/SwiftTerm-LICENSE.txt"
cp backend/performance.py "$APP/Contents/Resources/performance.py"
cp backend/updates.py "$APP/Contents/Resources/updates.py"
cp backend/server.py "$APP/Contents/Resources/server.py"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>LocalDeck</string>
<key>CFBundleIdentifier</key><string>dev.localdeck.mac</string>
<key>CFBundleIconFile</key><string>LocalDeck</string>
<key>CFBundleName</key><string>LocalDeck</string>
<key>CFBundleVersion</key><string>8</string>
<key>CFBundleShortVersionString</key><string>0.7.0</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$APP"
echo "$APP"
