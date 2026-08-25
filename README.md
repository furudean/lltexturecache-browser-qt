# lltexturecache-browser-qt

![A screenshot of lltexturecache-browser-qt with a cache open](<preview.png>)

A cross-platform user interface for the Second Life texture cache.

## Goals

- Browse, sort and filter through a large amount of textures in a cache
- Save textures to disk in a commonly-used image format
- Be fast and out of the way

## Build

Use [uv](https://docs.astral.sh/uv/) to build the final app.

```bash
uv run pyside6-deploy -c pysidedeploy.spec
```

## Develop

Use [uv](https://docs.astral.sh/uv/) to run the app in a debugger.


```bash
uv run lltexturecache-browser-qt
```