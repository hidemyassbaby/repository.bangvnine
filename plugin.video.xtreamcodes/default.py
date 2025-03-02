import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
from resources.lib.xtream import XtreamAPI

ADDON = xbmcaddon.Addon()
BASE_URL = "plugin://" + ADDON.getAddonInfo('id')

def get_settings():
    server = ADDON.getSetting("server_url")
    username = ADDON.getSetting("username")
    password = ADDON.getSetting("password")

    if not server or not username or not password:
        prompt_settings()
        return None
    return {"server": server, "username": username, "password": password}

def prompt_settings():
    dialog = xbmcgui.Dialog()
    server = dialog.input("Enter Server URL")
    username = dialog.input("Enter Username")
    password = dialog.input("Enter Password", option=xbmcgui.ALPHANUM_HIDE_INPUT)

    if server and username and password:
        ADDON.setSetting("server_url", server)
        ADDON.setSetting("username", username)
        ADDON.setSetting("password", password)

def build_menu():
    settings = get_settings()
    if not settings:
        return

    api = XtreamAPI(settings["server"], settings["username"], settings["password"])
    
    categories = [
        ("Live TV", "live"),
        ("Movies (VOD)", "movies"),
        ("TV Shows", "series"),
        ("EPG", "epg")
    ]

    for name, mode in categories:
        url = f"{BASE_URL}?mode={mode}"
        list_item = xbmcgui.ListItem(label=name)
        xbmcplugin.addDirectoryItem(handle=xbmcplugin.getCurrentHandle(), url=url, listitem=list_item, isFolder=True)

    xbmcplugin.endOfDirectory(xbmcplugin.getCurrentHandle())

if __name__ == '__main__':
    build_menu()
