import os
import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import json
from urllib.parse import parse_qsl, urlencode
from resources.lib.xtream_api import XtreamAPI
from resources.lib.cache import CacheManager

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmc.translatePath(ADDON.getAddonInfo('path'))
ICON_PATH = os.path.join(ADDON_PATH, 'resources', 'media')
HANDLE = int(sys.argv[1])

# API and Cache Setup
BASE_URL = "http://m3ufilter.media4u.top/player_api.php"
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")
API = XtreamAPI(BASE_URL, USERNAME, PASSWORD)
CACHE = CacheManager()

def get_icon(filename):
    return os.path.join(ICON_PATH, filename)

def add_directory_item(name, query, icon="folder.png", is_folder=True):
    url = f"{sys.argv[0]}?{urlencode(query)}"
    li = xbmcgui.ListItem(name)
    li.setArt({"icon": get_icon(icon), "thumb": get_icon(icon)})
    xbmcplugin.addDirectoryItem(HANDLE, url, li, is_folder)

def main_menu():
    xbmcplugin.setPluginCategory(HANDLE, "Media4u TV")
    xbmcplugin.setContent(HANDLE, "videos")

    add_directory_item("Live TV", {"action": "list_categories"}, icon="folder.png")
    add_directory_item("Search", {"action": "search"}, icon="search.png")
    add_directory_item("Favorites", {"action": "favorites"}, icon="favorites.png")

    xbmcplugin.endOfDirectory(HANDLE)

def list_categories():
    categories = CACHE.get("categories", API.get_live_categories)
    
    if not categories:
        xbmcgui.Dialog().ok("Media4u TV", "No live TV categories found.")
        return

    for category in categories:
        add_directory_item(category["category_name"], {"action": "list_streams", "category_id": category["category_id"]}, "folder.png")

    xbmcplugin.endOfDirectory(HANDLE)

def list_streams(category_id):
    streams = CACHE.get(f"streams_{category_id}", lambda: API.get_live_streams(category_id))

    if not streams:
        xbmcgui.Dialog().ok("Media4u TV", "No streams found in this category.")
        return

    for stream in streams:
        add_directory_item(stream["name"], {"action": "play", "stream_id": stream["stream_id"]}, "video.png", False)

    xbmcplugin.endOfDirectory(HANDLE)

def search():
    query = xbmcgui.Dialog().input("Search Streams")
    if not query:
        return
    
    results = API.search(query)
    if not results:
        xbmcgui.Dialog().ok("Media4u TV", "No results found.")
        return

    for stream in results:
        add_directory_item(stream["name"], {"action": "play", "stream_id": stream["stream_id"]}, "video.png", False)

    xbmcplugin.endOfDirectory(HANDLE)

def play(stream_id):
    stream_url = API.get_stream_url(stream_id)
    if not stream_url:
        xbmcgui.Dialog().ok("Media4u TV", "Failed to get stream URL.")
        return

    li = xbmcgui.ListItem(path=stream_url)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)

def router(params):
    if params:
        action = params.get("action", None)
        if action == "list_categories":
            list_categories()
        elif action == "list_streams":
            list_streams(params["category_id"])
        elif action == "search":
            search()
        elif action == "play":
            play(params["stream_id"])
    else:
        main_menu()

if __name__ == '__main__':
    router(dict(parse_qsl(sys.argv[2][1:])))
