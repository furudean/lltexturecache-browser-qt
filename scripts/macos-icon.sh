#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ]; then
	echo "err: the icon catalogue only builds on macos" >&2
	exit 1
fi

# captured first so a failure is raised early
info="$(uv run --no-project python scripts/app-info)"
eval "$info"

root="$(pwd -P)"
app="$root/$EXEC_DIRECTORY/$NAME.app"
source="$root/packaging/slcachegirl.icon"
icon="$(basename "$source" .icon)"

if [ ! -d "$app" ]; then
	echo "err: $app does not exist, run scripts/build.sh first" >&2
	exit 1
fi

if ! xcrun --find actool >/dev/null 2>&1; then
	echo "err: actool is missing, install xcode" >&2
	exit 1
fi

plist="$app/Contents/Info.plist"
partial="$(mktemp -t icon-plist)"

# macos 26 and up draw the icon out of Assets.car
if ! result="$(xcrun actool \
	--compile "$app/Contents/Resources" \
	--platform macosx \
	--minimum-deployment-target "${MACOSX_DEPLOYMENT_TARGET:-13.0}" \
	--app-icon "$icon" \
	--output-partial-info-plist "$partial" \
	"$source" 2>&1)"; then
	echo "$result" >&2
	exit 1
fi

for key in CFBundleIconName CFBundleIconFile; do
	value="$(plutil -extract "$key" raw -o - "$partial")"
	plutil -replace "$key" -string "$value" "$plist"
done

rm -f "$partial"

echo "compiled $source into $app"
