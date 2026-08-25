#!/bin/sh

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
	echo "working tree is dirty" >&2
	exit 1
fi

uv version --bump "$bump"

version="$(uv version --short)"
tag="v$version"

if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
	echo "tag $tag already exists" >&2
	exit 1
fi

git add pyproject.toml uv.lock
git commit -m "release $tag"
git tag "$tag"

git push origin HEAD
git push origin "$tag"

# publishing the release is what builds the binaries for every platform
gh release create "$tag" --generate-notes
