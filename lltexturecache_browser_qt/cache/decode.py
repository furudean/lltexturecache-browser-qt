from dataclasses import dataclass

import imagecodecs

# imagecodecs reaches its codecs through a module level __getattr__ that imports
# them by name. it is referenced so its included in the build by static analysis
from imagecodecs import _jpeg2k, _shared_cython  # noqa: F401
from texture_courier import TextureCacheError

GREYSCALE = 1
RGB = 3
RGBA = 4


@dataclass(frozen=True)
class Decoded:
    """A decoded texture, as tightly packed rows of 8 bit components"""

    pixels: bytes
    width: int
    height: int
    components: int

    @property
    def stride(self) -> int:
        """Bytes a row of pixels takes up"""

        return self.width * self.components


def decode_texture(codestream: bytes) -> Decoded:
    """Pixels from a codestream, in the nearest component count anything else understands"""

    # Everything decodes through openjpeg because qt only reads jpeg 2000 on macOS,
    # where it loads `qmacjp2` over Apple's ImageIO. Nothing equivalent ships in the qt
    # builds the pyside6 wheels repackage, so a reader path would come back null on
    # linux and windows.

    # It also takes the codestreams nothing else will: second life tags some of its
    # material textures `LL_RGBHM` and gives them five components, which pillow cannot
    # even name a mode for. The first three are colour and the fourth is opacity, and
    # the viewer drops whatever follows just as this does.

    try:
        # openjpeg lets go of the gil while it works, so this runs in the decode
        # pool as happily as qt's reader did
        decoded = imagecodecs.jpeg2k_decode(codestream)
    except imagecodecs.Jpeg2kError as e:
        # a RuntimeError on the way out of a decode thread says nothing about
        # which texture stopped it, and none of the callers are watching for one
        raise TextureCacheError(f"openjpeg could not decode the codestream: {e}") from e

    if decoded.dtype != "uint8":
        raise TextureCacheError(f"expected 8 bit components, decoded {decoded.dtype}")

    if decoded.ndim == 2:
        # openjpeg leaves the component axis off a single component image
        height, width = decoded.shape
        components = GREYSCALE
    elif decoded.ndim == 3:
        height, width, components = decoded.shape
    else:
        raise TextureCacheError(f"expected a two or three axis image, decoded {decoded.shape}")

    if components == GREYSCALE or components == RGB:
        # already the shape a reader wants, and contiguous as openjpeg wrote it
        return Decoded(decoded.tobytes(), width, height, components)

    if components == 2:
        # greyscale with opacity alongside, which only rgba can describe to both
        # of the consumers, so the one colour component is spread over three
        return Decoded(decoded[:, :, [0, 0, 0, 1]].tobytes(), width, height, RGBA)

    if components >= RGBA:
        # a slice of the last axis is strided, and every consumer wants the rows
        # the way an rgba buffer has them, which is what tobytes gathers into
        return Decoded(decoded[:, :, :RGBA].tobytes(), width, height, RGBA)

    raise TextureCacheError(f"decoded {components} components, which is not a picture")
