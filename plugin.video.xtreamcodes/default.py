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
    server = ADDON.getSetting("server_url").strip()
    username = ADDON.getSetting("username").strip()
    password = ADDON.getSetting("password").strip()

    if not server or not username or not password:
        return None
    return {"server": server, "username": username, "password": password}

def build_main_menu():
    """ Main Menu - Show Login if Not Logged In, Otherwise Show Categories """
    settings = get_settings()

    if not settings:
        # Show Login Button Only
        url = f"{BASE_URL}?mode=login"
        list_item = xbmcgui.ListItem(label="🔑 Login")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    api = XtreamAPI(settings["server"], settings["username"], settings["password"])
    
    # Categories
    categories = [
        ("📜 Account Info", "account_info"),
        ("📺 Live TV", "live"),
        ("🎬 Movies (VOD)", "movies"),
        ("📀 TV Shows", "series")
    ]

    for name, mode in categories:
        url = f"{BASE_URL}?mode={mode}"
        list_item = xbmcgui.ListItem(label=name.encode("utf-8").decode("utf-8"))  # Fixes encoding issue
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

def show_account_info():
    """ Display full account information in a folder structure """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI(settings["server"], settings["username"], settings["password"])
    user_info = api.get_user_info()

    if not user_info:
        xbmcgui.Dialog().ok("Error", "Could not fetch account info. Please check your login details.")
        logout()
        return

    details = {
        "Status": user_info.get("status", "Unknown"),
        "Expiry Date": user_info.get("exp_date", "Unknown"),
        "Active Connections": user_info.get("active_cons", "0"),
        "Max Connections": user_info.get("max_connections", "0"),
        "Is Trial": "Yes" if user_info.get("is_trial", "0") == "1" else "No",
        "Created At": user_info.get("created_at", "Unknown"),
        "Allowed Output Formats": user_info.get("allowed_output_formats", "N/A"),
    }

    for key, value in details.items():
        list_item = xbmcgui.ListItem(label=f"{key}: {value}")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url="", listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def open_settings():
    """ Open the Kodi Plugin Settings """
    ADDON.openSettings()
    xbmc.executebuiltin("Container.Refresh")  # Refresh UI after login

def logout():
    """ Logout and Reset Credentials """
    ADDON.setSetting("server_url", "")
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
    elif mode == "account_info":
        show_account_info()
    elif mode == "settings":
        open_settings()
    elif mode == "logout":
        logout()

if __name__ == '__main__':
    router()
