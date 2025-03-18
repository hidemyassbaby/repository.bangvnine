import sys
import os
import xbmc
import xbmcaddon
import xbmcvfs
import time

# Ensure the `lib` folder is added to Python's path
ADDON_PATH = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo("path"))
LIB_PATH = os.path.join(ADDON_PATH, "resources", "lib")
sys.path.append(LIB_PATH)

from xtream_api import XtreamAPI
from cache import CacheManager

# Initialize Add-on
ADDON = xbmcaddon.Addon()
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")
SERVER_URL = "http://m3ufilter.media4u.top"
BASE_URL = f"{SERVER_URL}/player_api.php"

# Initialize API and Cache
API = XtreamAPI(BASE_URL, USERNAME, PASSWORD)
CACHE = CacheManager()

# Background process to refresh cache every hour
while not xbmc.Monitor().abortRequested():
    categories = API.get_live_categories()
    if categories:
        CACHE.set_cache("categories", categories)

        for category in categories:
            category_id = category["category_id"]
            streams = API.get_live_streams(category_id)
            if streams:
                CACHE.set_cache(f"streams_{category_id}", streams)

    xbmc.sleep(3600000)  # Refresh every 1 hour
