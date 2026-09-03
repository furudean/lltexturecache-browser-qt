#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ]; then
	echo "err: universal bundles only build on macos" >&2
	exit 1
fi

# captured first so a failure is raised early
info="$(uv run --no-project python scripts/app-info)"
eval "$info"

arm="${1:-}"
intel="${2:-}"
out="${3:-$EXEC_DIRECTORY/$NAME.app}"

if [ -z "$arm" ] || [ -z "$intel" ]; then
	echo "usage: $0 <arm64 app> <x86_64 app> [output app]" >&2
	exit 2
fi

for app in "$arm" "$intel"; do
	if [ ! -d "$app" ]; then
		echo "err: $app does not exist" >&2
		exit 1
	fi
done

find "$arm" "$intel" -name .DS_Store -delete

# the walk below is over plain files, so a symlinked framework would go
# missing rather than come out broken. nuitka does not make any today
links="$(find "$arm" "$intel" -type l)"

if [ -n "$links" ]; then
	echo "err: the bundles hold symlinks, which the merge would drop" >&2
	echo "$links" >&2
	exit 1
fi

tmp="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/lipo"
rm -rf "$tmp"
mkdir -p "$tmp"

# the two bundles have to hold the same files, otherwise the merge would
# quietly ship whatever the arm64 build happened to have
( cd "$arm" && find . -type f | sort ) > "$tmp/arm.list"
( cd "$intel" && find . -type f | sort ) > "$tmp/intel.list"

if ! diff -u "$tmp/arm.list" "$tmp/intel.list" > "$tmp/diff.list"; then
	echo "err: the two bundles do not hold the same files" >&2
	cat "$tmp/diff.list" >&2
	exit 1
fi

rm -rf "$out"
mkdir -p "$(dirname "$out")"

merged=0
copied=0

while IFS= read -r file; do
	# the signature is rebuilt by scripts/macos-sign.sh, so it is not worth
	# carrying either bundle's over
	case "$file" in
		./Contents/_CodeSignature/* | ./Contents/CodeResources) continue ;;
	esac

	mkdir -p "$out/$(dirname "$file")"

	if file -b "$arm/$file" | grep -q Mach-O; then
		lipo -create "$arm/$file" "$intel/$file" -output "$out/$file"
		chmod "$(stat -f '%Lp' "$arm/$file")" "$out/$file"
		merged=$((merged + 1))
	else
		# everything else is architecture independent, so either copy will do
		cp -p "$arm/$file" "$out/$file"
		copied=$((copied + 1))
	fi
done < "$tmp/arm.list"

rm -rf "$tmp"

# a slice missing here would only surface as a crash on the other machine
missing="$(find "$out" -type f -exec sh -c '
	file -b "$1" | grep -q Mach-O || exit 0
	archs=" $(lipo -archs "$1") "
	case "$archs" in
		*" arm64 "*) ;;
		*) echo "$1:$archs" && exit 0 ;;
	esac
	case "$archs" in
		*" x86_64 "*) ;;
		*) echo "$1:$archs" ;;
	esac
' _ {} \;)"

if [ -n "$missing" ]; then
	echo "err: these binaries are not universal" >&2
	echo "$missing" >&2
	exit 1
fi

echo "$out has $merged universal binaries and $copied other files"
