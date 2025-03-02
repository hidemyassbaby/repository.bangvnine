import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
from resources.lib.xtream import XtreamAPI

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
BASE_URL = "plugin://" + ADDON_ID

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

def main_menu():
    settings = get_settings()
    if not settings:
        return

    url = settings['server']
    user = settings['username']
    passwd = settings['password']

    api = XtreamAPI(url, user, passwd)
    categories = api.get_live_categories()

    for category in categories:
        list_item = xbmcgui.ListItem(label=category['name'])
        xbmcplugin.addDirectoryItem(handle=xbmcplugin.getCurrentHandle(), url=BASE_URL, listitem=list_item, isFolder=True)

    xbmcplugin.endOfDirectory(xbmcplugin.getCurrentHandle())

if __name__ == '__main__':
    main_menu()
