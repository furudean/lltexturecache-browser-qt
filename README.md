# lltexturecache-browser-qt

<p align="center">
  <img src="preview.png" width="600"
    alt="a screenshot of lltexturecache-browser-qt with a cache open">
</p>

lltexturecache-browser-qt is a cross-platform tool to browse and export textures
from the second life texture cache.

this application is useful if you want to mod existing assets on second life, like character clothing and the author does not provide a texture to download.

lltexturecache-browser-qt only reads what is stored in your cache files. it is not a copybot and should not be used to steal assets.

the app's icon, slcachegirl, is designed by [@sferics32.bsky.social](https://bsky.app/profile/did:plc:omeuiwhg6nfnwdorlfxtszei).

## features

- browse and filter through a large amount of textures
- find a texture by a screenshot
- save to disk in commonly-used image formats
- drag and drop support
- it's fast
- it's not an electron app


## i want it

windows, linux and mac builds are attached to
[each release](https://github.com/furudean/lltexturecache-viewer-gui/releases).
on mac, open the `.dmg` and drag the app into Applications.

on mac, you may install with homebrew:

```bash
brew install --cask furudean/tap/lltexturecache-browser-qt
```

### platform requirements

| platform | runs on                                     |
| -------- | ------------------------------------------- |
| mac      | macos 13 ventura or later (any arch)        |
| windows  | windows 10 or later, x86-64                 |
| linux    | glibc 2.35 or later (ubuntu 22.04+), x86-64 |

to run from source or build your own, see [develop](#develop) and
[build](#build).

## developing

use [uv](https://docs.astral.sh/uv/) to run the app in a development context

```bash
uv run lltexturecache-browser-qt
```

## build

a script makes the app for the host platform. mac gets a `.app` windows
`.exe` and linux a binary/AppImage. cross-compiling is not supported.

```bash
./scripts/build.sh
```

| needs            | on    | for                                                     |
| ---------------- | ----- | ------------------------------------------------------- |
| `uv`             | all   | running the build                                       |
| `patchelf`       | linux | nuitka to fix up the rpaths of the bundled qt libraries |
| `libxcb-cursor0` | linux | nuitka to have a copy to bundle into the binary         |

none of it is needed to run the result

## release

publishing a github release builds for all platforms and attaches the binaries
to it. write what changed under the `## unreleased` heading in `CHANGELOG.md`
first, then run:

```bash
./scripts/release.sh major|minor|patch
```

the script will

1. bump the version
2. retitle `## unreleased` in [CHANGELOG.md](CHANGELOG.md) to the version and
   date being released
3. commit that along with the bump, and tag it
4. push
5. create the release with notes from the changelog

the release triggers a github workflow. which does the rest

## sign / notarize (mac only)

signing needs a developer ID Application certificate in a keychain the signing
machine can read, plus the environment below. then

```bash
./scripts/build.sh
./scripts/macos-sign.sh
./scripts/package.sh
```

[macos-sign.sh](scripts/macos-sign.sh) re-signs the bundle with the hardened
runtime, notarizes and staples it; [package.sh](scripts/package.sh) then makes
the `.dmg` with another notarization pass.

notarization is skipped when the credentials are unset, so it degrades to a
plain signing step. in CI [macos-keychain.sh](scripts/macos-keychain.sh) runs
first to make a throwaway keychain out of `MACOS_CERTIFICATE`.

| variable                     | is a                                                            | needed         |
| ---------------------------- | --------------------------------------------------------------- | -------------- |
| `MACOS_SIGN_IDENTITY`        | e.g. `Developer ID Application: Your Name (TEAMID)`             | signing        |
| `APPLE_ID`                   | Apple ID the app-specific password belongs to                   | notarization   |
| `APPLE_APP_PASSWORD`         | [app-specific password](https://support.apple.com/en-us/102654) | notarization   |
| `APPLE_TEAM_ID`              | last part of MACOS_SIGN_IDENTITY                                | notarization   |
| `MACOS_CERTIFICATE`          | developer id application certificate as `.p12`, base64 encoded  | keychain in CI |
| `MACOS_CERTIFICATE_PASSWORD` | password the `.p12` was exported with                           | keychain in CI |

## prior art

- [SLCacheViewer](http://slcacheviewer.com/) (Windows only)
