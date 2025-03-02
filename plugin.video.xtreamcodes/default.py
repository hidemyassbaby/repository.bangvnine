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
    server = ADDON.getSetting("server_url").strip()
    username = ADDON.getSetting("username").strip()
    password = ADDON.getSetting("password").strip()

    if not server or not username or not password:
        return None
    return {"server": server, "username": username, "password": password}

def build_main_menu():
    """ Main Menu - If Not Logged In, Show Only Login Button """
    settings = get_settings()

    if not settings:
        # Show Login Button Only
        url = f"{BASE_URL}?mode=login"
        list_item = xbmcgui.ListItem(label="🔑 Login")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    api = XtreamAPI(settings["server"], settings["username"], settings["password"])

    # Account Info
    user_info = api.get_user_info()
    expiry_date = user_info.get("exp_date", "Unknown")
    active_cons = user_info.get("active_cons", "0")
    max_cons = user_info.get("max_connections", "0")

    account_info = f"Account Info (Expires: {expiry_date})\nActive Connections: {active_cons}/{max_cons}"
    url = f"{BASE_URL}?mode=account_info"
    list_item = xbmcgui.ListItem(label=account_info)
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    # Categories
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

    # Settings Button
    url = f"{BASE_URL}?mode=settings"
    list_item = xbmcgui.ListItem(label="🔧 Settings")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    # Logout Button
    url = f"{BASE_URL}?mode=logout"
    list_item = xbmcgui.ListItem(label="🚪 Logout")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def open_settings():
    """ Open the Kodi Plugin Settings """
    ADDON.openSettings()

def logout():
    """ Logout and Reset Credentials """
    ADDON.setSetting("server_url", "")
    ADDON.setSetting("username", "")
    ADDON.setSetting("password", "")
    xbmcgui.Dialog().ok("Xtream Codes IPTV", "You have been logged out. Please restart the addon.")
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
