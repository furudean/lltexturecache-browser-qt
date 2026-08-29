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
- save textures to disk in commonly-used image formats
- drag and drop support
- it's fast
- it's not an electron app


## i want it

windows, linux and mac builds are attached to
[each release](https://github.com/furudean/lltexturecache-viewer-gui/releases).

on mac, you may install with homebrew:

```bash
brew install --cask furudean/tap/lltexturecache-browser-qt
```

| platform | runs on                                     |
| -------- | ------------------------------------------- |
| mac      | macos 13 ventura or later, apple silicon    |
| windows  | windows 10 or later, x86-64                 |
| linux    | glibc 2.35 or later (ubuntu 22.04+), x86-64 |

intel macs are not built for.

to run from source or build your own, see [develop](#develop) and
[build](#build).

## install

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
to it. it can be triggered like this:

```bash
./scripts/release.sh major|minor|patch
```

it bumps the version, commits the bump, tags it, pushes both and creates the
release. the release triggers a github workflow. which does the rest

## sign / notarize (mac only)

signing needs a developer ID Application certificate from an apple developer
program membership. create it in [certificates, identifiers &
profiles](https://developer.apple.com/account/resources/certificates), or let
xcode do it under settings > accounts > manage certificates

the certificate has to live in a keychain the signing machine can read. locally
that's your login keychain, in CI you want to base64 encode it

```bash
# import a .p12 exported certificate
security import developer-id.p12 -k ~/Library/Keychains/login.keychain-db

# check the identity is present
security find-identity -v -p codesigning
```

fill in the required environment variables (see
[signing environment](#signing-environment)), then

```bash
./scripts/build.sh
./scripts/macos-sign.sh
```

the build reads no environment at all, the identity is only used at sign time.
[scripts/macos-sign.sh](scripts/macos-sign.sh) re-signs the bundle with the
hardened runtime, notarizes it and staples the ticket. notarization is skipped
when the signature is ad-hoc or the apple credentials are unset, so it doubles
as a plain signing step

the first signature of a session makes macos ask for permission to use the key.
allow always, or every later `codesign` run stops on the same prompt

CI has no certificate in its login keychain, so
[scripts/macos-keychain.sh](scripts/macos-keychain.sh) has to run first. it
imports `MACOS_CERTIFICATE` into a throwaway keychain and authorises codesign to
use the key without a prompt

to validate the result:

```bash
# who signed it
codesign --display --verbose=4 dist/lltexturecache-browser-qt.app

# is the seal intact
codesign --verify --deep --strict --verbose=2 dist/lltexturecache-browser-qt.app

# is notarization stapled
xcrun stapler validate dist/lltexturecache-browser-qt.app

# gatekeeper
spctl --assess --type execute --verbose=4 dist/lltexturecache-browser-qt.app
```

### signing environment

set the following environment variables to enable code signing and notarization:

| secret                       | is a                                                            | needed         |
| ---------------------------- | --------------------------------------------------------------- | -------------- |
| `MACOS_SIGN_IDENTITY`        | e.g. `Developer ID Application: Your Name (TEAMID)`             | signing        |
| `APPLE_ID`                   | Apple ID the app-specific password belongs to                   | notarization   |
| `APPLE_APP_PASSWORD`         | [app-specific password](https://support.apple.com/en-us/102654) | notarization   |
| `APPLE_TEAM_ID`              | last part of MACOS_SIGN_IDENTITY                                | notarization   |
| `MACOS_CERTIFICATE`          | developer id application certificate as `.p12`, base64 encoded  | keychain in CI |
| `MACOS_CERTIFICATE_PASSWORD` | password the `.p12` was exported with                           | keychain in CI |

## prior art

- [SLCacheViewer](http://slcacheviewer.com/) (Windows only)
