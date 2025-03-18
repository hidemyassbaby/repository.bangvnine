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
    return {"username": username, "password": password} if username and password else None

def build_main_menu():
    """ Main Menu - Show Login if Not Logged In, Otherwise Show Live TV """
    settings = get_settings()

    if not settings:
        xbmcgui.Dialog().ok("Xtream Codes IPTV", "Please enter your username and password in settings.")
        open_settings()
        return

    api = XtreamAPI()
    if not api.test_connection():
        xbmcgui.Dialog().ok("Error", "Invalid credentials OR no Live TV categories found.")
        open_settings()
        return

    # Account Info
    url = f"{BASE_URL}?mode=account_info"
    list_item = xbmcgui.ListItem(label="👤 Account Info")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    # Live TV Section
    url = f"{BASE_URL}?mode=live"
    list_item = xbmcgui.ListItem(label="📺 Live TV")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    # Open Settings
    url = f"{BASE_URL}?mode=settings"
    list_item = xbmcgui.ListItem(label="⚙️ Settings")
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_live_categories():
    """ Display Dynamic Live TV Categories """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI()
    categories = api.get_live_categories()

    if not categories:
        xbmcgui.Dialog().ok("Error", "No Live TV categories found.")
        return

    for category in categories:
        url = f"{BASE_URL}?mode=live_streams&category_id={category['category_id']}"
        list_item = xbmcgui.ListItem(label=category["category_name"])
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=True)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_live_streams(category_id):
    """ Display Dynamic Live TV Streams """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI()
    streams = api.get_live_streams(category_id)

    if not streams:
        xbmcgui.Dialog().ok("Error", "No streams found in this category.")
        return

    for stream in streams:
        url = stream["play_url"]
        list_item = xbmcgui.ListItem(label=stream["title"])
        list_item.setArt({"icon": stream["stream_icon"], "thumb": stream["thumbnail"]})
        list_item.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def show_account_info():
    """ Display Account Information """
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI()
    url = f"{api.base_url}?username={api.username}&password={api.password}&action=user_info"
    response = api._send_request(url)

    if not response:
        xbmcgui.Dialog().ok("Error", "Failed to fetch account info.")
        return

    info = f"👤 **Username:** {response.get('username', 'N/A')}\n" \
           f"📅 **Expiry Date:** {response.get('exp_date', 'N/A')}\n" \
           f"🟢 **Active Connections:** {response.get('active_cons', 'N/A')}\n" \
           f"🔗 **Max Connections:** {response.get('max_connections', 'N/A')}\n"

    xbmcgui.Dialog().ok("📊 Account Info", info)

def open_settings():
    """ Open the Kodi Plugin Settings and refresh UI """
    ADDON.openSettings()
    xbmc.executebuiltin("Container.Refresh")

if __name__ == '__main__':
    params = get_params()
    mode = params.get("mode")

    if mode is None:
        build_main_menu()
    elif mode == "live":
        show_live_categories()
    elif mode == "live_streams":
        show_live_streams(params.get("category_id"))
    elif mode == "account_info":
        show_account_info()
    elif mode == "settings":
        open_settings()
