from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_TIMEOUT = 20
DEFAULT_CURRENCY = "RUB"
SEARCH_BASE_URL = "https://www.ozon.ru/search/?text="

KEYWORDS = [
    "Алиса Миди",
    "Алиса Мини 3",
    "Алиса Станция 3",
    "Алиса Мини 3 Про",
]


@dataclass
class Target:
    keyword: str
    min_price: Decimal
    max_price: Decimal


@dataclass
class PriceResult:
    title: str
    price: Decimal
    currency: str
    url: str


def normalize_decimal(value: str | float | int | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse decimal value: {value!r}") from exc


def load_targets_from_csv(path: str) -> list[Target]:
    targets: list[Target] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"keyword", "min_price", "max_price"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"CSV must contain columns: {', '.join(sorted(required))}. "
                f"Got: {reader.fieldnames}"
            )

        for row in reader:
            targets.append(
                Target(
                    keyword=row["keyword"].strip(),
                    min_price=normalize_decimal(row["min_price"]),
                    max_price=normalize_decimal(row["max_price"]),
                )
            )
    return targets


def build_search_url(keyword: str) -> str:
    return SEARCH_BASE_URL + quote_plus(keyword)


def infer_name_from_url(url: str) -> str:
    try:
        path = urlparse(url).path.rstrip("/")
        tail = path.split("/")[-1]
        return tail or url
    except Exception:
        return url


JSON_LD_PRICE_PATTERNS = [
    re.compile(r'"price"\s*:\s*"?(\d+(?:[\.,]\d+)?)"?', re.IGNORECASE),
    re.compile(r'"lowPrice"\s*:\s*"?(\d+(?:[\.,]\d+)?)"?', re.IGNORECASE),
]


def fetch_html(session: requests.Session, url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    resp = session.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_from_json_ld(html: str, page_url: str) -> Optional[PriceResult]:
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for script in scripts:
        text = script.string or script.get_text(strip=True)
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue

        candidates: list[dict] = []
        if isinstance(data, dict):
            candidates.append(data)
            if "@graph" in data and isinstance(data["@graph"], list):
                candidates.extend([x for x in data["@graph"] if isinstance(x, dict)])
        elif isinstance(data, list):
            candidates.extend([x for x in data if isinstance(x, dict)])

        for item in candidates:
            if item.get("@type") not in {"Product", "Offer", "AggregateOffer"}:
                continue

            title = (
                item.get("name")
                or item.get("title")
                or infer_name_from_url(page_url)
            )

            offers = item.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
                currency = offers.get("priceCurrency") or DEFAULT_CURRENCY
                if price is not None:
                    return PriceResult(title=str(title), price=normalize_decimal(price), currency=str(currency), url=page_url)
            elif isinstance(offers, list) and offers:
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    price = offer.get("price") or offer.get("lowPrice") or offer.get("highPrice")
                    if price is not None:
                        currency = offer.get("priceCurrency") or DEFAULT_CURRENCY
                        return PriceResult(title=str(title), price=normalize_decimal(price), currency=str(currency), url=page_url)

    return None


def extract_from_embedded_json(html: str, page_url: str) -> Optional[PriceResult]:
    # Generic fallback for embedded state data.
    soup = BeautifulSoup(html, "html.parser")
    text_chunks: list[str] = []
    for script in soup.find_all("script"):
        text = script.string or script.get_text(strip=True)
        if text:
            text_chunks.append(text)

    joined = "\n".join(text_chunks)
    price = None
    for pattern in JSON_LD_PRICE_PATTERNS:
        m = pattern.search(joined)
        if m:
            price = normalize_decimal(m.group(1))
            break
    if price is None:
        return None

    title = infer_name_from_url(page_url)
    title_match = re.search(r'"name"\s*:\s*"([^"]{3,200})"', joined)
    if title_match:
        title = title_match.group(1)

    currency = DEFAULT_CURRENCY
    cur_match = re.search(r'"priceCurrency"\s*:\s*"([A-Z]{3})"', joined)
    if cur_match:
        currency = cur_match.group(1)

    return PriceResult(title=title, price=price, currency=currency, url=page_url)


def extract_price(session: requests.Session, url: str) -> PriceResult:
    html = fetch_html(session, url)

    result = extract_from_json_ld(html, url)
    if result:
        return result

    result = extract_from_embedded_json(html, url)
    if result:
        return result

    raise RuntimeError(f"Could not find price on page: {url}")


def extract_product_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/product/" not in href:
            continue

        if href.startswith("/"):
            href = "https://www.ozon.ru" + href

        href = href.split("?")[0]
        links.add(href)

    return list(links)


def search_products(session: requests.Session, keyword: str) -> list[str]:
    url = build_search_url(keyword)
    html = fetch_html(session, url)
    return extract_product_links(html)


def in_range(price: Decimal, min_price: Decimal, max_price: Decimal) -> bool:
    return min_price <= price <= max_price


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": False}
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()


def format_alert(target: Target, result: PriceResult) -> str:
    return (
        f"Keyword: {target.keyword}
"
        f"Title: {result.title}
"
        f"Price: {result.price} {result.currency}
"
        f"Range: {target.min_price} - {target.max_price}
"
        f"Link: {result.url}"
    )


def check_targets(targets: Iterable[Target]) -> list[str]:
    alerts: list[str] = []
    session = requests.Session()

    for target in targets:
        try:
            product_links = search_products(session, target.keyword)

            if not product_links:
                print(f"[EMPTY] {target.keyword}: no products found")
                continue

            for link in product_links[:10]:
                try:
                    result = extract_price(session, link)

                    title_lower = result.title.lower()
                    keyword_lower = target.keyword.lower()

                    if keyword_lower not in title_lower:
                        continue

                    if in_range(result.price, target.min_price, target.max_price):
                        alerts.append(format_alert(target, result))
                        print(f"[MATCH] {result.title}: {result.price} {result.currency}")
                    else:
                        print(f"[SKIP] {result.title}: {result.price} {result.currency}")

                except Exception as item_exc:
                    print(f"[ERR] Product parse error: {item_exc}")

        except Exception as exc:
            print(f"[ERR] {target.keyword}: {exc}", file=sys.stderr)

    return alerts


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Monitor Ozon product prices")
    p.add_argument("--csv", help="Path to CSV with keyword,min_price,max_price")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Polling interval in seconds")
    p.add_argument("--once", action="store_true", help="Run one check and exit")
    return p.parse_args()


TARGETS: list[Target] = [
    Target(keyword="Алиса Миди", min_price=Decimal("5000"), max_price=Decimal("15000")),
    Target(keyword="Алиса Мини 3", min_price=Decimal("4000"), max_price=Decimal("12000")),
    Target(keyword="Алиса Станция 3", min_price=Decimal("10000"), max_price=Decimal("25000")),
    Target(keyword="Алиса Мини 3 Про", min_price=Decimal("7000"), max_price=Decimal("18000")),
]


def main() -> int:
    args = parse_args()

    if args.csv:
        targets = load_targets_from_csv(args.csv)
    else:
        if not TARGETS:
            print("No targets configured. Edit TARGETS in the script or pass --csv.", file=sys.stderr)
            return 1
        targets = TARGETS

    while True:
        alerts = check_targets(targets)
        for message in alerts:
            print("\n" + message + "\n")
            send_telegram(message)

        if args.once:
            return 0

        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
