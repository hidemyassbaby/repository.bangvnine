import xbmc
import json
import os
import time

CACHE_FILE = os.path.join(xbmc.translatePath(xbmcaddon.Addon().getAddonInfo('profile')), "cache.json")

class CacheManager:
    def __init__(self):
        self.load_cache()

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as file:
                self.cache = json.load(file)
        else:
            self.cache = {}

    def save_cache(self):
        with open(CACHE_FILE, "w") as file:
            json.dump(self.cache, file)

    def get(self, key, fetch_func):
        if key in self.cache and (time.time() - self.cache[key]["timestamp"] < 3600):
            return self.cache[key]["data"]
        
        data = fetch_func()
        if data:
            self.cache[key] = {"timestamp": time.time(), "data": data}
            self.save_cache()

        return data

    def update(self, key, fetch_func):
        data = fetch_func()
        if data:
            self.cache[key] = {"timestamp": time.time(), "data": data}
            self.save_cache()
