import sys
import xbmc
import xbmcgui
import xbmcplugin
import urllib.parse
import xbmcaddon
import os
import time

from resources.lib.xtream_api import XtreamAPI

addon_handle = int(sys.argv[1])
addon = xbmcaddon.Addon()
api = XtreamAPI()

def check_login():
    """Ensures user has set credentials before using the addon."""
    username = addon.getSetting("username")
    password = addon.getSetting("password")
    if not username or not password:
        xbmcgui.Dialog().ok("Media4U TV", "Please enter your Username & Password in settings.")
        addon.openSettings()

def list_categories():
    """Lists Live TV categories instantly from cache."""
    check_login()

    categories = api.get_live_categories()
    
    if not categories:
        xbmcgui.Dialog().ok("Media4U TV", "No Live TV categories found!")
        return

    for category in categories:
        cat_id = category["category_id"]
        cat_name = category["category_name"]
        url = f"{sys.argv[0]}?action=list_streams&category_id={cat_id}"
        li = xbmcgui.ListItem(label=cat_name)
        xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)

def list_streams(category_id):
    """Lists streams in a selected category."""
    streams = api.get_live_streams(category_id)
    
    if not streams:
        xbmcgui.Dialog().ok("Media4U TV", "No streams found in this category.")
        return

    for stream in streams:
        stream_id = stream["stream_id"]
        stream_name = stream["name"]
        stream_url = f"http://m3ufilter.media4u.top/{stream_id}.m3u8"
        li = xbmcgui.ListItem(label=stream_name)
        li.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(handle=addon_handle, url=stream_url, listitem=li)

    xbmcplugin.endOfDirectory(addon_handle)
