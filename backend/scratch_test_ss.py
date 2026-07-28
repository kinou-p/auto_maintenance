import asyncio
import sys
from pathlib import Path

# Fix path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.managers.screenshot_manager import ScreenshotManager

async def test():
    pages = [
        {"url": "http://larochelleportscenter-com-20260726-221202-950.ddev.site:8088/acteurs-du-territoire/", "name": "acteurs-du-territoire", "type": "page"}
    ]
    sm = ScreenshotManager("larochelleportscenter-com-20260726-221202-950")
    results = await sm.capture_screenshots(pages, "before")
    print("RESULTS:", results)

if __name__ == "__main__":
    asyncio.run(test())
