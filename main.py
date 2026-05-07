import asyncio
import os
import requests
from decimal import Decimal

from stable_ozon import OzonClient
from cache import load_cache, save_cache


# -------------------------
# TELEGRAM
# -------------------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send(text: str):
    if not TOKEN or not CHAT_ID:
        print("Telegram env not set")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=15
    )

    print("Telegram response:", response.text)


# -------------------------
# TARGETS
# -------------------------

TARGETS = [
    {
        "keyword": "Алиса Мини 3",
        "min_price": Decimal("1"),
        "max_price": Decimal("999999"),
    }
]


# -------------------------
# MAIN LOGIC
# -------------------------

def is_new(cache, item):
    return item["link"] not in cache


def mark(cache, item):
    cache[item["link"]] = True


async def run():
    print("Starting bot...")

    cache = load_cache()

    client = OzonClient()
    await client.start()

    send("🤖 Ozon bot started")

    for target in TARGETS:
        print(f"Searching: {target['keyword']}")

        try:
            items = await client.fetch(target["keyword"])

            print(f"Found items: {len(items)}")

            if not items:
                print("No items found")
                continue

            for item in items:

                if not is_new(cache, item):
                    continue

                if target["min_price"] <= item["price"] <= target["max_price"]:

                    text = (
                        "🔥 Найден товар\n\n"
                        f"{item['title']}\n"
                        f"{item['price']} ₽\n"
                        f"{item['link']}"
                    )

                    send(text)
                    mark(cache, item)

        except Exception as e:
            print("ERROR:", str(e))
            send(f"⚠️ Error: {str(e)}")

    await client.close()

    save_cache(cache)

    print("Done")


# -------------------------
# ENTRY
# -------------------------

if __name__ == "__main__":
    asyncio.run(run())
