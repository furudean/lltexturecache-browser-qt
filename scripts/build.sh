#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

spec=pysidedeploy.spec
generated_spec=pysidedeploy.generated.spec

names="$(uv run python -c 'import tomllib
config = tomllib.load(open("pyproject.toml", "rb"))
name = config["project"]["name"]
print(name)
print(config["tool"].get("app", {}).get("display-name", name))')"

# the slug names the files, the display name is what macOS puts in the menu bar
app_name="$(printf %s "$names" | sed -n 1p)"
display_name="$(printf %s "$names" | sed -n 2p)"

exec_directory="$(awk -F ' = ' '/^exec_directory = /{print $2}' "$spec")"

extra_args="--assume-yes-for-downloads"

if [ "$(uname -s)" = Darwin ]; then
	extra_args="$extra_args '--macos-app-name=$display_name'"

	if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
		extra_args="$extra_args '--macos-sign-identity=$MACOS_SIGN_IDENTITY' --macos-sign-notarization"
	fi
fi

mkdir -p "$exec_directory"

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

rm -rf "$exec_directory/$app_name.app" "$exec_directory/$app_name.exe" "$exec_directory/$app_name.bin"

uv run pyside6-deploy --config-file "$generated_spec" --name "$app_name" --force

# swap the flat .icns nuitka baked in for the layered Icon Composer icon
if [ "$(uname -s)" = Darwin ]; then
	./scripts/macos-icon.sh "$exec_directory/$app_name.app" packaging/slcachegirl.icon
fi
