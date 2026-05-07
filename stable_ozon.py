import asyncio
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_fixed

BASE_URL = "https://www.ozon.ru/search/?text={}"


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

        await page.goto(
            BASE_URL.format(query),
            wait_until="domcontentloaded",
            timeout=60000,
        )

        await page.wait_for_timeout(4000)

        # проверка что страница реально загрузилась
        if "captcha" in page.url.lower():
            raise Exception("Blocked by captcha")

        items = await page.locator("div[data-index]").all()

        results = []

        for item in items[:10]:
            try:
                title = await item.locator("span").first.inner_text()
                price_text = await item.locator("span").filter(
                    has_text="₽"
                ).first.inner_text()

                price = int("".join(filter(str.isdigit, price_text)))

                link = await item.locator("a").first.get_attribute("href")

                results.append({
                    "title": title,
                    "price": price,
                    "link": "https://www.ozon.ru" + link
                })

            except:
                continue

        await context.close()
        return results

    async def close(self):
        await self.browser.close()
