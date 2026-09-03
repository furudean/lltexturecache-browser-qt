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

changelog="CHANGELOG.md"

./scripts/changelog-notes.sh unreleased >/dev/null

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

date="$(date -u +%Y-%m-%d)"
tmp="$(mktemp)"
awk -v heading="## $tag - $date" \
	'!done && /^## unreleased$/ { print heading; done = 1; next } { print }' \
	"$changelog" >"$tmp"
mv "$tmp" "$changelog"

git add pyproject.toml uv.lock "$changelog"
git commit -m "release $tag"
git tag "$tag"

git push origin HEAD
git push origin "$tag"

echo "pushed $tag, the release workflow builds and publishes the release"
