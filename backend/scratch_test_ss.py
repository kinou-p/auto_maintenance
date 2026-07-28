import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        c = await b.new_context(ignore_https_errors=True)
        
        async def _route_ddev(route, request):
            req_url = request.url
            parsed = urlparse(req_url)
            print(f"[ROUTE CHECK] {req_url} | netloc: {parsed.netloc}")
            if ".ddev.site" in parsed.netloc:
                new_netloc = parsed.netloc.replace(parsed.hostname or "", "host.docker.internal")
                new_url = parsed._replace(netloc=new_netloc).geturl()
                headers = {**request.headers, "host": parsed.netloc}
                print(f"[REROUTING] {req_url} -> {new_url} (Host: {parsed.netloc})")
                try:
                    await route.continue_(url=new_url, headers=headers)
                except Exception as ex:
                    print(f"[ROUTE ERR] {ex}")
                    await route.continue_()
            else:
                await route.continue_()

        await c.route("**/*", _route_ddev)
        page = await c.new_page()
        try:
            target = "http://larochelleportscenter-com-20260726-221202-950.ddev.site:8088/acteurs-du-territoire/"
            print("Navigating to:", target)
            res = await page.goto(target, timeout=10000)
            print("PAGE GOTO RESPONSE:", res.status if res else "None")
        except Exception as e:
            print("PAGE GOTO ERROR:", type(e).__name__, e)
        await b.close()

if __name__ == "__main__":
    asyncio.run(test())
