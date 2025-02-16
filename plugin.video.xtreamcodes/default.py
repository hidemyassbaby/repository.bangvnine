import sys
import urllib.parse
import xbmc
import xbmcplugin
import xbmcgui
import xbmcaddon
from resources.lib.api import XtreamAPI

addon = xbmcaddon.Addon()
addon_handle = int(sys.argv[1])
base_url = sys.argv[0]

# Get user settings
server_url = addon.getSetting("server_url")
username = addon.getSetting("username")
password = addon.getSetting("password")

api = XtreamAPI(server_url, username, password)

def build_url(query):
    return f"{base_url}?{urllib.parse.urlencode(query)}"

def main_menu():
    xbmcplugin.setContent(addon_handle, 'videos')

    categories = [
        ("Live TV", {"mode": "live"}),
        ("Movies", {"mode": "vod"}),
        ("TV Shows", {"mode": "series"})
    ]
    
    for title, params in categories:
        url = build_url(params)
        li = xbmcgui.ListItem(title)
        li.setArt({"icon": "DefaultFolder.png"})
        xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)

if __name__ == '__main__':
    args = urllib.parse.parse_qs(sys.argv[2][1:])
    mode = args.get("mode", [None])[0]

    if mode is None:
        main_menu()
