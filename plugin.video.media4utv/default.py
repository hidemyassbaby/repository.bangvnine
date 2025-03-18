import os
import sys
import json
import requests
import xbmc
import xbmcaddon
import xbmcplugin
import xbmcgui
import xbmcvfs
from urllib.parse import parse_qs

# Add-on Info
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_DATA_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
PAGE_LIMIT = 50  # Limit categories & streams per page

# Read Username & Password from settings.xml
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")

# M3U URL
M3U_URL = f"https://m3ufilter.media4u.top/get.php?username={USERNAME}&password={PASSWORD}&type=m3u_plus"
CACHE_FILE = os.path.join(ADDON_DATA_PATH, "m3u_cache.json")

# Ensure Addon Data Directory Exists
if not os.path.exists(ADDON_DATA_PATH):
    os.makedirs(ADDON_DATA_PATH)

# **Fetch & Cache M3U Data**
def fetch_m3u():
    """Fetch M3U and parse it into a structured format."""
    xbmc.log("[Media4u TV] Fetching M3U...", xbmc.LOGINFO)

    try:
        response = requests.get(M3U_URL, timeout=15)
        response.raise_for_status()
        m3u_data = response.text
    except requests.exceptions.RequestException as e:
        xbmc.log(f"[Media4u TV] M3U Fetch Failed: {e}", xbmc.LOGERROR)
        return None

    parsed_data = parse_m3u(m3u_data)

    if parsed_data:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=4)
        return parsed_data
    else:
        xbmc.log("[Media4u TV] M3U Parse Failed", xbmc.LOGERROR)
        return None

# **Parse M3U into Categories & Streams**
def parse_m3u(m3u_data):
    """Convert M3U into structured categories & streams."""
    categories = {}
    lines = m3u_data.split("\n")
    current_category = "Uncategorized"

    for i, line in enumerate(lines):
        if line.startswith("#EXTINF"):
            parts = line.split(" ")
            name = line.split(",")[-1].strip()
            category = "Uncategorized"
            logo = ""

            # Extract Metadata
            for part in parts:
                if "group-title" in part:
                    category = part.split("=")[-1].replace('"', '').strip()
                if "tvg-logo" in part:
                    logo = part.split("=")[-1].replace('"', '').strip()

            # Get Stream URL
            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                if url.startswith("http"):
                    if category not in categories:
                        categories[category] = []
                    categories[category].append({"name": name, "url": url, "logo": logo})

    return categories

# **Load Cached M3U**
def load_cached_m3u():
    """Load M3U data from cache if available."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# **Display Main Menu**
def main_menu():
    xbmcplugin.setPluginCategory(int(sys.argv[1]), ADDON_NAME)
    
    add_directory_item("Live TV", "list_categories", is_folder=True)
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# **List Categories (FIXED: Ensures It Opens)**
def list_categories(page=1):
    """Show available categories with pagination."""
    categories = load_cached_m3u()

    if not categories:
        xbmc.log("[Media4u TV] No cached M3U data found. Fetching new data...", xbmc.LOGWARNING)
        categories = fetch_m3u()

    if not categories:
        xbmcgui.Dialog().ok(ADDON_NAME, "No categories found. Try again later.")
        return

    category_list = sorted(categories.keys())  # Sort category names
    start_index = (page - 1) * PAGE_LIMIT
    end_index = start_index + PAGE_LIMIT
    paged_categories = category_list[start_index:end_index]

    for category in paged_categories:
        add_directory_item(category, f"list_streams&category={category}", is_folder=True)

    if end_index < len(category_list):
        add_directory_item("Next Page", f"list_categories&page={page + 1}", is_folder=True)
    if page > 1:
        add_directory_item("Previous Page", f"list_categories&page={page - 1}", is_folder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# **List Streams (FIXED: Ensures Streams Load)**
def list_streams(category, page=1):
    """Show streams in a category with pagination."""
    categories = load_cached_m3u()

    if not categories or category not in categories:
        xbmc.log(f"[Media4u TV] No streams found for {category}, retrying...", xbmc.LOGWARNING)
        
        for attempt in range(1, 6):
            xbmc.log(f"[Media4u TV] Attempt {attempt}/5: Fetching M3U again", xbmc.LOGWARNING)
            categories = fetch_m3u()
            if categories and category in categories:
                break
            xbmc.sleep(3000)  # Wait 3 seconds before retrying

        if not categories or category not in categories:
            xbmcgui.Dialog().ok(ADDON_NAME, f"No streams found in {category}.\nTry again later.")
            return

    streams = categories[category]
    start_index = (page - 1) * PAGE_LIMIT
    end_index = start_index + PAGE_LIMIT
    paged_streams = streams[start_index:end_index]

    for stream in paged_streams:
        add_directory_item(stream["name"], f"play_stream&url={stream['url']}&logo={stream['logo']}", is_folder=False, logo=stream["logo"])

    if end_index < len(streams):
        add_directory_item("Next Page", f"list_streams&category={category}&page={page + 1}", is_folder=True)
    if page > 1:
        add_directory_item("Previous Page", f"list_streams&category={category}&page={page - 1}", is_folder=True)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# **Play Stream (FIXED: Click to Play Works)**
def play_stream(url, logo=""):
    """Play selected stream when clicked."""
    list_item = xbmcgui.ListItem(path=url)
    list_item.setInfo("video", {"title": "Live Stream"})
    if logo:
        list_item.setArt({"icon": logo, "thumb": logo})
    xbmc.Player().play(url, list_item)  # Ensures clicking works like "Play from Here"

# **Add Directory Item**
def add_directory_item(name, action, is_folder=True, logo=""):
    """Add an item to Kodi menu."""
    url = f"{sys.argv[0]}?action={action}"
    list_item = xbmcgui.ListItem(label=name)
    list_item.setInfo("video", {"title": name})
    if logo:
        list_item.setArt({"icon": logo, "thumb": logo})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, list_item, isFolder=is_folder)

# **Route Actions**
def router(param_string):
    """Handle plugin actions."""
    params = parse_qs(param_string)
    action = params.get("action", [""])[0]

    if action == "list_categories":
        page = int(params.get("page", [1])[0])
        list_categories(page)
    elif action == "list_streams":
        category = params["category"][0]
        page = int(params.get("page", [1])[0])
        list_streams(category, page)
    elif action == "play_stream":
        play_stream(params["url"][0], params.get("logo", [""])[0])
    else:
        main_menu()

# **Run Plugin**
if __name__ == "__main__":
    router(sys.argv[2][1:]) if len(sys.argv) > 2 else main_menu()
