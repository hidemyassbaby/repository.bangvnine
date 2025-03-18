import xbmc
import xbmcgui
import xbmcplugin
import os
import sys
import json
from urllib.parse import parse_qsl

# Import API
addon_path = os.path.dirname(__file__)
sys.path.append(addon_path)
from resources.lib.xtream_api import XtreamAPI

ADDON_HANDLE = int(sys.argv[1])
BASE_URL = "plugin://plugin.video.media4utv"
CATEGORIES_PER_PAGE = 10

def get_favorites():
    """Load favorites from file"""
    favorites_file = os.path.join(addon_path, "favorites.json")
    if os.path.exists(favorites_file):
        with open(favorites_file, "r") as f:
            return json.load(f)
    return {}

def save_favorites(favorites):
    """Save favorites to file"""
    favorites_file = os.path.join(addon_path, "favorites.json")
    with open(favorites_file, "w") as f:
        json.dump(favorites, f)

def build_main_menu(page=0):
    """Show paginated categories"""
    api = XtreamAPI()
    categories = api.get_live_categories()

    if not categories:
        xbmcgui.Dialog().ok("Media4U TV", "No Live TV categories found.")
        return

    start_idx = page * CATEGORIES_PER_PAGE
    end_idx = start_idx + CATEGORIES_PER_PAGE
    paginated_categories = categories[start_idx:end_idx]

    for category in paginated_categories:
        url = f"{BASE_URL}?mode=live_streams&category_id={category['category_id']}"
        list_item = xbmcgui.ListItem(label=category["category_name"])
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    # Pagination Controls
    if start_idx > 0:
        prev_url = f"{BASE_URL}?mode=main_menu&page={page-1}"
        prev_item = xbmcgui.ListItem(label="Previous Page")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=prev_url, listitem=prev_item, isFolder=True)

    if end_idx < len(categories):
        next_url = f"{BASE_URL}?mode=main_menu&page={page+1}"
        next_item = xbmcgui.ListItem(label="Next Page")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=next_url, listitem=next_item, isFolder=True)

    # Search Button
    search_url = f"{BASE_URL}?mode=search"
    search_item = xbmcgui.ListItem(label="Search")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=search_url, listitem=search_item, isFolder=False)

    # Favorites Button
    favorites_url = f"{BASE_URL}?mode=favorites"
    favorites_item = xbmcgui.ListItem(label="Favorites")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=favorites_url, listitem=favorites_item, isFolder=True)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_live_streams(category_id):
    """Show streams for selected category"""
    api = XtreamAPI()
    streams = api.get_live_streams(category_id)

    if not streams:
        xbmcgui.Dialog().ok("Media4U TV", "No streams found in this category.")
        return

    favorites = get_favorites()

    for stream in streams:
        stream_url = f"http://example.com/live/{stream['stream_id']}.m3u8"
        list_item = xbmcgui.ListItem(label=stream["name"])
        list_item.setArt({'icon': stream.get("stream_icon", "")})
        list_item.setInfo("video", {"title": stream["name"]})

        # Context Menu for Favorites
        favorite_action = "Remove from Favorites" if stream["stream_id"] in favorites else "Add to Favorites"
        favorite_url = f"{BASE_URL}?mode=toggle_favorite&stream_id={stream['stream_id']}&stream_name={stream['name']}"
        list_item.addContextMenuItems([(favorite_action, f'RunPlugin({favorite_url})')])

        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=stream_url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def search():
    """Search Streams & Categories"""
    query = xbmcgui.Dialog().input("Enter search query")
    if not query:
        return

    api = XtreamAPI()
    categories = api.get_live_categories()
    streams = []

    for category in categories:
        category_streams = api.get_live_streams(category["category_id"])
        if category_streams:
            streams.extend(category_streams)

    results = [s for s in streams if query.lower() in s["name"].lower()]

    if not results:
        xbmcgui.Dialog().ok("Media4U TV", "No results found.")
        return

    for stream in results:
        stream_url = f"http://example.com/live/{stream['stream_id']}.m3u8"
        list_item = xbmcgui.ListItem(label=stream["name"])
        list_item.setInfo("video", {"title": stream["name"]})
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=stream_url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_favorites():
    """Show Favorite Streams"""
    favorites = get_favorites()
    if not favorites:
        xbmcgui.Dialog().ok("Media4U TV", "No favorites added.")
        return

    for stream_id, stream_name in favorites.items():
        stream_url = f"http://example.com/live/{stream_id}.m3u8"
        list_item = xbmcgui.ListItem(label=stream_name)
        list_item.setInfo("video", {"title": stream_name})
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=stream_url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def toggle_favorite(stream_id, stream_name):
    """Add/Remove Stream from Favorites"""
    favorites = get_favorites()
    if stream_id in favorites:
        del favorites[stream_id]
    else:
        favorites[stream_id] = stream_name
    save_favorites(favorites)
    xbmcgui.Dialog().ok("Favorites", "Updated favorites list.")

if __name__ == "__main__":
    params = dict(parse_qsl(sys.argv[2][1:]))
    mode = params.get("mode", "main_menu")
    page = int(params.get("page", 0))

    if mode == "main_menu":
        build_main_menu(page)
    elif mode == "live_streams":
        show_live_streams(params["category_id"])
    elif mode == "search":
        search()
    elif mode == "favorites":
        show_favorites()
    elif mode == "toggle_favorite":
        toggle_favorite(params["stream_id"], params["stream_name"])
