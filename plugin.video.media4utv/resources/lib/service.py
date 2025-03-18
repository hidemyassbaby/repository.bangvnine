import xbmc
import xbmcaddon
import xbmcgui
import time
import requests
import os
from cache import CacheManager  # ✅ Fix import for the correct path

# Add-on Information
ADDON = xbmcaddon.Addon()
USERNAME = ADDON.getSetting("username")
PASSWORD = ADDON.getSetting("password")
M3U_URL = f"https://m3ufilter.media4u.top/get.php?username={USERNAME}&password={PASSWORD}&type=m3u_plus"

# Initialize Cache
CACHE = CacheManager()

def fetch_m3u():
    """Fetch M3U data and cache it, with retries."""
    retries = 5
    for attempt in range(retries):
        try:
            xbmc.log(f"[Media4u TV] Fetching M3U (Attempt {attempt+1}/{retries})", xbmc.LOGINFO)
            response = requests.get(M3U_URL, timeout=15)
            response.raise_for_status()
            m3u_data = response.text
            parsed_data = parse_m3u(m3u_data)

            if parsed_data:
                CACHE.save_cache(parsed_data)
                xbmc.log("[Media4u TV] ✅ M3U Data Cached Successfully", xbmc.LOGINFO)
            return
        except requests.exceptions.RequestException as e:
            xbmc.log(f"[Media4u TV] ❌ M3U Fetch Failed: {e}", xbmc.LOGERROR)
            time.sleep(5)  # Wait before retrying

    xbmc.log("[Media4u TV] ❌ API request failed after retries!", xbmc.LOGERROR)

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

# Background process to refresh cache every hour
while not xbmc.Monitor().abortRequested():
    fetch_m3u()
    xbmc.sleep(3600000)  # Refresh every 1 hour
