import os
import sys
import xbmc
import xbmcaddon
import xbmcplugin
import xbmcgui
import xbmcvfs
import requests
from resources.lib.cache import CacheManager

# Add-on Info
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
CACHE = CacheManager()

# Get Username & Password from Settings
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")
M3U_URL = f"https://m3ufilter.media4u.top/get.php?username={USERNAME}&password={PASSWORD}&type=m3u_plus"

def main_menu():
    """Display the main menu based on login status."""
    xbmcplugin.setPluginCategory(int(sys.argv[1]), ADDON_NAME)

    if not USERNAME or not PASSWORD:
        add_directory_item("Login", "open_settings", is_folder=False)
    else:
        if CACHE.is_cache_expired():
            force_update()  # Update on startup if needed

        add_directory_item("Force Update", "force_update", is_folder=False)
        add_directory_item("Live TV Categories", "list_categories", is_folder=True)
        add_directory_item("Search", "search", is_folder=False)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def open_settings():
    """Open Addon Settings, wait for input, and restart addon if credentials are entered."""
    xbmc.executebuiltin(f"Addon.OpenSettings({ADDON_ID})")

    # Wait for settings dialog to close
    monitor = xbmc.Monitor()
    while xbmc.getCondVisibility("Window.IsVisible(10140)"):  # 10140 = Settings Window ID
        if monitor.waitForAbort(1):  
            return  # Exit if Kodi is shutting down

    # Refresh username/password after user input
    updated_username = ADDON.getSetting("username")
    updated_password = ADDON.getSetting("password")

    if updated_username and updated_password:
        force_update()  # Update cache after login
        xbmc.executebuiltin("Container.Refresh")  # Refresh UI
        xbmc.executebuiltin(f"RunAddon({ADDON_ID})")  # Restart addon

def force_update():
    """Trigger a forced update of M3U data and cache."""
    if not USERNAME or not PASSWORD:
        xbmcgui.Dialog().ok(ADDON_NAME, "No login details found. Please enter credentials first.")
        open_settings()
        return

    dialog = xbmcgui.DialogProgress()
    dialog.create("Updating Data", "Fetching latest channel list, please wait...")

    try:
        response = requests.get(M3U_URL, timeout=15)
        response.raise_for_status()
        m3u_data = response.text

        if not m3u_data.strip():
            xbmcgui.Dialog().ok(ADDON_NAME, "Server returned empty data. Try again later.")
            return

        parsed_data = parse_m3u(m3u_data)
        if parsed_data:
            CACHE.save_cache(parsed_data)
            xbmcgui.Dialog().ok(ADDON_NAME, "Update successful!")
        else:
            xbmcgui.Dialog().ok(ADDON_NAME, "Failed to parse data.")

    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok(ADDON_NAME, f"Failed to fetch data:\n{e}")
    finally:
        dialog.close()
        xbmc.executebuiltin("Container.Refresh")  # Refresh UI

def parse_m3u(m3u_data):
    """Convert M3U into structured categories & streams."""
    categories = {}
    lines = m3u_data.split("\n")

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

def list_categories():
    """List Live TV categories."""
    categories = CACHE.load_cache()

    if not categories:
        xbmcgui.Dialog().ok(ADDON_NAME, "No categories found. Try updating.")
        return

    for category in categories.keys():
        add_directory_item(category, "list_streams", is_folder=True, params={"category": category})

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def list_streams(category):
    """List streams within a selected category."""
    categories = CACHE.load_cache()

    if not categories or category not in categories:
        xbmcgui.Dialog().ok(ADDON_NAME, "No streams found in this category.")
        return

    streams = categories[category]

    for stream in streams:
        add_directory_item(stream["name"], "play_stream", is_folder=False, params={"url": stream["url"]}, stream_url=stream["url"])

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def play_stream(url):
    """Play the selected stream."""
    list_item = xbmcgui.ListItem(path=url)
    list_item.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, list_item)

def add_directory_item(name, action, is_folder=True, params={}, stream_url=None):
    """Helper function to add items to the Kodi directory."""
    url = f"{sys.argv[0]}?action={action}"
    for key, value in params.items():
        url += f"&{key}={value}"
    
    list_item = xbmcgui.ListItem(label=name)
    if stream_url:
        list_item.setProperty("IsPlayable", "true")
        list_item.setPath(stream_url)

    xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, list_item, isFolder=is_folder)

def router(param_string):
    """Route actions based on user selection."""
    params = dict(arg.split("=") for arg in param_string.split("&") if "=" in arg)
    action = params.get("action", "")

    if action == "force_update":
        force_update()
    elif action == "list_categories":
        list_categories()
    elif action == "list_streams":
        list_streams(params.get("category", ""))
    elif action == "play_stream":
        play_stream(params.get("url", ""))
    elif action == "open_settings":
        open_settings()
    else:
        main_menu()

if __name__ == "__main__":
    router(sys.argv[2][1:]) if len(sys.argv) > 2 else main_menu()
