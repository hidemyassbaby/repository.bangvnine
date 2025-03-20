import xbmcaddon
import xbmcplugin
import xbmcgui
import sys
import urllib.parse
import requests
import xml.etree.ElementTree as ET

# Kodi addon settings
ADDON = xbmcaddon.Addon()
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")
BASE_URL = "https://m3ufilter.media4u.top"

# API Endpoints
CATEGORY_URL = f"{BASE_URL}/player_api.php?username={USERNAME}&password={PASSWORD}&action=get_live_categories"
M3U_URL = f"{BASE_URL}/get.php?username={USERNAME}&password={PASSWORD}&type=m3u_plus"

# Get handle
HANDLE = int(sys.argv[1])


def get_categories():
    """Fetch Live TV categories from API."""
    try:
        response = requests.get(CATEGORY_URL)
        return response.json() if response.status_code == 200 else []
    except:
        return []


def get_m3u():
    """Fetch and parse M3U playlist."""
    try:
        response = requests.get(M3U_URL)
        return response.text if response.status_code == 200 else ""
    except:
        return ""


def parse_m3u(m3u_data):
    """Parse M3U file into structured channel data."""
    channels = []
    lines = m3u_data.splitlines()
    
    for i in range(len(lines)):
        if lines[i].startswith("#EXTINF"):
            details = lines[i]
            url = lines[i + 1] if i + 1 < len(lines) else ""
            name = details.split(",")[-1]
            group = "Unknown"
            
            if "group-title" in details:
                group = details.split("group-title=\"")[1].split("\"")[0]
            
            channels.append({"name": name, "url": url, "group": group})
    
    return channels


def build_category_list():
    """Display categories in Kodi."""
    categories = get_categories()
    for category in categories:
        url = f"{sys.argv[0]}?action=list&category={urllib.parse.quote(category['category_name'])}"
        li = xbmcgui.ListItem(label=category['category_name'])
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)


def build_channel_list(category):
    """Display channels in the selected category."""
    m3u_data = get_m3u()
    channels = parse_m3u(m3u_data)
    
    for channel in channels:
        if channel['group'].lower() == category.lower():
            li = xbmcgui.ListItem(label=channel['name'])
            li.setInfo('video', {"Title": channel['name']})
            li.setProperty('IsPlayable', 'true')
            xbmcplugin.addDirectoryItem(HANDLE, channel['url'], li, False)
    
    xbmcplugin.endOfDirectory(HANDLE)


def router():
    """Router to handle navigation."""
    params = urllib.parse.parse_qs(sys.argv[2][1:])
    action = params.get('action', [None])[0]
    category = params.get('category', [None])[0]
    
    if action == 'list' and category:
        build_channel_list(category)
    else:
        build_category_list()


if __name__ == "__main__":
    router()
