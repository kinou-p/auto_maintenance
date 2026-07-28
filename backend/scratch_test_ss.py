import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        # Test avec route pour intercepter la requête initiale
        c = await b.new_context(ignore_https_errors=True)

        async def route_handler(route):
            url = route.request.url
            print(f"Intercepted request to: {url}")
            if "acteurs-du-territoire" in url:
                new_url = "http://172.17.0.1:8088/acteurs-du-territoire/"
                # On ne passe PAS 'headers' qui crashe Chromium avec ERR_INVALID_ARGUMENT
                await route.continue_(url=new_url)
            else:
                await route.continue_()

        await c.route("**/*", route_handler)
        page = await c.new_page()

        try:
            target = "http://larochelleportscenter-com-20260726-221202-950.ddev.site:8088/acteurs-du-territoire/"
            print("Navigating to ddev domain:", target)
            res = await page.goto(target, timeout=10000)
            print("PAGE GOTO RESPONSE:", res.status if res else "None")
        except Exception as e:
            print("PAGE GOTO ERROR:", type(e).__name__, e)
        await b.close()

if __name__ == "__main__":
    asyncio.run(test())
