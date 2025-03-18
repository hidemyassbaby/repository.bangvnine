import os
import json
import time
import xbmcvfs

CACHE_EXPIRY = 3600  # Cache expires every 1 hour
ADDON_ID = "plugin.video.media4utv"
CACHE_DIR = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")
CACHE_FILE = os.path.join(CACHE_DIR, "cache.json")

class CacheManager:
    """Handles caching of API data for faster loading."""
    
    def __init__(self):
        """Ensure cache directory exists."""
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    def load_cache(self):
        """Load only cached data (ignores timestamp)."""
        if not os.path.exists(CACHE_FILE):
            return None  # No cache found

        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                return cache.get("data", None)  # Ensure only the stored data is returned
        except (json.JSONDecodeError, IOError):
            return None  # Cache corrupt, return None

    def save_cache(self, data):
        """Save cache with timestamp."""
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "data": data}, f, indent=4)
        except IOError:
            pass  # Failed to write cache

    def is_cache_expired(self):
        """Check if cache is expired or missing."""
        if not os.path.exists(CACHE_FILE):
            return True  # No cache, must update

        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                return time.time() - cache.get("timestamp", 0) > CACHE_EXPIRY
        except (json.JSONDecodeError, IOError):
            return True  # Cache corrupt, force update

    def clear_cache(self):
        """Clear all cached data."""
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
