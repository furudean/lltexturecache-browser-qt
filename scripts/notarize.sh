#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ]; then
	echo "err: notarization only runs on macos" >&2
	exit 1
fi

: "${APPLE_ID:?the apple id to submit as}"
: "${APPLE_TEAM_ID:?the team the apple id belongs to}"
: "${APPLE_APP_PASSWORD:?an app specific password for the apple id}"

# captured first so a failure here is not swallowed by eval
info="$(uv run python scripts/app-info)"
eval "$info"

app="$EXEC_DIRECTORY/$NAME.app"
archive="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/notarize.zip"

if [ ! -d "$app" ]; then
	echo "err: $app does not exist, run scripts/build.sh first" >&2
	exit 1
fi

ditto -c -k --keepParent "$app" "$archive"

xcrun notarytool submit "$archive" \
	--apple-id "$APPLE_ID" \
	--team-id "$APPLE_TEAM_ID" \
	--password "$APPLE_APP_PASSWORD" \
	--wait

rm -f "$archive"

xcrun stapler staple "$app"
