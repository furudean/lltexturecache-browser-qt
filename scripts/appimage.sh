#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Linux ]; then
	echo "err: AppImages can only be built on linux" >&2
	exit 1
fi

appimagetool_version=1.9.1

case "$(uname -m)" in
	x86_64) arch=x86_64 ;;
	aarch64 | arm64) arch=aarch64 ;;
	*)
		echo "err: no appimagetool for $(uname -m)" >&2
		exit 1
		;;
esac

names="$(uv run python -c 'import tomllib
config = tomllib.load(open("pyproject.toml", "rb"))
name = config["project"]["name"]
print(name)
print(config["tool"].get("app", {}).get("display-name", name))')"

app_name="$(printf %s "$names" | sed -n 1p)"
display_name="$(printf %s "$names" | sed -n 2p)"

exec_directory="$(awk -F ' = ' '/^exec_directory = /{print $2}' pysidedeploy.spec)"

binary="$exec_directory/$app_name.bin"
appdir="$exec_directory/$app_name.AppDir"
output="$exec_directory/$app_name.AppImage"

if [ ! -f "$binary" ]; then
	echo "err: $binary does not exist, run scripts/build.sh first" >&2
	exit 1
fi

tool="${XDG_CACHE_HOME:-$HOME/.cache}/appimagetool-$appimagetool_version-$arch.AppImage"

if [ ! -f "$tool" ]; then
	mkdir -p "$(dirname "$tool")"
	curl --location --fail --silent --show-error --output "$tool.part" \
		"https://github.com/AppImage/appimagetool/releases/download/$appimagetool_version/appimagetool-$arch.AppImage"
	mv "$tool.part" "$tool"
fi

chmod +x "$tool"

rm -rf "$appdir" "$output"

mkdir -p "$appdir/usr/bin" "$appdir/usr/share/applications"

cp "$binary" "$appdir/usr/bin/$app_name"
chmod +x "$appdir/usr/bin/$app_name"

sed -e "s|@NAME@|$app_name|g" -e "s|@DISPLAY_NAME@|$display_name|g" \
	packaging/app.desktop > "$appdir/$app_name.desktop"
cp "$appdir/$app_name.desktop" "$appdir/usr/share/applications/$app_name.desktop"

# the icon is needed at the root of the AppDir for the desktop file to resolve
# and under hicolor for the menu entry once the AppImage is integrated
cp packaging/icon.png "$appdir/$app_name.png"
ln -s "$app_name.png" "$appdir/.DirIcon"

# the hicolor directory has to say what size the artwork actually is
icon_size="$(uv run python -c 'from PIL import Image
print(Image.open("packaging/icon.png").width)')"

icon_dir="$appdir/usr/share/icons/hicolor/${icon_size}x${icon_size}/apps"
mkdir -p "$icon_dir"
cp packaging/icon.png "$icon_dir/$app_name.png"

cat > "$appdir/AppRun" <<SH
#!/usr/bin/env sh
here="\$(dirname "\$(readlink -f "\$0")")"
exec "\$here/usr/bin/$app_name" "\$@"
SH

chmod +x "$appdir/AppRun"

# extract-and-run because the runner has no FUSE to mount appimagetool with
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$arch" "$tool" --no-appstream "$appdir" "$output"

rm -rf "$appdir"

echo "wrote $output"
