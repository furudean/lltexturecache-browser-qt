#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

target="${1:-}"

if [ -z "$target" ]; then
	echo "usage: $0 <app or dmg to notarize>" >&2
	exit 2
fi

if [ ! -e "$target" ]; then
	echo "err: $target does not exist" >&2
	exit 1
fi

# an ad-hoc signature is not something apple will notarize, and the
# credentials are only present on a release runner
if [ "${MACOS_SIGN_IDENTITY:--}" = "-" ]; then
	echo "note: signed ad-hoc, skipping notarization of $target"
	exit 0
fi

if [ -z "${APPLE_ID:-}" ] || [ -z "${APPLE_TEAM_ID:-}" ] || [ -z "${APPLE_APP_PASSWORD:-}" ]; then
	echo "note: apple credentials unset, skipping notarization of $target"
	exit 0
fi

# notarytool takes a zip, a dmg or an installer package, so a bundle has to be
# archived on the way in. the ticket is still stapled to the bundle itself
if [ -d "$target" ]; then
	submission="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/notarize.zip"
	ditto -c -k --keepParent "$target" "$submission"
else
	submission="$target"
fi

xcrun notarytool submit "$submission" \
	--apple-id "$APPLE_ID" \
	--team-id "$APPLE_TEAM_ID" \
	--password "$APPLE_APP_PASSWORD" \
	--wait

if [ "$submission" != "$target" ]; then
	rm -f "$submission"
fi

xcrun stapler staple "$target"
xcrun stapler validate "$target"
