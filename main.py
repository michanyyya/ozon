import asyncio
import os
import requests
from decimal import Decimal

from stable_ozon import OzonClient
from cache import load_cache, save_cache


# =========================
# TELEGRAM CONFIG
# =========================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send(text: str):
    if not TOKEN or not CHAT_ID:
        print("❌ Telegram env not set")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=15
        )
        print("📨 Telegram:", r.text)
    except Exception as e:
        print("❌ Telegram error:", e)


# =========================
# TARGETS
# =========================

TARGETS = [
    {
        "keyword": "Алиса Мини 3",
        "min_price": Decimal("1"),
        "max_price": Decimal("999999"),
    }
]


# =========================
# HELPERS
# =========================

def is_new(cache, item):
    return item["link"] not in cache


def mark(cache, item):
    cache[item["link"]] = True


# =========================
# MAIN
# =========================

async def run():
    print("🚀 Bot starting...")

    cache = load_cache()

    client = OzonClient()
    await client.start()

    send("🤖 Ozon bot started")

    for target in TARGETS:

        print(f"🔎 Searching: {target['keyword']}")

        try:
            items = await client.fetch(target["keyword"])

            print(f"📦 Found items: {len(items)}")

            # 🔴 ДИАГНОСТИКА (очень важно)
            if not items:
                print("⚠️ EMPTY RESULT FROM OZON")
                send("⚠️ Ozon returned 0 items (possible block or no results)")
                continue

            for item in items:

                print("ITEM:", item)

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
            print("❌ ERROR:", str(e))
            send(f"⚠️ Error in Ozon parser:\n{str(e)}")

    await client.close()

    save_cache(cache)

    print("✅ Done")


# =========================
# ENTRY
# =========================

if __name__ == "__main__":
    asyncio.run(run())
