# changelog

all notable changes to this project are documented in this file.

## unreleased

- fixes a bug where the texture cache may not open due to integrity checks
- ships a `.dmg` next to the zip
- on mac, share menu bar for all windows

## v0.5.0 - 2026-09-01

- find a texture from a similar image. useful for screenshots
- a failed export no longer leaves a truncated file behind
- set LLTEXTURECACHE_LOG env var to see debugging information
- the app hands its exit code back
- bumps texture-courier dependency, bringing in some minor improvements
- right click menu on the inspector, with the alpha mode shown in it
- drag and drop in the inspector
- better tooltip for the inspector preview
- rename "Transparency Mode" to "Alpha Mode", and "Grid" to "Checkerboard"
- fix sticky swatches
- render alerts as a dialog instead of a line in the status bar

## v0.4.0 - 2026-08-28

- hide simple textures by default (can be shown through view menu)
- make space shortcut a grid-level action instead of global
- smart adjust aspect ratio in preview
- stretch preview instead of letterbox
- separate native View menu items with a separator

## v0.3.1 - 2026-08-27

- no functional changes from v0.3.0 (re-release)

## v0.3.0 - 2026-08-27

- fix regression with encoding
- her background is black-ish purple now. sorry. it wont change any more
- preview is shared between windows

## v0.2.3 - 2026-08-27

- mac app is now notarized

## v0.2.2 - 2026-08-27

- another failed attempt to notarize mac app x-o

## v0.2.1 - 2026-08-27

- failed attempt to notarize mac app o_x

## v0.2.0 - 2026-08-27

- optimize checkerboard sample
- she's pink now (on mac)
- fix load priority in decoding queue
- inspector/preview inherit their transparency
- empty frame on grid
- remove the open button on empty windows
- drag and drop in texturecache dirs
- drag textures out of window to save them as jp2
- transparency settings in View menu

## v0.1.0 - 2026-08-26

- improve algorithm for color filters
- can show incomplete textures
- persistent color swatches, with defaults
- new mac icon

## v0.0.9 - 2026-08-26

- shrink build by excluding unused dependencies
- remove post-tahoe icons
- don't show useless open button
- new icon

## v0.0.8 - 2026-08-25

- appimage build with a temporary icon
- fix setuptools packaging

## v0.0.7 - 2026-08-25

- windows build step that invokes vcvars64
- drop unused nuitka cache

## v0.0.6 - 2026-08-25

- only jump to end of grid on new textures
- pin grid to bottom
- bump color match floor
- homebrew tap, and dumpbin in the windows release
- mark releases as pre-release until assets are uploaded

## v0.0.5 - 2026-08-25

- homebrew tap groundwork
- release script updates

## v0.0.4 - 2026-08-25

- packaging fixes only

## v0.0.3 - 2026-08-25

- use nuitka cache in builds

## v0.0.2 - 2026-08-25

- decode through openJPEG on all platforms
- rework color filters
- use intrinsic size on checkerboard
- "Open Suggested" in menu
- make the picker more clear
- use ccache in build

## v0.0.1 - 2026-08-25

- initial release
