# default.py
import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import json
import requests

addon = xbmcaddon.Addon()
handle = int(sys.argv[1])

# Always load the main SportShroud menu
menu_url = "https://raw.githubusercontent.com/hidemyassbaby/SportShroud/refs/heads/main/Main%20Menu/SportShroudMenu.json"

# Function to build a Kodi URL
def build_url(query):
    return sys.argv[0] + '?' + urllib.parse.urlencode(query)

# Function to open a remote JSON URL and return parsed data
def get_json(url):
    try:
        response = requests.get(url)
        return response.json()
    except:
        return []

# Load the main menu
menu = get_json(menu_url)

for item in menu:
    li = xbmcgui.ListItem(label=item.get("name", "Unknown"))
    info = li.getVideoInfoTag()
    info.setTitle(item.get("name", ""))
    info.setPlot(item.get("plot", ""))
    if item.get("thumb"):
        li.setArt({"thumb": item["thumb"], "icon": item["thumb"], "poster": item["thumb"]})
    url = item.get("url", "")
    if url.endswith(".json"):
        # It's a final stream list
        streams = get_json(url)
        if isinstance(streams, list):
            for stream in streams:
                title = stream.get("name", "Stream")
                stream_li = xbmcgui.ListItem(label=title)
                stream_li.setProperty("IsPlayable", "true")
                stream_li.setPath(stream.get("url"))
                xbmcplugin.addDirectoryItem(handle, stream.get("url"), stream_li, isFolder=False)
            xbmcplugin.endOfDirectory(handle)
            sys.exit()
    else:
        dir_url = build_url({"name": item.get("name"), "url": url})
        xbmcplugin.addDirectoryItem(handle, dir_url, li, isFolder=True)

xbmcplugin.endOfDirectory(handle)
