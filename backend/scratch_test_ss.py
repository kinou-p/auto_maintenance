import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        # Test avec page.set_extra_http_headers
        c = await b.new_context(ignore_https_errors=True)
        page = await c.new_page()
        await page.set_extra_http_headers({"Host": "larochelleportscenter-com-20260726-221202-950.ddev.site"})
        try:
            target = "http://172.17.0.1:8088/acteurs-du-territoire/"
            print("Navigating to IP with page.set_extra_http_headers:", target)
            res = await page.goto(target, timeout=10000)
            print("PAGE GOTO RESPONSE:", res.status if res else "None")
        except Exception as e:
            print("PAGE GOTO ERROR:", type(e).__name__, e)
        await b.close()

if __name__ == "__main__":
    asyncio.run(test())
