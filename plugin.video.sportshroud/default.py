# default.py
import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import json
import requests

addon = xbmcaddon.Addon()
handle = int(sys.argv[1])

# Parse plugin parameters
params = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
menu_url = params.get("url")
if not menu_url:
    # Default to main menu
    menu_url = "https://raw.githubusercontent.com/hidemyassbaby/SportShroud/refs/heads/main/Main%20Menu/SportShroudMenu.json"

# Function to build a Kodi URL
def build_url(query):
    return sys.argv[0] + '?' + urllib.parse.urlencode(query)

# Function to open a remote JSON URL and return parsed data
def get_json(url):
    try:
        xbmc.log(f"[SportShroud] Fetching JSON from: {url}", level=xbmc.LOGINFO)
        response = requests.get(url)
        return response.json()
    except Exception as e:
        xbmc.log(f"[SportShroud] Failed to fetch JSON from {url}: {e}", level=xbmc.LOGERROR)
        return []

# Log which URL is being opened
xbmc.log(f"[SportShroud] Loading menu from: {menu_url}", level=xbmc.LOGINFO)

# Load the menu
menu = get_json(menu_url)

for item in menu:
    li = xbmcgui.ListItem(label=item.get("name", "Unknown"))
    info = li.getVideoInfoTag()
    info.setTitle(item.get("name", ""))
    info.setPlot(item.get("plot", ""))
    if item.get("thumb"):
        li.setArt({"thumb": item["thumb"], "icon": item["thumb"], "poster": item["thumb"]})
    url = item.get("url", "")
    dir_url = build_url({"name": item.get("name"), "url": url})
    xbmcplugin.addDirectoryItem(handle, dir_url, li, isFolder=True)

xbmcplugin.endOfDirectory(handle)
