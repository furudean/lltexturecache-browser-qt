import imagecodecs
from texture_courier import TextureCacheError
from texture_courier.encode import codestream_size

# qt and pillow both stop at rgba, so this is the count past which a codestream
# has to go the long way round
MAX_READER_COMPONENTS = 4


def extra_components(codestream: bytes) -> bool:
    """Whether a codestream carries more components than an image reader takes"""

    return codestream_size(codestream)[2] > MAX_READER_COMPONENTS


def decode_rgba(codestream: bytes) -> tuple[bytes, int, int]:
    """Colour and opacity from a codestream, as tightly packed rgba rows"""

    # The codestreams an image reader will not take can be decoded through
    # openjpeg for compatibility

    # Second life encodes some of its material textures with five components rather
    # than the four an rgba image has, and tags them `LL_RGBHM`. Neither reader the
    # rest of the app leans on will touch one: qt's jp2 plugin reports the file as
    # readable and then fails on the data, and pillow only knows how to name 1-4
    # component images, so it cannot even work out a mode. The codestream itself is
    # fine, and openjpeg decodes it without complaint.

    # The viewer keeps a four component thumbnail for every one of these in its fast
    # cache, so the extra components are not part of the picture it draws. The first
    # three are colour and the fourth is opacity, exactly as in an rgba texture, and
    # whatever follows is dropped the same way the viewer drops it.

    try:
        # openjpeg lets go of the gil while it works, so this runs in the decode
        # pool as happily as qt's reader does
        decoded = imagecodecs.jpeg2k_decode(codestream)
    except imagecodecs.Jpeg2kError as e:
        # a RuntimeError on the way out of a decode thread says nothing about
        # which texture stopped it, and none of the callers are watching for one
        raise TextureCacheError(f"openjpeg could not decode the codestream: {e}") from e

    if decoded.ndim != 3 or decoded.shape[2] < MAX_READER_COMPONENTS:
        raise TextureCacheError(f"expected at least {MAX_READER_COMPONENTS} components, decoded {decoded.shape}")

    if decoded.dtype != "uint8":
        raise TextureCacheError(f"expected 8 bit components, decoded {decoded.dtype}")

    height, width, _ = decoded.shape

    # a slice of the last axis is strided, and both consumers want the rows the way
    # an rgba buffer has them, which is what tobytes gathers a strided slice into
    return decoded[:, :, :MAX_READER_COMPONENTS].tobytes(), width, height
