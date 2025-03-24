import sys
import os
import time
import base64
import json
import hashlib
import re
import urllib.parse
import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
from xbmcvfs import translatePath
from collections import defaultdict

# ------------ CONFIG & PATHS ------------
addon = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
CACHE_PATH = translatePath(addon.getAddonInfo('profile')).rstrip('/')
if not os.path.exists(CACHE_PATH):
    os.makedirs(CACHE_PATH)

FAVOURITES_FILE = os.path.join(CACHE_PATH, "favourites.json")
PIN_FILE = os.path.join(CACHE_PATH, "pin.lock")
SETUP_FILE = os.path.join(CACHE_PATH, ".setupdone")
DEV_MODE_FILE = os.path.join(CACHE_PATH, ".devmode")

M3U_URL_OBFUSCATED = "aHR0cHM6Ly9pcHR2LW9yZy5naXRodWIuaW8vaXB0di9pbmRleC5jYXRlZ29yeS5tM3U="
COUNTRY_M3U_URL = "https://iptv-org.github.io/iptv/index.country.m3u"

M3U_CACHE = os.path.join(CACHE_PATH, "iptv_cache.m3u")
COUNTRY_CACHE = os.path.join(CACHE_PATH, "iptv_country_cache.m3u")

CACHE_EXPIRY = 3600  # 1 hour
ADULT_KEYWORDS = ["xxx", "porn", "18+", "erotic", "adult"]

# ------------ HELPERS ------------
def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def save_pin(pin):
    hashed = hashlib.sha256(pin.encode()).hexdigest()
    with open(PIN_FILE, 'w') as f:
        f.write(hashed)

def verify_pin(pin):
    if not os.path.exists(PIN_FILE):
        return False
    hashed = hashlib.sha256(pin.encode()).hexdigest()
    with open(PIN_FILE, 'r') as f:
        return f.read() == hashed

def prompt_for_pin():
    pin = xbmcgui.Dialog().input("Enter PIN", type=xbmcgui.INPUT_NUMERIC)
    return pin if verify_pin(pin) else None

def is_developer_mode():
    return os.path.exists(DEV_MODE_FILE)

def toggle_developer_mode():
    if is_developer_mode():
        os.remove(DEV_MODE_FILE)
        xbmcgui.Dialog().notification("Developer Mode", "Disabled", xbmcgui.NOTIFICATION_INFO)
    else:
        password = xbmcgui.Dialog().input("Enter Developer Password", type=xbmcgui.INPUT_ALPHANUM)
        if password == "bangdev":
            with open(DEV_MODE_FILE, 'w') as f:
                f.write("enabled")
            xbmcgui.Dialog().notification("Developer Mode", "Enabled", xbmcgui.NOTIFICATION_INFO)
        else:
            xbmcgui.Dialog().ok("Access Denied", "Incorrect password.")
    xbmc.executebuiltin("Container.Refresh")

# ------------ M3U FETCHING ------------
def fetch_file(url, cache_file, force=False):
    if os.path.exists(cache_file) and not force:
        if time.time() - os.path.getmtime(cache_file) < CACHE_EXPIRY:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(r.text)
        return r.text
    except Exception as e:
        xbmcgui.Dialog().notification("Fetch Error", str(e), xbmcgui.NOTIFICATION_ERROR)
        return ""

def fetch_main_m3u(force=False):
    return fetch_file(base64.b64decode(M3U_URL_OBFUSCATED).decode(), M3U_CACHE, force)

def fetch_country_m3u(force=False):
    return fetch_file(COUNTRY_M3U_URL, COUNTRY_CACHE, force)

# ------------ M3U PARSING ------------
def parse_m3u(data):
    entries = []
    lines = data.splitlines()
    for i in range(len(lines)):
        line = lines[i]
        if line.startswith("#EXTINF:"):
            logo = re.search(r'tvg-logo="([^"]*)"', line)
            group = re.search(r'group-title="([^"]*)"', line)
            name = re.search(r',(.+)', line)
            logo = logo.group(1) if logo else ""
            group = group.group(1) if group else "Other"
            name = name.group(1).strip() if name else "Unknown"
            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                if url.startswith("http"):
                    entries.append((logo, group, name, url))
    return entries

# ------------ MAIN MENU & SUBMENUS ------------
def main_menu():
    run_first_time_setup()
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'live_tv'}), xbmcgui.ListItem(label='Live TV'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'favourites'}), xbmcgui.ListItem(label='Favourites'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'search'}), xbmcgui.ListItem(label='Search'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'settings'}), xbmcgui.ListItem(label='Settings'), True)
    xbmcplugin.endOfDirectory(HANDLE)

