import os
import json
import time
import xbmcvfs

CACHE_DIR = xbmcvfs.translatePath("special://profile/addon_data/plugin.video.media4utv/cache")
CACHE_FILE = os.path.join(CACHE_DIR, "cache.json")
CACHE_EXPIRY = 3600  # 1 hour

class CacheManager:
    def __init__(self):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    def _load_cache(self):
        if not os.path.exists(CACHE_FILE):
            return {}
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_cache(self, cache_data):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=4)
        except IOError:
            pass

    def get_cached_data(self, key):
        cache_data = self._load_cache()
        if key in cache_data and time.time() - cache_data[key]["timestamp"] < CACHE_EXPIRY:
            return cache_data[key]["data"]
        return None

    def set_cache(self, key, data):
        cache_data = self._load_cache()
        cache_data[key] = {"timestamp": time.time(), "data": data}
        self._save_cache(cache_data)
