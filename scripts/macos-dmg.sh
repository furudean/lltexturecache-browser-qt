#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ]; then
	echo "err: disk images only build on macos" >&2
	exit 1
fi

# captured first so a failure is raised early
info="$(uv run --no-project python scripts/app-info)"
eval "$info"

app="$EXEC_DIRECTORY/$NAME.app"
dmg="${1:-$EXEC_DIRECTORY/$NAME.dmg}"
identity="${MACOS_SIGN_IDENTITY:--}"

if [ ! -d "$app" ]; then
	echo "err: $app does not exist, run scripts/build.sh first" >&2
	exit 1
fi

root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/dmg"

rm -rf "$root"
mkdir -p "$root"

# the bundle plus the usual drag target, so the image installs the way people
# expect one to
ditto "$app" "$root/$NAME.app"
ln -s /Applications "$root/Applications"
find "$root" -name .DS_Store -delete

mkdir -p "$(dirname "$dmg")"
rm -f "$dmg"

hdiutil create \
	-volname "$DISPLAY_NAME $VERSION" \
	-srcfolder "$root" \
	-fs HFS+ \
	-format UDZO \
	-quiet \
	"$dmg"

rm -rf "$root"

# an ad-hoc signature on the image buys nothing, gatekeeper reads the one on
# the bundle inside it
if [ "$identity" != "-" ]; then
	codesign \
		--sign "$identity" \
		--identifier "$BUNDLE_ID.dmg" \
		--force \
		--timestamp \
		"$dmg"

	codesign --verify --strict --verbose=2 "$dmg"
fi

./scripts/macos-notarize.sh "$dmg"

ls -l "$dmg"
