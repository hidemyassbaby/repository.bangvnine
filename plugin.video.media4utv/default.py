import os
import sys
import json
import xbmc
import xbmcaddon
import xbmcplugin
import xbmcgui
import xbmcvfs  # ✅ Fix for path translation in Kodi 19+
import requests
from resources.lib.cache import CacheManager
from resources.lib.xtream_api import XtreamAPI

# Add-on Info
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_DATA_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))  # ✅ Fixed path translation
FAVORITES_FILE = os.path.join(ADDON_DATA_PATH, "favorites.json")
PAGE_LIMIT = 50  # ✅ Show 50 categories/streams per page

# Ensure addon data directory exists
if not os.path.exists(ADDON_DATA_PATH):
    os.makedirs(ADDON_DATA_PATH)

# Xtream API Credentials (Hardcoded)
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")
BASE_URL = "http://m3ufilter.media4u.top/player_api.php"
API = XtreamAPI(BASE_URL, USERNAME, PASSWORD)
CACHE = CacheManager()

# Read Favorites
def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# Save Favorites
def save_favorites(favorites):
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favorites, f, indent=4)

# Display Main Menu
def main_menu():
    xbmcplugin.setPluginCategory(int(sys.argv[1]), ADDON_NAME)
    
    add_directory_item("Live TV Categories", "list_categories", is_folder=True)
    add_directory_item("⭐ Favorites", "list_favorites", is_folder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# List Categories with Pagination & Caching
def list_categories(page=1):
    categories = CACHE.get_cached_data("categories")

    if not categories:
        for attempt in range(5):  # ✅ Retry API up to 5 times
            categories = API.get_live_categories()
            if categories:
                CACHE.set_cache("categories", categories)
                break
            xbmc.sleep(2000)  # Wait 2 seconds before retrying

    if not categories:
        xbmcgui.Dialog().ok(ADDON_NAME, "No categories found. Check credentials or try again later.")
        return

    start_index = (page - 1) * PAGE_LIMIT
    end_index = start_index + PAGE_LIMIT
    paged_categories = categories[start_index:end_index]

    for category in paged_categories:
        add_directory_item(category["category_name"], f"list_streams&category_id={category['category_id']}", is_folder=True)

    if end_index < len(categories):
        add_directory_item("➡ Next Page", f"list_categories&page={page + 1}", is_folder=True)
    if page > 1:
        add_directory_item("⬅ Previous Page", f"list_categories&page={page - 1}", is_folder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# List Streams with Pagination & Caching
def list_streams(category_id, page=1):
    streams = CACHE.get_cached_data(f"streams_{category_id}")

    if not streams:
        for attempt in range(5):  # ✅ Retry API up to 5 times
            streams = API.get_live_streams(category_id)
            if streams:
                CACHE.set_cache(f"streams_{category_id}", streams)
                break
            xbmc.sleep(2000)  # Wait 2 seconds before retrying

    if not streams:
        xbmcgui.Dialog().ok(ADDON_NAME, "No streams found in this category. Try again later.")
        return

    start_index = (page - 1) * PAGE_LIMIT
    end_index = start_index + PAGE_LIMIT
    paged_streams = streams[start_index:end_index]

    for stream in paged_streams:
        add_directory_item(stream["name"], f"play_stream&stream_id={stream['stream_id']}", is_folder=False)

    if end_index < len(streams):
        add_directory_item("➡ Next Page", f"list_streams&category_id={category_id}&page={page + 1}", is_folder=True)
    if page > 1:
        add_directory_item("⬅ Previous Page", f"list_streams&category_id={category_id}&page={page - 1}", is_folder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# Play Stream
def play_stream(stream_id):
    stream_url = f"{BASE_URL}?username={USERNAME}&password={PASSWORD}&stream_id={stream_id}"

    list_item = xbmcgui.ListItem(path=stream_url)
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, list_item)

# List Favorites
def list_favorites():
    favorites = load_favorites()

    if not favorites:
        xbmcgui.Dialog().ok(ADDON_NAME, "No favorites added.")
        return

    for fav in favorites:
        add_directory_item(fav["name"], f"play_stream&stream_id={fav['stream_id']}", is_folder=False)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# Add to Favorites
def add_favorite(name, stream_id):
    favorites = load_favorites()
    if not any(fav["stream_id"] == stream_id for fav in favorites):
        favorites.append({"name": name, "stream_id": stream_id})
        save_favorites(favorites)
        xbmcgui.Dialog().notification(ADDON_NAME, f"Added {name} to favorites.", xbmcgui.NOTIFICATION_INFO)

# Remove from Favorites
def remove_favorite(stream_id):
    favorites = load_favorites()
    favorites = [fav for fav in favorites if fav["stream_id"] != stream_id]
    save_favorites(favorites)
    xbmcgui.Dialog().notification(ADDON_NAME, "Removed from favorites.", xbmcgui.NOTIFICATION_INFO)

# Context Menu for Adding/Removing Favorites
def context_menu():
    params = dict(arg.split("=") for arg in sys.argv[2][1:].split("&"))
    action = params.get("action", "")

    if action == "add_favorite":
        add_favorite(params["name"], params["stream_id"])
    elif action == "remove_favorite":
        remove_favorite(params["stream_id"])

# Add Directory Item
def add_directory_item(name, action, is_folder=True):
    url = f"{sys.argv[0]}?action={action}"
    list_item = xbmcgui.ListItem(label=name)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, list_item, isFolder=is_folder)

# Route Actions
def router(param_string):
    params = dict(arg.split("=") for arg in param_string.split("&") if "=" in arg)
    action = params.get("action", "")

    if action == "list_categories":
        page = int(params.get("page", 1))
        list_categories(page)
    elif action == "list_streams":
        category_id = params["category_id"]
        page = int(params.get("page", 1))
        list_streams(category_id, page)
    elif action == "play_stream":
        play_stream(params["stream_id"])
    elif action == "list_favorites":
        list_favorites()
    elif action == "context_menu":
        context_menu()
    else:
        main_menu()

# Execute Router
if __name__ == "__main__":
    router(sys.argv[2][1:]) if len(sys.argv) > 2 else main_menu()
