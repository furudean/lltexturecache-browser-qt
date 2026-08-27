#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ]; then
	echo "err: signing only runs on macos" >&2
	exit 1
fi

# captured first so a failure is raised early
info="$(uv run python scripts/app-info)"
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

# an ad-hoc signature is not something apple will notarize, and the
# credentials are only present on a release runner
if [ "$identity" = "-" ]; then
	echo "note: signed ad-hoc, skipping notarization"
	exit 0
fi

if [ -z "${APPLE_ID:-}" ] || [ -z "${APPLE_TEAM_ID:-}" ] || [ -z "${APPLE_APP_PASSWORD:-}" ]; then
	echo "note: apple credentials unset, skipping notarization"
	exit 0
fi

archive="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/notarize.zip"

ditto -c -k --keepParent "$app" "$archive"

xcrun notarytool submit "$archive" \
	--apple-id "$APPLE_ID" \
	--team-id "$APPLE_TEAM_ID" \
	--password "$APPLE_APP_PASSWORD" \
	--wait

rm -f "$archive"

xcrun stapler staple "$app"
spctl --assess --type execute --verbose=4 "$app"
codesign --verify --deep --strict --verbose=2 "$app"
