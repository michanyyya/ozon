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
TELEGRAM_TOKEN = "8647208789:AAHO_bvEcYvT1B_o9OMJsXecFSMnfRNooPk"  # ЗАМЕНИ НА НОВЫЙ
TELEGRAM_CHAT_ID = "babatum001"

PRODUCTS = [
    {"name": "Алиса Мини 3", "search": "алиса мини 3", "price_min": 6000, "price_max": 8000},
    {"name": "Алиса Миди", "search": "алиса миди", "price_min": 10000, "price_max": 12000}
]

ALERT_MEMORY_FILE = "sent_alerts.json"

# Список разных User-Agent для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
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
    except:
        return False

def search_ozon(query, max_pages=2):
    results = []
    session = requests.Session()
    
    for page in range(1, max_pages + 1):
        url = f"https://www.ozon.ru/search/?text={query}&page={page}"
        
        try:
            print(f"  Запрос страницы {page}...")
            response = session.get(url, headers=get_headers(), timeout=20)
            
            if response.status_code == 403:
                print(f"  Блокировка 403, пробуем другой User-Agent...")
                # Пауза подольше
                time.sleep(5)
                continue
                
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Пробуем разные селекторы
            cards = soup.select('[data-testid="grid-cell"]')
            if not cards:
                cards = soup.select('div[class*="tile"]')
            if not cards:
                cards = soup.select('div[data-index]')
            
            print(f"  Найдено карточек: {len(cards)}")
            
            for card in cards:
                # Ищем цену разными способами
                price_str = None
                price_selectors = [
                    'span[class*="final"]',
                    'span[class*="price"]',
                    'div[class*="price"] span',
                    'span[data-testid="price-current"]',
                    'span[class*="c3a1"]'
                ]
                
                for sel in price_selectors:
                    elem = card.select_one(sel)
                    if elem:
                        price_str = elem.get_text(strip=True)
                        break
                
                if not price_str:
                    continue
                
                # Извлекаем число
                import re
                digits = re.findall(r'\d+', price_str.replace(' ', ''))
                if not digits:
                    continue
                price = int(''.join(digits))
                
                # Ссылка
                link = card.select_one('a')
                if link and link.get('href'):
                    href = link.get('href')
                    if href.startswith('/'):
                        href = 'https://www.ozon.ru' + href
                    results.append({"price": price, "url": href})
            
            time.sleep(random.uniform(2, 4))  # случайная задержка
            
        except Exception as e:
            print(f"  Ошибка страницы {page}: {e}")
            continue
    
    # Убираем дубликаты по url
    unique = []
    seen = set()
    for item in results:
        if item['url'] not in seen:
            seen.add(item['url'])
            unique.append(item)
    
    return unique

def run_parser():
    print(f"\n{'='*50}")
    print(f"Запуск: {datetime.now()}")
    print(f"{'='*50}")
    
    sent = load_sent_alerts()
    
    for p in PRODUCTS:
        print(f"\n--- {p['name']} ---")
        items = search_ozon(p['search'])
        
        if not items:
            print(f"  Не найдено товаров")
            continue
        
        items.sort(key=lambda x: x['price'])
        print(f"  Самая низкая цена: {items[0]['price']} руб")
        
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
            # Сбрасываем флаги, если вышли из диапазона
            sent = [k for k in sent if not k.startswith(p['name'])]
            print(f"  ❌ Товаров в диапазоне нет")
    
    save_sent_alerts(sent)
    print(f"\nГотово: {datetime.now()}")

# ========== ВЕБ-СЕРВЕР ==========
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
        pass  # отключаем лишний лог

def start_webserver():
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_webserver, daemon=True).start()
    print(f"Сервер запущен на порту {os.environ.get('PORT', 8000)}")
    
    # При первом запуске сразу проверим
    run_parser()
    
    # Держим процесс живым
    while True:
        time.sleep(60)
