# lltexturecache-browser-qt

![a screenshot of lltexturecache-browser-qt with a cache open](preview.png)

a cross-platform tool to browse and export textures from the second life texture cache

## install

windows and linux builds are attached to
[each release](https://github.com/furudean/lltexturecache-browser-qt/releases).

on mac, you can install with homebrew:

```bash
brew install --cask furudean/tap/lltexturecache-browser-qt
```

## features

- browse and filter through a large amount of textures in a cache
- save textures to disk in commonly-used image formats
- be fast and out of the way
- it's not an electron app

## develop

use [uv](https://docs.astral.sh/uv/) to run the app in a development context

```bash
uv run lltexturecache-browser-qt
```

## build

build script makes the app for the host platform. mac gets a `.app`
windows `.exe` and linux a binary/AppImage. cross-compiling is not
supported

```bash
./scripts/build.sh
```

uv is required to build. on linux, you will also need `patchelf` and 
`libxcb-cursor0` on PATH.

## release

publishing a github release builds for all platforms and attaches the binaries
to it. it can be triggered like this:

```bash
./scripts/release.sh major|minor|patch
```

it bumps the version, commits the bump, tags it, pushes both and creates the release. the release triggers a 
github workflow. which does the rest


to sign and/or notarize the app for mac, the following secrets should be set in the deployment pipeline:

| secret                       | is a                                                            | used for     |
| ---------------------------- | --------------------------------------------------------------- | ------------ |
| `MACOS_CERTIFICATE`          | developer ID Application certificate as `.p12`, base64 encoded  | signing      |
| `MACOS_CERTIFICATE_PASSWORD` | password the `.p12` was exported with                           | signing      |
| `MACOS_SIGN_IDENTITY`        | e.g. `Developer ID Application: Your Name (TEAMID)`             | signing      |
| `APPLE_ID`                   | Apple ID the app-specific password belongs to                   | notarization |
| `APPLE_APP_PASSWORD`         | [app-specific password](https://support.apple.com/en-us/102654) | notarization |
| `APPLE_TEAM_ID`              | ten character team ID                                           | notarization |

## attribution

the icon was made by [@sferics32.bsky.social](https://bsky.app/profile/did:plc:omeuiwhg6nfnwdorlfxtszei).