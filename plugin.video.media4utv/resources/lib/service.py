import xbmc
import xbmcaddon
import time
from resources.lib.xtream_api import XtreamAPI 
from resources.lib.cache import CacheManager  

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
