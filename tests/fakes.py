"""Stand-ins for the cache entries the app is built around

A real Texture only comes out of a real TextureCache, which is a directory of
binary the suite has no business carrying around. What the app asks of one is
small and stable, so it is written out here instead.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from PySide6.QtGui import QColor, QPixmap
from texture_courier import Texture, TextureCache, TextureCacheError

CACHED_AT = datetime(2024, 3, 7, 15, 4, 5, tzinfo=UTC)
PAYLOAD = b"jpeg 2000 bytes"


@dataclass
class FakeTexture:
    uuid: str = "0e7c8bd7-8a4a-4c1e-9f61-1f0a2b3c4d5e"
    index: int = 3
    cached_size: int = 512
    image_size: int = 65536
    body_size: int = 65024
    complete: bool = True
    unreadable: bool = False
    payload: bytes = PAYLOAD
    time: datetime = field(default=CACHED_AT)

    def whole(self) -> bool:
        return self.complete

    def thumbnail_png(self) -> bytes | None:
        return None

    def jpeg_2000(self) -> bytes:
        if self.unreadable:
            raise TextureCacheError("no such texture")

        return self.payload

    def codestream(self) -> bytes:
        return self.jpeg_2000()


class FakeCache:
    """Stands in for a texture cache, which only the colour scan touches"""

    def __init__(self, count: int = 0) -> None:
        self._count = count

    def __len__(self) -> int:
        return self._count


def texture(**fields: object) -> Texture:
    """A stand-in, typed as the cache entry it stands in for

    Nothing the app asks of a texture is declared anywhere it could be
    implemented against, so the cast is where the duck typing is admitted to
    rather than something every call site repeats.
    """

    return cast("Texture", FakeTexture(**fields))  # type: ignore[arg-type]


def textures(count: int, **fields: object) -> list[Texture]:
    return [texture(uuid=f"texture-{row}", **fields) for row in range(count)]


def cache(count: int = 0) -> TextureCache:
    return cast("TextureCache", FakeCache(count))


def card(width: int = 8, height: int = 8, color: str = "red", *, alpha: int = 0xFF) -> QPixmap:
    """A pixmap standing in for a decoded texture

    Named for what it is used as: the app calls one of these a card wherever it
    lays a selection out as a pile. Filled flat, since nothing under test reads
    a pixel out of it — only its size, its shape and whether it has an alpha
    channel.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(color) if alpha == 0xFF else QColor(0, 0, 0, 0))

    return pixmap


class FakeCacheDir:
    """A cache directory a window can be opened on

    A real TextureCache wants a viewer's cache on disk. A window iterates it,
    counts it, names it and refreshes it, so this stands in for all four.
    """

    def __init__(self, cache_dir: "Path", textures: list[Texture]) -> None:
        self.cache_dir = cache_dir

        self._textures = list(textures)
        self._pending: list[Texture] | None = None
        self._changed: list[Texture] = []
        self._refusing: Exception | None = None

    def __iter__(self) -> "Iterator[Texture]":
        return iter(self._textures)

    def __len__(self) -> int:
        return len(self._textures)

    def rewrite(self, textures: list[Texture], *, changed: list[Texture] | None = None) -> None:
        """Stage what the next refresh will find

        The viewer writes to the cache while the app is holding it, and the
        app does not see any of it until it reads again, so what is staged
        here does not land until `refresh` is called.
        """

        self._pending = list(textures)
        self._changed = list(changed if changed is not None else textures)

    def refuse(self, error: Exception) -> None:
        """Make the next refresh fail, as a cache unplugged mid-session would"""

        self._refusing = error

    def refresh(self) -> "Iterator[Texture]":
        if self._refusing is not None:
            raise self._refusing

        if self._pending is not None:
            self._textures, self._pending = self._pending, None

        return iter(self._changed)


def cache_dir(path: "Path", count: int = 0) -> TextureCache:
    return cast("TextureCache", FakeCacheDir(path, textures(count)))
