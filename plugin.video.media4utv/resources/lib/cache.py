import os
import json
import time
import xbmc
import xbmcaddon
from xbmcvfs import translatePath  # ✅ Use xbmcvfs for correct path handling

# Get addon info
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

# Set cache directory path
CACHE_DIR = translatePath(f"special://profile/addon_data/{ADDON_ID}/cache")
CACHE_FILE = os.path.join(CACHE_DIR, "cache.json")
CACHE_EXPIRY = 3600  # Cache expires after 1 hour (3600 seconds)

class CacheManager:
    def __init__(self):
        """Ensure cache directory exists."""
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    def _load_cache(self):
        """Load cache data from file."""
        if not os.path.exists(CACHE_FILE):
            return {}

        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                return cache_data
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_cache(self, cache_data):
        """Save cache data to file."""
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=4)
        except IOError:
            pass

    def get_cached_data(self, key):
        """Retrieve cached data if it hasn't expired."""
        cache_data = self._load_cache()
        if key in cache_data:
            entry = cache_data[key]
            if time.time() - entry["timestamp"] < CACHE_EXPIRY:
                return entry["data"]
        
        return None  # Cache expired or key not found

    def set_cache(self, key, data):
        """Store data in cache with timestamp."""
        cache_data = self._load_cache()
        cache_data[key] = {"timestamp": time.time(), "data": data}
        self._save_cache(cache_data)

    def clear_cache(self):
        """Clear all cached data."""
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
