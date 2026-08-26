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

info="$(uv run python scripts/app-info)"
eval "$info"

binary="$EXEC_DIRECTORY/$NAME.bin"
appdir="$EXEC_DIRECTORY/$NAME.AppDir"
output="$EXEC_DIRECTORY/$NAME.AppImage"

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

cp "$binary" "$appdir/usr/bin/$NAME"
chmod +x "$appdir/usr/bin/$NAME"

sed -e "s|@NAME@|$NAME|g" -e "s|@DISPLAY_NAME@|$DISPLAY_NAME|g" \
	packaging/app.desktop > "$appdir/$NAME.desktop"
cp "$appdir/$NAME.desktop" "$appdir/usr/share/applications/$NAME.desktop"

cp packaging/slcachegirl.png "$appdir/$NAME.png"
ln -s "$NAME.png" "$appdir/.DirIcon"

icon_size="$(uv run python -c 'import struct
with open("packaging/slcachegirl.png", "rb") as png:
    print(struct.unpack(">I", png.read(20)[16:])[0])')"

icon_dir="$appdir/usr/share/icons/hicolor/${icon_size}x${icon_size}/apps"
mkdir -p "$icon_dir"
cp packaging/slcachegirl.png "$icon_dir/$NAME.png"

cat > "$appdir/AppRun" <<SHIM
#!/usr/bin/env sh
here="\$(dirname "\$(readlink -f "\$0")")"
exec "\$here/usr/bin/$NAME" "\$@"
SHIM

chmod +x "$appdir/AppRun"

# extract-and-run because the runner has no FUSE to mount appimagetool with
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$arch" "$tool" --no-appstream "$appdir" "$output"

rm -rf "$appdir"

echo "wrote $output"
