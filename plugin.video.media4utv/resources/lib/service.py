import time
import os
import json
import requests
import xbmc

CACHE_FILE = os.path.expanduser("~/media4u_cache.json")
BASE_URL = "http://m3ufilter.media4u.top/player_api.php"
CACHE_TIME = 3600  # 1 hour

USERNAME = xbmcaddon.Addon().getSetting("username")
PASSWORD = xbmcaddon.Addon().getSetting("password")

def fetch_data(action, params=None):
    """Fetch data from Xtream Codes API."""
    params = params or {}
    params.update({
        "username": USERNAME,
        "password": PASSWORD,
        "action": action
    })
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        return response.json() if response.status_code == 200 else []
    except requests.exceptions.RequestException:
        return []

def update_cache():
    """Fetches latest categories and streams, saving to cache."""
    xbmc.log("Updating Media4U TV cache in the background...", xbmc.LOGINFO)

    categories = fetch_data("get_live_categories")
    streams = {}

    for category in categories:
        category_id = category["category_id"]
        streams[category_id] = fetch_data("get_live_streams", {"category_id": category_id})

    cache_data = {
        "timestamp": time.time(),
        "categories": categories,
        "streams": streams
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(cache_data, f)

    xbmc.log("Media4U TV cache updated successfully!", xbmc.LOGINFO)

class BackgroundService(xbmc.Monitor):
    """Runs in the background and updates cache every hour."""
    def __init__(self):
        super().__init__()
        while not self.waitForAbort(CACHE_TIME):  # Runs every 1 hour
            update_cache()

if __name__ == "__main__":
    BackgroundService()
