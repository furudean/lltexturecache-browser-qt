"""Where the files packaged beside the code live

The assets sit at the root of the package rather than beside whichever module
happens to use them, so the path to them is worked out once here instead of
being counted out in directory hops from each caller.
"""

from pathlib import Path

ASSETS = Path(__file__).parent / "assets"

APP_ICON = ASSETS / "slcachegirl.png"
LICENCES = ASSETS / "licences"
