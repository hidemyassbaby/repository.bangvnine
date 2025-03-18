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
    """ Main Menu - Show Login if Not Logged In, Otherwise Show Categories """
    settings = get_settings()

    if not settings:
        url = f"{BASE_URL}?mode=login"
        list_item = xbmcgui.ListItem(label="Login")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    # Validate login before showing categories
    api = XtreamAPI(settings["username"], settings["password"])
    if not api.test_connection():
        xbmcgui.Dialog().ok("Error", "Invalid credentials or server is unreachable. Please check your settings.")
        open_settings()
        return

    categories = [
        ("Account Info", "account_info"),
        ("Live TV", "live"),
        ("Movies (VOD)", "movies"),
        ("TV Shows", "series")
    ]

    for name, mode in categories:
        url = f"{BASE_URL}?mode={urllib.parse.quote(mode)}"
        list_item = xbmcgui.ListItem(label=name)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    url = f"{BASE_URL}?mode=settings"
    list_item = xbmcgui.ListItem(label="Settings")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    url = f"{BASE_URL}?mode=logout"
    list_item = xbmcgui.ListItem(label="Logout")
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
    elif mode == "login":
        open_settings()
    elif mode == "settings":
        open_settings()
    elif mode == "logout":
        logout()

if __name__ == '__main__':
    router()
