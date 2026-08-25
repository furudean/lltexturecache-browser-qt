#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

bump="${1:-}"

case "$bump" in
	major | minor | patch) ;;
	*)
		echo "usage: $0 major|minor|patch" >&2
		exit 2
		;;
esac

if [ -n "$(git status --porcelain)" ]; then
	echo "err: working tree is dirty" >&2
	exit 1
fi

version="$(uv version --bump "$bump" --dry-run --short)"
tag="v$version"

if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
	echo "err: tag $tag already exists" >&2
	exit 1
fi

printf 'you are about to release %s (from v%s) on branch %s. continue? [y/N] ' \
	"$tag" "$(uv version --short)" "$(git rev-parse --abbrev-ref HEAD)"
read -r reply </dev/tty
case "$reply" in
	y | Y | yes | YES) ;;
	*)
		echo "aborted" >&2
		exit 1
		;;
esac

uv version --bump "$bump"

git add pyproject.toml uv.lock
git commit -m "release $tag"
git tag "$tag"

git push origin HEAD
git push origin "$tag"

# publishing the release is what builds the binaries for every platform
gh release create "$tag" --generate-notes
