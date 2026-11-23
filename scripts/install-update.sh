#!/bin/sh
# Arguments are local paths prepared by the updater after download verification.
set -eu
pid=$1
image=$2
target=$3
version=$4
report_failure() {
    /usr/bin/osascript -e 'display alert "LocalDeck 更新未完成" message "请检查安装目录权限，或从下载目录手动安装。" as warning' >/dev/null 2>&1 || :
}
work=$(/usr/bin/mktemp -d "${target%/*}/.localdeck-update.XXXXXX")
mount="$work/mount"
mkdir "$mount"
cleanup() {
    status=$?
    /usr/bin/hdiutil detach "$mount" -quiet 2>/dev/null || :
    /bin/rm -rf "$work"
    if [ "$status" -ne 0 ]; then
        if ! kill -0 "$pid" 2>/dev/null && [ -d "$target" ]; then /usr/bin/open "$target" || :; fi
        report_failure
    fi
}
trap cleanup EXIT
/usr/bin/hdiutil attach "$image" -readonly -nobrowse -mountpoint "$mount" -quiet
/usr/bin/ditto "$mount/LocalDeck.app" "$work/LocalDeck.app"
/usr/bin/codesign --verify --deep --strict "$work/LocalDeck.app"
plist="$work/LocalDeck.app/Contents/Info.plist"
[ "$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$plist")" = dev.localdeck.mac ]
[ "$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$plist")" = "$version" ]
for i in $(/usr/bin/seq 1 120); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
done
! kill -0 "$pid" 2>/dev/null
mv "$target" "$work/previous.app"
if mv "$work/LocalDeck.app" "$target"; then
    if ! /usr/bin/open "$target"; then
        mv "$target" "$work/failed.app"
        mv "$work/previous.app" "$target" || { trap - EXIT; report_failure; }
        exit 1
    fi
else
    mv "$work/previous.app" "$target" || { trap - EXIT; report_failure; }
    exit 1
fi
