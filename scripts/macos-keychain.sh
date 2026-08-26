#!/usr/bin/env sh

set -eu

keychain="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/build.keychain-db"

case "${1:-}" in
	import)
		: "${MACOS_CERTIFICATE:?the base64 encoded .p12 to sign with}"
		: "${MACOS_CERTIFICATE_PASSWORD:?the password the .p12 was exported with}"

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
		;;
	delete)
		security delete-keychain "$keychain" || true
		;;
	*)
		echo "usage: $0 import|delete" >&2
		exit 2
		;;
esac
