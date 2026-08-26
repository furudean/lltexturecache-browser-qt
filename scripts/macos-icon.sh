#!/usr/bin/env sh

# nuitka only knows how to set a .icns, which is the flat pre-Tahoe icon. the
# .icon bundle from Icon Composer is what macOS 26 wants: it holds the layers
# the system needs to render the icon in light, dark, clear and tinted modes.
# there is no way to hand that to nuitka, so we compile it ourselves and graft
# the result onto the finished bundle.

set -eu

if [ $# -ne 2 ]; then
	echo "usage: $0 path/to/App.app path/to/icon.icon" >&2
	exit 2
fi

app="$1"
icon="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"  # actool needs absolute path

name="$(basename "$icon" .icon)"
plist="$app/Contents/Info.plist"

if [ ! -d "$app" ]; then
	echo "err: $app is not an app bundle" >&2
	exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# writes Assets.car, a legacy $name.icns fallback for older macOS, and a plist
# fragment naming the icon
compile() {
	xcrun actool "$icon" \
		--compile "$work" \
		--app-icon "$name" \
		--platform macosx \
		--minimum-deployment-target 26.0 \
		--output-partial-info-plist "$work/partial.plist" \
		--errors --warnings >"$work/actool.log" 2>&1
}

# actool only learned to read .icon in Xcode 26, and a machine can have several
# Xcodes installed, any of which may be too old or not through its first launch,
# so try the selected one and then every other, newest first, until one manages
# it. the CI runner is a case in point: its default Xcode is 16, with newer ones
# installed alongside as Xcode_26.x.app
if ! compile; then
	for candidate in $(ls -d /Applications/Xcode*.app/Contents/Developer 2>/dev/null | sort -rV); do
		[ -x "$candidate/usr/bin/actool" ] || continue
		DEVELOPER_DIR="$candidate"
		export DEVELOPER_DIR
		compile && break
	done
fi

if [ ! -f "$work/Assets.car" ]; then
	cat "$work/actool.log" >&2
	echo "warn: could not compile $icon, keeping the .icns icon" >&2
	exit 0
fi

cp "$work/Assets.car" "$app/Contents/Resources/Assets.car"
cp "$work/$name.icns" "$app/Contents/Resources/$name.icns"

# CFBundleIconName points at the entry in Assets.car, CFBundleIconFile is the
# fallback for anything that does not read asset catalogs
plutil -replace CFBundleIconName -string "$name" "$plist"
plutil -replace CFBundleIconFile -string "$name" "$plist"

# adding files to Resources invalidates the seal nuitka signed the bundle with,
# so sign it again the way nuitka would have. --deep matters: nuitka drops data
# files into Contents/MacOS, which codesign insists on treating as code, and
# without it the signature is refused
identity="${MACOS_SIGN_IDENTITY:--}"
set -- --force --deep --preserve-metadata=entitlements --sign "$identity"

if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
	set -- "$@" --options=runtime --timestamp
fi

# /usr/bin/codesign explicitly, to sidestep any codesign on PATH from a conda
# style environment
/usr/bin/codesign "$@" "$app"
