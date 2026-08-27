#!/usr/bin/env sh

set -eu

: "${MACOS_CERTIFICATE:?the base64 encoded .p12 to sign with}"
: "${MACOS_CERTIFICATE_PASSWORD:?the password the .p12 was exported with, macos will not import one without}"

keychain="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/build.keychain-db"
keychain_password="$(openssl rand -base64 24)"
certificate="$(dirname "$keychain")/certificate.p12"

security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 3600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"

echo "$MACOS_CERTIFICATE" | base64 --decode > "$certificate"
security import "$certificate" -k "$keychain" -P "$MACOS_CERTIFICATE_PASSWORD" \
	-T /usr/bin/codesign -T /usr/bin/security
rm "$certificate"

# let codesign use the key without an interactive prompt
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$keychain_password" "$keychain"

# keep the login keychain searchable, the runner needs it elsewhere.
# unquoted on purpose, the existing list has to split into arguments
security list-keychains -d user -s "$keychain" $(security list-keychains -d user | tr -d '"')

identities="$(security find-identity -v -p codesigning "$keychain")"
echo "$identities"

# fail here rather than a thousand lines into the nuitka build, which is
# where a name that does not match anything in the keychain would show up
if [ -n "${MACOS_SIGN_IDENTITY:-}" ] && ! echo "$identities" | grep -qF "$MACOS_SIGN_IDENTITY"; then
	echo "err: no identity matching MACOS_SIGN_IDENTITY in the keychain" >&2
	exit 1
fi
