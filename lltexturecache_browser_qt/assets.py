import platform
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"

APP_ICON = (ASSETS / "slcachegirl-mac.png") if platform.system() == "Darwin" else (ASSETS / "slcachegirl.png")
LICENCES = ASSETS / "licences"
