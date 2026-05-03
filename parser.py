import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8647208789:AAHbaUUUxIi_M-ROAR1ldZ1cmd2Frk17j-o"
TELEGRAM_CHAT_ID = "babatum001"

PRODUCTS = [
    {
        "name": "Алиса Мини 3",
        "search": "алиса мини 3",
        "price_min": 6000,
        "price_max": 8000
    },
    {
        "name": "Алиса Миди",
        "search": "алиса миди",
        "price_min": 10000,
        "price_max": 12000
    }
]

ALERT_MEMORY_FILE = "sent_alerts.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
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
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.ok
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")
        return False

def search_ozon(query, max_pages=3):
    results = []
    
    for page in range(1, max_pages + 1):
        url = f"https://www.ozon.ru/search/?text={query}&page={page}"
        
        try:
            print(f"  Парсинг страницы {page}...")
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            product_cards = soup.select('[data-testid="grid-cell"]') or \
                           soup.select('.widget-search-result-container div[class*="tile"]') or \
                           soup.select('div[data-widget="searchResultsV2"] div[class*="card"]')
            
            if not product_cards:
                product_cards = soup.select('div[class*="a1c2"]')
            
            for card in product_cards:
                price_elem = None
                price_selectors = [
                    'span[class*="final-price"]',
                    'span[class*="price-"]',
                    'div[class*="price"] span',
                    'span[data-testid="price-current"]'
                ]
                
                for selector in price_selectors:
                    price_elem = card.select_one(selector)
                    if price_elem:
                        break
                
                if not price_elem:
                    continue
                
                price_text = price_elem.get_text(strip=True)
                import re
                price_match = re.search(r'(\d+[\s\d]*)', price_text)
                if not price_match:
                    continue
                price_str = price_match.group(1).replace('\u2009', '').replace(' ', '')
                try:
                    price = int(price_str)
                except:
                    continue
                
                title_elem = card.select_one('span[class*="tsBody"]') or \
                            card.select_one('div[class*="title"]') or \
                            card.select_one('a[class*="title"]')
                title = title_elem.get_text(strip=True) if title_elem else "Неизвестно"
                
                link_elem = card.select_one('a')
                if link_elem and link_elem.get('href'):
                    href = link_elem.get('href')
                    if not href.startswith('http'):
                        href = 'https://www.ozon.ru' + href
                else:
                    href = f"https://www.ozon.ru/search/?text={query}"
                
                results.append({
                    "title": title[:100],
                    "price": price,
                    "url": href
                })
            
            time.sleep(2)
            
        except Exception as e:
            print(f"  Ошибка при парсинге страницы {page}: {e}")
            continue
    
    unique_results = []
    seen_urls = set()
    for item in results:
        if item['url'] not in seen_urls:
            seen_urls.add(item['url'])
            unique_results.append(item)
    
    return unique_results

def check_product(product):
    print(f"\n--- Проверяем: {product['name']} ---")
    
    items = search_ozon(product['search'], max_pages=2)
    
    if not items:
        print(f"  Не найдено товаров по запросу '{product['search']}'")
        return None
    
    items.sort(key=lambda x: x['price'])
    
    for item in items:
        if product['price_min'] <= item['price'] <= product['price_max']:
            print(f"  ✅ НАЙДЕН! {item['title'][:50]} - {item['price']} руб")
            return item
    
    print(f"  ❌ Товаров в диапазоне {product['price_min']}-{product['price_max']} не найдено")
    print(f"  Самая низкая цена: {items[0]['price']} руб")
    return None

def main():
    print(f"\n{'='*50}")
    print(f"Запуск парсера: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    sent_alerts = load_sent_alerts()
    
    for product in PRODUCTS:
        found_item = check_product(product)
        
        if found_item:
            alert_key = f"{product['name']}_{found_item['url']}"
            
            if alert_key not in sent_alerts:
                message = f"""
🔔 <b>НАШЕЛ ТОВАР В ДИАПАЗОНЕ!</b>

<b>Товар:</b> {product['name']}
<b>Конкретный товар:</b> {found_item['title']}
<b>Цена:</b> {found_item['price']:,} ₽
<b>Диапазон:</b> {product['price_min']:,} - {product['price_max']:,} ₽

<b>Ссылка:</b> {found_item['url']}

🕐 Проверено: {datetime.now().strftime('%H:%M:%S')}
                """.replace(',', ' ')
                
                print(f"Отправляю уведомление о {product['name']}")
                send_telegram_message(message)
                sent_alerts.append(alert_key)
            else:
                print(f"Уведомление о {product['name']} уже отправлялось, пропускаем")
        else:
            keys_to_remove = [k for k in sent_alerts if k.startswith(product['name'])]
            for key in keys_to_remove:
                sent_alerts.remove(key)
                print(f"Сброшен флаг уведомления для {product['name']}")
    
    save_sent_alerts(sent_alerts)
    
    print(f"\nПарсер завершил работу в {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()