def show_live_tv_menu():
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'categories'}), xbmcgui.ListItem(label='Categories'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'countries'}), xbmcgui.ListItem(label='Countries'), True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_groups(raw_data, target_mode):
    groups = defaultdict(list)
    for logo, group, name, url in parse_m3u(raw_data):
        groups[group].append((logo, name, url))
    for group in sorted(groups):
        if any(word in group.lower() for word in ADULT_KEYWORDS):
            if not os.path.exists(PIN_FILE) or not verify_pin(prompt_for_pin() or ""):
                continue
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': target_mode, 'group': group}), xbmcgui.ListItem(label=group), True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_group_items(raw_data, target_group):
    for logo, group, name, url in parse_m3u(raw_data):
        if group != target_group:
            continue
        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': logo})
        li.setPath(url)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

# ------------ CACHE MANAGEMENT ------------
def cache_expired(path):
    return not os.path.exists(path) or (time.time() - os.path.getmtime(path) > CACHE_EXPIRY)

def run_first_time_setup():
    if cache_expired(M3U_CACHE) or cache_expired(COUNTRY_CACHE):
        fetch_main_m3u(force=True)
        fetch_country_m3u(force=True)
    if not os.path.exists(SETUP_FILE):
        open(SETUP_FILE, 'w').close()

# ------------ SEARCH ------------
def search_channels():
    query = xbmcgui.Dialog().input("Search Channels")
    if not query:
        return
    data = fetch_main_m3u()
    results = [entry for entry in parse_m3u(data) if query.lower() in entry[2].lower()]
    for logo, group, name, url in results:
        li = xbmcgui.ListItem(label=f"{name} [{group}]")
        li.setArt({'thumb': logo})
        li.setPath(url)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

# ------------ SETTINGS ------------
def show_settings():
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'update'}), xbmcgui.ListItem(label='Update Channels Now'), False)
    if not os.path.exists(PIN_FILE):
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'set_pin'}), xbmcgui.ListItem(label='Set PIN'), False)
    else:
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'change_pin'}), xbmcgui.ListItem(label='Change PIN'), False)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'reset_pin'}), xbmcgui.ListItem(label='Reset PIN'), False)

    dev_label = f"Developer Mode: {'ON' if is_developer_mode() else 'OFF'}"
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'toggle_dev'}), xbmcgui.ListItem(label=dev_label), False)
    xbmcplugin.endOfDirectory(HANDLE)

def set_pin():
    pin = xbmcgui.Dialog().input("Set a 4-digit PIN", type=xbmcgui.INPUT_NUMERIC)
    if pin and pin.isdigit() and len(pin) == 4:
        save_pin(pin)
        xbmcgui.Dialog().notification("PIN Set", "PIN saved.", xbmcgui.NOTIFICATION_INFO)
    else:
        xbmcgui.Dialog().ok("Invalid PIN", "PIN must be 4 digits.")

def change_pin():
    current = xbmcgui.Dialog().input("Enter current PIN", type=xbmcgui.INPUT_NUMERIC)
    if not verify_pin(current):
        xbmcgui.Dialog().ok("Incorrect PIN", "PIN incorrect.")
        return
    set_pin()

def reset_pin():
    master = xbmcgui.Dialog().input("Enter master password", type=xbmcgui.INPUT_ALPHANUM)
    if master == 'bangunlock':
        if os.path.exists(PIN_FILE):
            os.remove(PIN_FILE)
        set_pin()
    else:
        xbmcgui.Dialog().ok("Incorrect Password", "Reset failed.")

# ------------ ROUTER ------------
def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    mode = params.get('mode')

    if mode == 'live_tv':
        show_live_tv_menu()
    elif mode == 'categories':
        list_groups(fetch_main_m3u(), 'category_items')
    elif mode == 'countries':
        list_groups(fetch_country_m3u(), 'country_items')
    elif mode == 'category_items':
        list_group_items(fetch_main_m3u(), params.get('group'))
    elif mode == 'country_items':
        list_group_items(fetch_country_m3u(), params.get('group'))
    elif mode == 'search':
        search_channels()
    elif mode == 'settings':
        show_settings()
    elif mode == 'set_pin':
        set_pin()
    elif mode == 'change_pin':
        change_pin()
    elif mode == 'reset_pin':
        reset_pin()
    elif mode == 'toggle_dev':
        toggle_developer_mode()
    elif mode == 'update':
        fetch_main_m3u(force=True)
        fetch_country_m3u(force=True)
        xbmcgui.Dialog().notification("IPTV-Org", "Playlists updated.", xbmcgui.NOTIFICATION_INFO)
    else:
        main_menu()

# ------------ MAIN ENTRY ------------
if __name__ == '__main__':
    router(sys.argv[2][1:])
