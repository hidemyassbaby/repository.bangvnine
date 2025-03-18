import sys
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import urllib.parse
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

def main_menu():
    """Display the main menu."""
    xbmcplugin.setContent(int(sys.argv[1]), 'videos')
    
    # Live TV Categories
    url = f"{sys.argv[0]}?action=list_categories"
    li = xbmcgui.ListItem("Live TV Categories")
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=li, isFolder=True)

    # Favorites
    url = f"{sys.argv[0]}?action=favorites"
    li = xbmcgui.ListItem("Favorites")
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def list_categories():
    """List available categories."""
    categories = CACHE.get_cached_data("categories") or API.get_live_categories()
    
    if not categories:
        xbmcgui.Dialog().ok("Media4u TV", "No categories found or API error occurred!")
        return

    for category in categories:
        url = f"{sys.argv[0]}?action=list_streams&category_id={category['category_id']}"
        li = xbmcgui.ListItem(category["category_name"])
        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def list_streams(category_id):
    """List streams in a selected category."""
    streams = CACHE.get_cached_data(f"streams_{category_id}") or API.get_live_streams(category_id)

    if not streams:
        xbmcgui.Dialog().ok("Media4u TV", "No streams found or API error occurred!")
        return

    for stream in streams:
        if "stream_id" not in stream or "name" not in stream:
            xbmc.log(f"[Media4u TV] Skipping invalid stream entry: {stream}", xbmc.LOGWARNING)
            continue

        url = f"{sys.argv[0]}?action=play_stream&stream_url={urllib.parse.quote(stream['stream_url'])}"
        li = xbmcgui.ListItem(stream["name"])
        li.setInfo("video", {"title": stream["name"]})
        li.addContextMenuItems([("Add to Favorites", f"RunPlugin({sys.argv[0]}?action=add_favorite&stream_id={stream['stream_id']})")])

        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=li, isFolder=False)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def play_stream(stream_url):
    """Play a selected stream."""
    li = xbmcgui.ListItem(path=urllib.parse.unquote(stream_url))
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, li)

def add_favorite(stream_id):
    """Add a stream to favorites."""
    favorites = CACHE.get_cached_data("favorites") or []
    if stream_id not in favorites:
        favorites.append(stream_id)
        CACHE.set_cache("favorites", favorites)
        xbmcgui.Dialog().notification("Media4u TV", "Added to favorites!", xbmcgui.NOTIFICATION_INFO)

def show_favorites():
    """Show favorite streams."""
    favorites = CACHE.get_cached_data("favorites") or []
    if not favorites:
        xbmcgui.Dialog().ok("Media4u TV", "No favorites added yet.")
        return

    for stream_id in favorites:
        url = f"{sys.argv[0]}?action=play_stream&stream_url={urllib.parse.quote(API.get_stream_url(stream_id))}"
        li = xbmcgui.ListItem(f"Favorite Stream {stream_id}")
        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=li, isFolder=False)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def router(paramstring):
    """Router to handle plugin actions."""
    params = dict(urllib.parse.parse_qsl(paramstring))
    action = params.get("action")

    if action == "list_categories":
        list_categories()
    elif action == "list_streams":
        list_streams(params["category_id"])
    elif action == "play_stream":
        play_stream(params["stream_url"])
    elif action == "add_favorite":
        add_favorite(params["stream_id"])
    elif action == "favorites":
        show_favorites()
    else:
        main_menu()

if __name__ == "__main__":
    router(sys.argv[2][1:]) if len(sys.argv) > 2 else main_menu()
