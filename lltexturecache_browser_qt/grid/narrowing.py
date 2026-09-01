"""Which textures the grid is showing, and in what order

A cache is filtered by colour and by whether a texture holds a picture at all.
Both answers come out of the colour scan, which arrives long after the grid
has been filled, so what is being asked for is kept here and applied whenever
there is something to apply it against.
"""

from dataclasses import dataclass, field

from PySide6.QtGui import QColor

from lltexturecache_browser_qt.cache.color import MATCH_FLOOR, ColorIndex


@dataclass
class Narrowing:
    colors: list[QColor] = field(default_factory=list)

    # whether the textures holding one solid colour, or nothing visible at all,
    # are being left out of the grid rather than only ringed in it
    simple_hidden: bool = False

    # what the colour scan found, which is nothing until it lands
    index: ColorIndex | None = None

    @property
    def asking(self) -> bool:
        return bool(self.colors) or self.simple_hidden

    @property
    def narrowed(self) -> bool:
        return bool(self.colors) and self.index is not None

    def hidden(self) -> int:
        if not self.simple_hidden or self.index is None:
            return 0

        return len(self.index.flat)

    def flat_uuids(self, uuids: list[str]) -> set[str]:
        if self.index is None:
            return set()

        return {uuids[row] for row in self.index.flat}

    def shown_rows(self, count: int) -> list[int] | None:
        """Nothing at all when something is being asked for that only the scan can
        answer and the scan has not landed: the caller leaves the grid as it is
        and this is asked again when it does.
        """

        if not self.asking:
            return list(range(count))

        if self.index is None:
            return None

        flat = self.index.flat if self.simple_hidden else set()

        kept = [row for row in range(count) if row not in flat]

        if not self.colors:
            return kept

        scores = self.index.scores(self.colors)

        # a texture has to hold some of every colour asked for, and the more
        # colours are asked for the less of each one any texture can be
        floor = MATCH_FLOOR / len(self.colors)

        kept = [row for row in kept if scores[row] >= floor]
        kept.sort(key=lambda row: -scores[row])

        return kept
