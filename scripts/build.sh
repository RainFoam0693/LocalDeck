#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
APP="$PWD/dist/LocalDeck.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" /tmp/localdeck-module-cache
swiftc Sources/LocalDeck.swift -target "$(uname -m)-apple-macos13.0" -parse-as-library -swift-version 5 -module-cache-path /tmp/localdeck-module-cache -O -o "$APP/Contents/MacOS/LocalDeck" -framework SwiftUI -framework AppKit
swiftc scripts/make-icon.swift -module-cache-path /tmp/localdeck-module-cache -o /tmp/localdeck-make-icon -framework AppKit
/tmp/localdeck-make-icon "$PWD"
iconutil -c icns assets/LocalDeck.iconset -o assets/LocalDeck.icns
cp assets/LocalDeck.icns "$APP/Contents/Resources/LocalDeck.icns"
cp backend/server.py "$APP/Contents/Resources/server.py"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>LocalDeck</string>
<key>CFBundleIdentifier</key><string>dev.localdeck.mac</string>
<key>CFBundleIconFile</key><string>LocalDeck</string>
<key>CFBundleName</key><string>LocalDeck</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$APP"
echo "$APP"
