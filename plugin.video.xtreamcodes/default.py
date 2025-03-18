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
    """ Get user credentials and validate them """
    username = ADDON.getSetting("username").strip()
    password = ADDON.getSetting("password").strip()

    if not username or not password:
        return None
    return {"username": username, "password": password}

def build_main_menu():
    """ Main Menu - Show Login if Not Logged In, Otherwise Show Live TV """
    settings = get_settings()

    if not settings:
        xbmcgui.Dialog().ok("Xtream Codes IPTV", "Please enter your username and password in settings.")
        open_settings()
        return

    api = XtreamAPI()
    if not api.test_connection():
        xbmcgui.Dialog().ok("Error", "Invalid credentials or server is unreachable. Please check your settings.")
        open_settings()
        return

    # Live TV Section
    url = f"{BASE_URL}?mode=live"
    list_item = xbmcgui.ListItem(label="Live TV")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    # Settings Button
    url = f"{BASE_URL}?mode=settings"
    list_item = xbmcgui.ListItem(label="Settings")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    # Logout Button
    url = f"{BASE_URL}?mode=logout"
    list_item = xbmcgui.ListItem(label="Logout")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_live_categories():
    """ Display Live TV Categories """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI()
    categories = api.get_live_categories()

    if not categories:
        xbmcgui.Dialog().ok("Error", "No live TV categories found.")
        return

    for category in categories:
        url = f"{BASE_URL}?mode=live_streams&category_id={category['category_id']}"
        list_item = xbmcgui.ListItem(label=category["category_name"])
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_live_streams(category_id):
    """ Display Live TV Streams for a Category """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI()
    streams = api.get_live_streams(category_id)

    if not streams:
        xbmcgui.Dialog().ok("Error", "No streams found in this category.")
        return

    for stream in streams:
        url = f"{stream['stream_url']}"
        list_item = xbmcgui.ListItem(label=stream["name"])
        list_item.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def open_settings():
    """ Open the Kodi Plugin Settings and refresh UI """
    ADDON.openSettings()
    xbmc.executebuiltin("Container.Refresh")

def logout():
    """ Logout and Reset Credentials """
    ADDON.setSetting("username", "")
    ADDON.setSetting("password", "")
    xbmcgui.Dialog().ok("Xtream Codes IPTV", "You have been logged out.")
    xbmc.executebuiltin("Container.Refresh")

def router():
    """ Handle navigation """
    params = get_params()
    mode = params.get("mode")

    if mode is None:
        build_main_menu()
    elif mode == "live":
        show_live_categories()
    elif mode == "live_streams":
        show_live_streams(params.get("category_id"))
    elif mode == "settings":
        open_settings()
    elif mode == "logout":
        logout()

if __name__ == '__main__':
    router()
