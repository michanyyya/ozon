import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import random

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8647208789:AAHO_bvEcYvT1B_o9OMJsXecFSMnfRNooPk"
TELEGRAM_CHAT_ID = "babatum001"

PRODUCTS = [
    {"name": "Алиса Мини 3", "search": "алиса мини 3", "price_min": 6000, "price_max": 8000},
    {"name": "Алиса Миди", "search": "алиса миди", "price_min": 10000, "price_max": 12000}
]

ALERT_MEMORY_FILE = "sent_alerts.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Referer": "https://www.ozon.ru/"
    }

def load_sent_alerts():
    if os.path.exists(ALERT_MEMORY_FILE):
        with open(ALERT_MEMORY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_sent_alerts(alerts):
    with open(ALERT_MEMORY_FILE, 'w') as f:
        json.dump(alerts, f, indent=2)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.ok
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

def search_ozon(query, max_pages=2):
    results = []
    session = requests.Session()
    
    for page in range(1, max_pages + 1):
        url = f"https://www.ozon.ru/search/?text={query}&page={page}"
        try:
            print(f"  Страница {page}...")
            response = session.get(url, headers=get_headers(), timeout=20)
            
            if response.status_code != 200:
                print(f"  Ошибка {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.select('[data-testid="grid-cell"]')
            
            if not cards:
                cards = soup.select('div[class*="tile"]')
            
            for card in cards:
                price_elem = card.select_one('span[class*="price"]') or card.select_one('div[class*="price"] span')
                if not price_elem:
                    continue
                
                import re
                digits = re.findall(r'\d+', price_elem.get_text().replace(' ', ''))
                if not digits:
                    continue
                price = int(''.join(digits))
                
                link = card.select_one('a')
                if link and link.get('href'):
                    href = link.get('href')
                    if href.startswith('/'):
                        href = 'https://www.ozon.ru' + href
                    results.append({"price": price, "url": href})
            
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"  Ошибка: {e}")
            continue
    
    unique = []
    seen = set()
    for item in results:
        if item['url'] not in seen:
            seen.add(item['url'])
            unique.append(item)
    return unique

def run_parser():
    print(f"\n{'='*50}")
    print(f"Запуск: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    sent = load_sent_alerts()
    
    for p in PRODUCTS:
        print(f"\n--- {p['name']} ---")
        items = search_ozon(p['search'])
        
        if not items:
            print(f"  Товаров не найдено")
            continue
        
        items.sort(key=lambda x: x['price'])
        print(f"  Мин. цена: {items[0]['price']} руб")
        
        found = None
        for item in items:
            if p['price_min'] <= item['price'] <= p['price_max']:
                found = item
                break
        
        if found:
            key = f"{p['name']}_{found['url']}"
            if key not in sent:
                msg = f"🔔 <b>{p['name']}</b>\n💰 Цена: {found['price']} ₽\n📊 Диапазон: {p['price_min']} - {p['price_max']} ₽\n🔗 {found['url']}"
                send_telegram_message(msg)
                sent.append(key)
                print(f"  ✅ Уведомление отправлено!")
            else:
                print(f"  ⏩ Уже уведомляли")
        else:
            sent = [k for k in sent if not k.startswith(p['name'])]
            print(f"  ❌ Нет товаров в диапазоне")
    
    save_sent_alerts(sent)
    print(f"\nГотово: {datetime.now().strftime('%H:%M:%S')}")

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/run':
            threading.Thread(target=run_parser).start()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Parser started')
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        pass

def start_webserver():
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

if __name__ == "__main__":
    # Запускаем веб-сервер
    threading.Thread(target=start_webserver, daemon=True).start()
    
    print(f"✅ Парсер запущен!")
    print(f"📍 Адрес: https://ozon-mfq9.onrender.com")
    print(f"⏰ Проверка цен каждый час")
    
    # Запускаем бесконечный цикл проверки
    while True:
        run_parser()
        print("\n⏳ Жду 1 час до следующей проверки...\n")
        time.sleep(3600)  # 1 час
