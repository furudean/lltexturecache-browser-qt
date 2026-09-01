"""Stand-ins for the cache entries the app is built around

A real Texture only comes out of a real TextureCache, which is a directory of
binary the suite has no business carrying around. What the app asks of one is
small and stable, so it is written out here instead.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from texture_courier import Texture, TextureCache, TextureCacheError

CACHED_AT = datetime(2024, 3, 7, 15, 4, 5, tzinfo=UTC)
PAYLOAD = b"jpeg 2000 bytes"


@dataclass
class FakeTexture:
    uuid: str = "0e7c8bd7-8a4a-4c1e-9f61-1f0a2b3c4d5e"
    index: int = 3
    cached_size: int = 512
    image_size: int = 65536
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
