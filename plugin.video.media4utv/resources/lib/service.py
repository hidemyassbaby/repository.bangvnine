import xbmc
import xbmcaddon
import time
from resources.lib.xtream_api import XtreamAPI
from resources.lib.cache import CacheManager

ADDON = xbmcaddon.Addon()
BASE_URL = "http://m3ufilter.media4u.top/player_api.php"
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")
API = XtreamAPI(BASE_URL, USERNAME, PASSWORD)
CACHE = CacheManager()

while not xbmc.abortRequested:
    CACHE.update("categories", API.get_live_categories)
    xbmc.sleep(3600000)  # Refresh every 1 hour
