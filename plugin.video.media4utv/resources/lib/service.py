import xbmc
import xbmcaddon
import time
from resources.lib.xtream_api import XtreamAPI  # ✅ Correct path
from resources.lib.cache import CacheManager  # ✅ Correct path

# Initialize Add-on
ADDON = xbmcaddon.Addon()
BASE_URL = "http://m3ufilter.media4u.top/player_api.php"
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")

# Initialize API and Cache
API = XtreamAPI(BASE_URL, USERNAME, PASSWORD)
CACHE = CacheManager()

# Background process to refresh cache every hour
while not xbmc.abortRequested:
    CACHE.update("categories", API.get_live_categories)
    xbmc.sleep(3600000)  # Refresh every 1 hour
