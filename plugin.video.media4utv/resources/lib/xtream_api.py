import json
import os
import time
import xbmc

CACHE_FILE = os.path.expanduser("~/media4u_cache.json")
CACHE_TIME = 3600  # 1 hour

class XtreamAPI:
    def __init__(self):
        self._load_cache()

    def _load_cache(self):
        """Loads cached categories & streams."""
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
            if time.time() - cache.get("timestamp", 0) < CACHE_TIME:
                self.live_categories = cache.get("categories", [])
                self.live_streams = cache.get("streams", {})
                return
        self.live_categories = []
        self.live_streams = {}

    def get_live_categories(self):
        """Returns cached categories."""
        return self.live_categories

    def get_live_streams(self, category_id):
        """Returns cached streams for a category."""
        return self.live_streams.get(category_id, [])
