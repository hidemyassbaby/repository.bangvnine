import xbmc
import xbmcgui
import xbmcplugin
from xtream import XtreamAPI

ADDON_HANDLE = int(sys.argv[1])
BASE_URL = "plugin://plugin.video.xtreamcodes"

def build_main_menu():
    """ Main Menu - Show Login if Not Logged In, Otherwise Show Live TV """
    api = XtreamAPI()
    categories = api.get_live_categories()

    if not categories:
        xbmcgui.Dialog().ok("Xtream Codes IPTV", "No Live TV categories found or invalid credentials.")
        return

    for category in categories:
        category_id = category["category_id"]
        category_name = category["category_name"]
        url = f"{BASE_URL}?mode=live_streams&category_id={category_id}"
        list_item = xbmcgui.ListItem(label=category_name)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    # Refresh Cache Button
    refresh_url = f"{BASE_URL}?mode=refresh_cache"
    refresh_item = xbmcgui.ListItem(label="🔄 Refresh Cache")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=refresh_url, listitem=refresh_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_live_streams(category_id):
    """ Show Streams for Selected Category """
    api = XtreamAPI()
    streams = api.get_live_streams(category_id)

    if not streams:
        xbmcgui.Dialog().ok("Xtream Codes IPTV", "No streams found in this category.")
        return

    for stream in streams:
        stream_url = f"http://example.com/live/{stream['stream_id']}.m3u8"
        list_item = xbmcgui.ListItem(label=stream["name"])
        list_item.setArt({'icon': stream.get("stream_icon", "")})
        list_item.setInfo("video", {"title": stream["name"]})
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=stream_url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def refresh_cache():
    """ Manually Refresh the Cache """
    api = XtreamAPI()
    api.get_live_categories()  # Force update
    xbmcgui.Dialog().ok("Cache Refreshed", "Live TV categories have been updated.")
    xbmc.executebuiltin("Container.Refresh")  # Reload menu

if __name__ == "__main__":
    params = dict(parse_qsl(sys.argv[2][1:]))
    mode = params.get("mode")

    if mode is None:
        build_main_menu()
    elif mode == "live_streams":
        category_id = params.get("category_id")
        if category_id:
            show_live_streams(category_id)
    elif mode == "refresh_cache":
        refresh_cache()
