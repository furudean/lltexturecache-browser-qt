"""The one place the app reaches past texture_courier's public API

A thumbnail is stored in the cache alongside the mip level it was reduced
from, which is the only thing in the cache that says how large the texture
behind it really is. texture_courier hands over the encoded thumbnail and
nothing else, so that level is read through its internals instead.

Kept to this module so the reach is one import rather than a habit: if
texture_courier publishes the level, only this file changes.
"""

from texture_courier import TextureCache
from texture_courier.core import Thumbnail, read_fast_cache

__all__ = ["Thumbnail", "stored_thumbnail"]


def stored_thumbnail(cache: TextureCache, index: int) -> Thumbnail | None:
    """The thumbnail as the cache holds it, which knows what it was reduced from

    Nothing at all when the cache has no fast-cache file beside it, which is
    a cache the viewer has not finished writing yet.
    """

    fast_cache = cache.fast_cache_file

    return read_fast_cache(fast_cache, index) if fast_cache is not None else None
