import asyncio
import json
import re
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_fixed


BASE_URL = "https://www.ozon.ru/search/?text={query}"


class OzonClient:

    def __init__(self):
        self.browser = None

    async def start(self):
        p = await async_playwright().start()

        self.browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

    # =========================
    # JSON EXTRACTION CORE
    # =========================

    def extract_json_from_html(self, html: str):

        # ищем большие JSON блоки (Next.js / __NEXT_DATA__)
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL
        )

        if not match:
            return None

        try:
            return json.loads(match.group(1))
        except:
            return None

    # =========================
    # PARSE PRODUCTS FROM JSON
    # =========================

    def find_products(self, data):

        results = []

        def walk(obj):

            if isinstance(obj, dict):

                # Ozon product structure variations
                if "title" in obj and ("price" in obj or "offer" in obj):

                    title = obj.get("title")

                    price = None

                    # разные варианты структуры цены
                    if isinstance(obj.get("price"), dict):
                        price = obj["price"].get("value")

                    if isinstance(obj.get("offer"), dict):
                        price = obj["offer"].get("price")

                    if price and title:

                        link = obj.get("link") or obj.get("url") or ""

                        results.append({
                            "title": title,
                            "price": int(price),
                            "link": "https://www.ozon.ru" + link if link.startswith("/") else link
                        })

                for v in obj.values():
                    walk(v)

            elif isinstance(obj, list):
                for i in obj:
                    walk(i)

        walk(data)

        return results

    # =========================
    # MAIN FETCH
    # =========================

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def fetch(self, query: str):

        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
        )

        page = await context.new_page()

        url = BASE_URL.format(query=query)

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        await page.wait_for_timeout(5000)

        html = await page.content()

        data = self.extract_json_from_html(html)

        if not data:
            print("❌ No JSON found (possible block or layout change)")
            await context.close()
            return []

        products = self.find_products(data)

        await context.close()

        return products

    async def close(self):
        await self.browser.close()
