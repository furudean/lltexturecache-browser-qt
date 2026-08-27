#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

info="$(uv run python scripts/app-info)"
eval "$info"

spec=pysidedeploy.spec
generated_spec=pysidedeploy.generated.spec

extra_args="--assume-yes-for-downloads"

if [ "$(uname -s)" = Darwin ]; then
	extra_args="$extra_args '--macos-app-name=$DISPLAY_NAME'"
	extra_args="$extra_args '--macos-signed-app-name=$BUNDLE_ID'"
	extra_args="$extra_args '--macos-app-version=$VERSION'"
fi

mkdir -p "$EXEC_DIRECTORY"

# nuitka wants .icns on mac, .ico on windows and .png everywhere else
case "$(uname -s)" in
	Darwin) icon=packaging/slcachegirl.icns ;;
	CYGWIN* | MINGW* | MSYS* | Windows_NT) icon=packaging/slcachegirl.ico ;;
	*) icon=packaging/slcachegirl.png ;;
esac

awk -v extra="$extra_args" -v icon="$icon" '
	/^extra_args = / { print $0 " " extra; next }
	/^icon = / { print "icon = " icon; next }
	{ print }
' "$spec" > "$generated_spec"

uv run python scripts/generate-metadata

# the licence of everything the build bundles, read out of the installed
# packages rather than kept in the tree
uv run python scripts/generate-licences

rm -rf "$EXEC_DIRECTORY/$NAME.app" "$EXEC_DIRECTORY/$NAME.exe" "$EXEC_DIRECTORY/$NAME.bin"

uv run pyside6-deploy --config-file "$generated_spec" --name "$NAME" --force

if [ "$(uname -s)" = Linux ]; then
	./scripts/appimage.sh
fi
