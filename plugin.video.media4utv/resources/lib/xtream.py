import os
import json
import time
import requests
import xbmc
import xbmcaddon

ADDON = xbmcaddon.Addon()
CACHE_FILE = os.path.join(xbmc.translatePath(ADDON.getAddonInfo("profile")), "cache.json")
CACHE_EXPIRY = 1800  # 30 minutes (1800 seconds)
BASE_URL = "https://m3ufilter.media4u.top/player_api.php"

class XtreamAPI:
    def __init__(self):
        self.username = ADDON.getSetting("username").strip()
        self.password = ADDON.getSetting("password").strip()
        self.session = requests.Session()

    def get_api_url(self, action):
        """ Build API URL """
        return f"{BASE_URL}?username={self.username}&password={self.password}&action={action}"

    def fetch_data(self, url):
        """ Fetch API Data with Exception Handling """
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException:
            xbmc.log("XtreamAPI: Request failed!", xbmc.LOGERROR)
        return None

    def is_cache_expired(self, key):
        """ Check if cache is expired """
        cache = self.load_cache()
        return key not in cache or (time.time() - cache.get(f"{key}_timestamp", 0) > CACHE_EXPIRY)

    def get_live_categories(self):
        """ Fetch and Cache Live TV Categories """
        if not self.is_cache_expired("categories"):
            return self.load_cache().get("categories", [])

        categories = self.fetch_data(self.get_api_url("get_live_categories"))
        if categories:
            categories = self.clean_data(categories)  # Remove emojis & special characters
            self.save_cache("categories", categories)
        return categories or []

    def get_live_streams(self, category_id):
        """ Fetch Live TV Streams (Use Caching) """
        cache_key = f"streams_{category_id}"
        if not self.is_cache_expired(cache_key):
            return self.load_cache().get(cache_key, [])

        streams = self.fetch_data(self.get_api_url(f"get_live_streams&category_id={category_id}"))
        if streams:
            streams = self.clean_data(streams)  # Remove emojis & special characters
            self.save_cache(cache_key, streams)
        return streams or []

    def load_cache(self):
        """ Load Cached Data """
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_cache(self, key, data):
        """ Save Cache to File """
        cache = self.load_cache()
        cache[key] = data
        cache[f"{key}_timestamp"] = time.time()  # Save last update time
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)

    def clean_data(self, data):
        """ Remove emojis & special characters from names """
        import re
        def remove_emoji(text):
            emoji_pattern = re.compile("["
                                       u"\U0001F600-\U0001F64F"  # emoticons
                                       u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                                       u"\U0001F680-\U0001F6FF"  # transport & map symbols
                                       u"\U0001F700-\U0001F77F"  # alchemical symbols
                                       u"\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
                                       u"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
                                       u"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
                                       u"\U0001FA00-\U0001FA6F"  # Chess Symbols
                                       u"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
                                       u"\U00002702-\U000027B0"  # Dingbats
                                       "]+", flags=re.UNICODE)
            return emoji_pattern.sub(r'', text)

        for item in data:
            if "category_name" in item:
                item["category_name"] = remove_emoji(item["category_name"])
            if "name" in item:
                item["name"] = remove_emoji(item["name"])
        return data
