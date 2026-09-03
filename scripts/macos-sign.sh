#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ]; then
	echo "err: signing only runs on macos" >&2
	exit 1
fi

# captured first so a failure is raised early
info="$(uv run --no-project python scripts/app-info)"
eval "$info"

app="$EXEC_DIRECTORY/$NAME.app"
identity="${MACOS_SIGN_IDENTITY:--}"

if [ ! -d "$app" ]; then
	echo "err: $app does not exist, run scripts/build.sh first" >&2
	exit 1
fi

find "$app" -name .DS_Store -delete

codesign \
	--sign "$identity" \
	--identifier "$BUNDLE_ID" \
	--force \
	--deep \
	--options=runtime \
	--timestamp \
	"$app"

codesign --verify --deep --strict --verbose=2 "$app"

./scripts/macos-notarize.sh "$app"

if [ "$identity" != "-" ]; then
	spctl --assess --type execute --verbose=4 "$app"
fi

codesign --verify --deep --strict --verbose=2 "$app"
