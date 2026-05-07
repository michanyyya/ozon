import asyncio
from decimal import Decimal
from stable_ozon import OzonClient
from cache import load_cache, save_cache
import requests

TOKEN = "YOUR_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"


TARGETS = [
    {
        "keyword": "Алиса Мини 3",
        "min_price": Decimal("1"),
        "max_price": Decimal("999999"),
    }
]


def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )


def is_new(cache, item):
    return item["link"] not in cache


def mark_seen(cache, item):
    cache[item["link"]] = True


async def run():
    cache = load_cache()

    client = OzonClient()
    await client.start()

    for target in TARGETS:
        try:
            items = await client.fetch(target["keyword"])

            for item in items:
                if not is_new(cache, item):
                    continue

                if target["min_price"] <= item["price"] <= target["max_price"]:

                    send(
                        f"🔥 Новый товар\n\n"
                        f"{item['title']}\n"
                        f"{item['price']} ₽\n"
                        f"{item['link']}"
                    )

                    mark_seen(cache, item)

        except Exception as e:
            print("Error:", e)

    await client.close()
    save_cache(cache)


if __name__ == "__main__":
    asyncio.run(run())
