import sys
import urllib.parse
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
from resources.lib.xtream import XtreamAPI

ADDON = xbmcaddon.Addon()
ADDON_HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

def get_params():
    """ Parse URL parameters """
    param_string = sys.argv[2][1:]
    return dict(urllib.parse.parse_qsl(param_string))

def get_settings():
    """ Get user credentials """
    server = ADDON.getSetting("server_url")
    username = ADDON.getSetting("username")
    password = ADDON.getSetting("password")

    if not server or not username or not password:
        xbmcgui.Dialog().ok("Xtream Codes IPTV", "Please enter your server settings!")
        ADDON.openSettings()
        return None
    return {"server": server, "username": username, "password": password}

def build_main_menu():
    """ Main Menu - Categories for Video Addon """
    categories = [
        ("Live TV", "live"),
        ("Movies (VOD)", "movies"),
        ("TV Shows", "series")
    ]

    for name, mode in categories:
        url = f"{BASE_URL}?mode={mode}"
        list_item = xbmcgui.ListItem(label=name)
        list_item.setArt({"icon": "DefaultVideo.png"})
        list_item.setInfo("video", {"title": name})
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def list_live_tv():
    """ Display Live TV categories """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI(settings["server"], settings["username"], settings["password"])
    categories = api.get_live_categories()

    for category in categories:
        url = f"{BASE_URL}?mode=live_channels&category_id={category['category_id']}"
        list_item = xbmcgui.ListItem(label=category['category_name'])
        list_item.setInfo("video", {"title": category["category_name"]})
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def list_live_channels(category_id):
    """ Display Live TV channels """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI(settings["server"], settings["username"], settings["password"])
    channels = api.get_live_streams(category_id)

    for channel in channels:
        stream_url = f"{settings['server']}/live/{settings['username']}/{settings['password']}/{channel['stream_id']}.m3u8"
        url = f"{BASE_URL}?mode=play&url={urllib.parse.quote(stream_url)}"
        list_item = xbmcgui.ListItem(label=channel['name'])
        list_item.setArt({"icon": "DefaultVideo.png"})
        list_item.setProperty("IsPlayable", "true")
        list_item.setInfo("video", {"title": channel["name"]})
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def play_stream(stream_url):
    """ Play IPTV stream """
    list_item = xbmcgui.ListItem(path=stream_url)
    list_item.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(ADDON_HANDLE, True, list_item)

def router():
    """ Handle navigation """
    params = get_params()
    mode = params.get("mode")

    if mode is None:
        build_main_menu()
    elif mode == "live":
        list_live_tv()
    elif mode == "live_channels":
        category_id = params.get("category_id")
        if category_id:
            list_live_channels(category_id)
    elif mode == "play":
        play_stream(params.get("url"))

if __name__ == '__main__':
    router()
