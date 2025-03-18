import xbmc
import xbmcaddon
import time
import sys
import os

# Ensure correct module paths
sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))

from xtream_api import XtreamAPI  # ✅ Now directly from lib folder
from cache import CacheManager  # ✅ Now directly from lib folder

# Initialize Add-on
ADDON = xbmcaddon.Addon()
BASE_URL = "http://m3ufilter.media4u.top/player_api.php"
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")

# Initialize API and Cache
API = XtreamAPI(BASE_URL, USERNAME, PASSWORD)
CACHE = CacheManager()

def update_cache():
    """Update cache with new data."""
    try:
        live_categories = API.get_live_categories()
        CACHE.set_cache("categories", live_categories)
        xbmc.log("[Media4u TV] Cache updated successfully.", xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f"[Media4u TV] Cache update failed: {e}", xbmc.LOGERROR)

# First-time cache update
update_cache()

# Background process to refresh cache every hour
while not xbmc.abortRequested:
    update_cache()
    xbmc.sleep(3600000)  # Refresh every 1 hour
