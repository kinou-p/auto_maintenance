import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--host-resolver-rules=MAP *.ddev.site 172.17.0.1",
            ]
        )
        c = await b.new_context(ignore_https_errors=True)
        page = await c.new_page()

        try:
            target = "http://larochelleportscenter-com-20260726-221202-950.ddev.site:8088/"
            print("Navigating to Homepage:", target)
            res = await page.goto(target, timeout=10000)
            print("HOMEPAGE RESPONSE:", res.status if res else "None", "FINAL URL:", res.url if res else "")
        except Exception as e:
            print("HOMEPAGE ERROR:", type(e).__name__, e)
        await b.close()

if __name__ == "__main__":
    asyncio.run(test())
