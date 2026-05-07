import json
import os

FILE = "cache.json"


def load_cache():
    if not os.path.exists(FILE):
        return {}
    return json.load(open(FILE, "r", encoding="utf-8"))


def save_cache(data):
    json.dump(data, open(FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
