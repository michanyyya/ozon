import asyncio
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
                "--disable-blink-features=AutomationControlled",
            ],
        )

    # =========================
    # DETECTION HELPERS
    # =========================

    def is_blocked(self, html: str):
        blocked_signs = [
            "captcha",
            "robot",
            "access denied",
            "доступ ограничен"
        ]
        return any(x in html.lower() for x in blocked_signs)

    # =========================
    # FALLBACK TEXT PARSER
    # =========================

    def parse_from_text(self, html: str):

        items = []

        # ищем цены
        prices = re.findall(r"(\d[\d\s]{2,})\s?₽", html)

        # ищем названия (очень грубо, но работает как fallback)
        titles = re.findall(r'\"title\":\"(.*?)\"', html)

        for i in range(min(len(prices), len(titles))):
            try:
                price = int(prices[i].replace(" ", ""))
                title = titles[i][:120]

                items.append({
                    "title": title,
                    "price": price,
                    "link": "https://www.ozon.ru"
                })
            except:
                continue

        return items

    # =========================
    # UI PARSER (MAIN)
    # =========================

    def parse_ui(self, page):

        items = []

        cards = page.locator("div[data-widget='searchResultsV2'] a")

        count = cards.count()

        for i in range(min(count, 10)):
            try:
                card = cards.nth(i)

                text = card.inner_text()

                if "₽" not in text:
                    continue

                price_match = re.search(r"(\d[\d\s]+)\s?₽", text)
                price = int(price_match.group(1).replace(" ", "")) if price_match else 0

                link = card.get_attribute("href")

                items.append({
                    "title": text[:120],
                    "price": price,
                    "link": "https://www.ozon.ru" + (link or "")
                })

            except:
                continue

        return items

    # =========================
    # MAIN FETCH
    # =========================

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(3))
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

        await page.wait_for_timeout(6000)

        html = await page.content()

        # =========================
        # BLOCK DETECTION
        # =========================

        if self.is_blocked(html):
            print("🚨 BLOCK DETECTED")
            await context.close()
            return []

        # =========================
        # TRY UI PARSING FIRST
        # =========================

        items = self.parse_ui(page)

        # =========================
        # FALLBACK IF EMPTY
        # =========================

        if not items:
            print("⚠️ UI empty → fallback parser")
            items = self.parse_from_text(html)

        await context.close()

        return items

    async def close(self):
        await self.browser.close()
