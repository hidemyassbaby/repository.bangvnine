import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import requests
import re
import os
import time
import hashlib
import json
import base64
from xbmcvfs import translatePath
from collections import defaultdict

# Helper to build plugin URLs
def build_url(query):
    return sys.argv[0] + '?' + urllib.parse.urlencode(query)

addon = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

M3U_URL_OBFUSCATED = "aHR0cHM6Ly9pcHR2LW9yZy5naXRodWIuaW8vaXB0di9pbmRleC5jYXRlZ29yeS5tM3U="
CACHE_EXPIRY = 3600
CACHE_PATH = translatePath(addon.getAddonInfo('profile')).rstrip('/')
if not os.path.exists(CACHE_PATH):
    os.makedirs(CACHE_PATH)

FAVOURITES_FILE = os.path.join(CACHE_PATH, "favourites.json")
PIN_FILE = os.path.join(CACHE_PATH, "pin.lock")
SETUP_FILE = os.path.join(CACHE_PATH, ".setupdone")
DEV_MODE_FILE = os.path.join(CACHE_PATH, ".devmode")

HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; Android 9) IPTV",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Connection": "Keep-Alive"
}

ADULT_KEYWORDS = ["xxx", "adult", "18+", "porn", "erotic"]

# ------------------ PIN & Developer Mode ------------------
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
        xbmcgui.Dialog().notification("Developer Mode", "Disabled", xbmcgui.NOTIFICATION_INFO, 3000)
        xbmc.executebuiltin("Container.Refresh")  # Auto-refresh
    else:
        password = xbmcgui.Dialog().input("Enter Developer Password", type=xbmcgui.INPUT_ALPHANUM)
        if password == 'bangdev':  # bangdev
            with open(DEV_MODE_FILE, 'w') as f:
                f.write("enabled")
            xbmcgui.Dialog().notification("Developer Mode", "Enabled", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmc.executebuiltin("Container.Refresh")
        else:
            xbmcgui.Dialog().ok("Access Denied", "Incorrect password.")

# ------------------ Settings Menu ------------------
def show_settings():
    last_updated_path = os.path.join(CACHE_PATH, 'last_updated.txt')
    last_updated = 'Never'
    if os.path.exists(last_updated_path):
        with open(last_updated_path, 'r') as f:
            last_updated = f.read().strip()

    xbmcplugin.addDirectoryItem(HANDLE, '', xbmcgui.ListItem(label=f'[I]Last Updated: {last_updated}[/I]'), False)
    dev_status = "ON" if is_developer_mode() else "OFF"
    dev_status_label = f"Developer Mode: [B]{dev_status}[/B]"
    xbmc.log(f"[IPTV-Org] Developer Mode Status: {dev_status}", xbmc.LOGINFO)
    xbmcplugin.setPluginCategory(HANDLE, 'IPTV-Org Settings')

    li = xbmcgui.ListItem(label='Update TV')
    li.setInfo('video', {'title': 'Refresh live TV channels now'})
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'update_tv'}), li, False)

    if not os.path.exists(PIN_FILE):
        li_set = xbmcgui.ListItem(label='Set Adult Content PIN')
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'set_pin'}), li_set, False)
    else:
        li_change = xbmcgui.ListItem(label='Change PIN (requires current PIN)')
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'change_pin'}), li_change, False)

        li_reset = xbmcgui.ListItem(label='Reset PIN (requires master password)')
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'reset_pin'}), li_reset, False)

    dev_status = "ON" if is_developer_mode() else "OFF"
    dev_color = "[COLOR=green]ON[/COLOR]" if dev_status == "ON" else "[COLOR=red]OFF[/COLOR]"
    li_dev = xbmcgui.ListItem(label=f'Developer Mode ({dev_color})', offscreen=True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'dev_toggle'}), li_dev, False)

    changelog = os.path.join(translatePath(addon.getAddonInfo('path')), 'changelog.txt')
    if os.path.exists(changelog):
        li2 = xbmcgui.ListItem(label='View Changelog')
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'view_changelog'}), li2, False)

    li3 = xbmcgui.ListItem(label='Open Settings')
    li3.setProperty('Addon.OpenSettings', addon.getAddonInfo('id'))
    xbmcplugin.addDirectoryItem(HANDLE, f'ActivateWindow(10007,addons://user/{addon.getAddonInfo("id")}/)', li3, False)

    xbmcplugin.endOfDirectory(HANDLE)

# ------------------ Settings Actions ------------------
def set_pin_from_settings():
    pin = xbmcgui.Dialog().input("Set a 4-digit PIN", type=xbmcgui.INPUT_NUMERIC)
    if pin and pin.isdigit() and len(pin) == 4:
        save_pin(pin)
        xbmcgui.Dialog().notification("PIN Set", "PIN saved.", xbmcgui.NOTIFICATION_INFO, 3000)
    else:
        xbmcgui.Dialog().ok("Invalid PIN", "PIN must be exactly 4 digits.")

def change_pin():
    if not os.path.exists(PIN_FILE):
        xbmcgui.Dialog().ok("PIN Not Set", "No PIN is currently set.")
        return
    current = xbmcgui.Dialog().input("Enter current PIN", type=xbmcgui.INPUT_NUMERIC)
    if not verify_pin(current):
        xbmcgui.Dialog().ok("Incorrect PIN", "The PIN you entered is incorrect.")
        return
    new_pin = xbmcgui.Dialog().input("Enter new PIN", type=xbmcgui.INPUT_NUMERIC)
    if new_pin and new_pin.isdigit() and len(new_pin) == 4:
        save_pin(new_pin)
        xbmcgui.Dialog().notification("PIN Changed", "PIN has been updated.", xbmcgui.NOTIFICATION_INFO, 3000)
    else:
        xbmcgui.Dialog().ok("Invalid PIN", "PIN must be exactly 4 digits.")

def reset_pin():
    master = xbmcgui.Dialog().input("Enter master password", type=xbmcgui.INPUT_ALPHANUM)
    if master == 'bangunlock':  # bangunlock  # Password hidden
        os.remove(PIN_FILE)
        new_pin = xbmcgui.Dialog().input("Set new PIN", type=xbmcgui.INPUT_NUMERIC)
        if new_pin and new_pin.isdigit() and len(new_pin) == 4:
            save_pin(new_pin)
            xbmcgui.Dialog().notification("PIN Reset", "PIN has been reset and saved.", xbmcgui.NOTIFICATION_INFO, 3000)
        else:
            xbmcgui.Dialog().ok("Invalid PIN", "PIN must be exactly 4 digits.")
    else:
        xbmcgui.Dialog().ok("Incorrect Password", "The master password you entered is invalid.")

# ------------------ M3U Parsing & Display ------------------
def parse_m3u(data):
    pattern = re.compile(r'#EXTINF:-1.*?tvg-logo="(.*?)".*?group-title="(.*?)".*?,(.*?)\n(.*?)\n', re.DOTALL)
    return pattern.findall(data)

def list_m3u_group_category():
    raw_data = fetch_m3u()
    groups = defaultdict(list)
    for logo, group, name, url in parse_m3u(raw_data):
        groups[group].append((logo, name, url))

    for group in sorted(groups):
        if any(word in group.lower() for word in ADULT_KEYWORDS):
            if not is_developer_mode():
                if not os.path.exists(PIN_FILE):
                    xbmcgui.Dialog().notification("Restricted", "Set a PIN in Settings to view adult content.", xbmcgui.NOTIFICATION_WARNING, 3000)
                    continue
                if not verify_pin(prompt_for_pin() or ""):
                    xbmcgui.Dialog().notification("Access Denied", "Incorrect PIN.", xbmcgui.NOTIFICATION_ERROR, 3000)
                    continue

        li = xbmcgui.ListItem(label=group)
        url = build_url({'mode': 'm3u_group_items', 'group': group})
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_m3u_group_items(group):
    raw_data = fetch_m3u()
    favourites = []
    if os.path.exists(FAVOURITES_FILE):
        with open(FAVOURITES_FILE, 'r') as f:
            favourites = json.load(f)
    for logo, grp, name, url in parse_m3u(raw_data):
        if grp != group:
            continue
        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': logo})
        li.setInfo('video', {'title': name})
        li.setPath(url)

        is_fav = any(f['url'] == url for f in favourites)
        context = []
        if is_fav:
            context.append(("Remove from IPTV-Org Favourites", f"RunPlugin({build_url({'mode': 'remove_favourite', 'name': name, 'url': url, 'logo': logo})})"))
        else:
            context.append(("Add to IPTV-Org Favourites", f"RunPlugin({build_url({'mode': 'add_favourite', 'name': name, 'url': url, 'logo': logo})})"))
        li.addContextMenuItems(context, replaceItems=True)

        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def list_favourites():
    if not os.path.exists(FAVOURITES_FILE):
        xbmcgui.Dialog().notification("Favourites", "No favourites found.", xbmcgui.NOTIFICATION_INFO, 3000)
        xbmcplugin.endOfDirectory(HANDLE)
        return
    with open(FAVOURITES_FILE, 'r') as f:
        favs = json.load(f)
    for fav in favs:
        li = xbmcgui.ListItem(label=fav['name'])
        li.setArt({'thumb': fav.get('logo', '')})
        li.setInfo('video', {'title': fav['name']})
        li.setPath(fav['url'])

        # Add context menu item to remove favourite
        context = [
            ("Remove from IPTV-Org Favourites", f"RunPlugin({build_url({'mode': 'remove_favourite', 'url': fav['url']})})")
        ]
        li.addContextMenuItems(context, replaceItems=True)

        xbmcplugin.addDirectoryItem(HANDLE, fav['url'], li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def search():
    query = xbmcgui.Dialog().input("Search Channels")
    if not query:
        return
    raw_data = fetch_m3u()
    results = [entry for entry in parse_m3u(raw_data) if query.lower() in entry[2].lower()]
    if not results:
        xbmcgui.Dialog().notification("Search", "No results found.", xbmcgui.NOTIFICATION_INFO, 3000)
    for logo, group, name, url in results:
        li = xbmcgui.ListItem(label=f"{name} [{group}]")
        li.setArt({'thumb': logo})
        li.setInfo('video', {'title': name})
        li.setPath(url)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

# ------------------ Route Additions ------------------
# ------------------ Main Menu ------------------
def run_first_time_setup():
    if not os.path.exists(SETUP_FILE):
        xbmcgui.Dialog().ok("Welcome", "Welcome to IPTV-Org TV Addon")
        if xbmcgui.Dialog().yesno("Setup", "Would you like to set a PIN for adult channels?"):
            while True:
                pin = xbmcgui.Dialog().input("Set a 4-digit PIN", type=xbmcgui.INPUT_NUMERIC)
                if not pin:
                    xbmcgui.Dialog().notification("PIN Setup", "PIN not set. Adult content will be hidden.", xbmcgui.NOTIFICATION_INFO, 3000)
                    break
                elif len(pin) == 4 and pin.isdigit():
                    save_pin(pin)
                    xbmcgui.Dialog().notification("PIN Set", "PIN successfully saved.", xbmcgui.NOTIFICATION_INFO, 3000)
                    break
                else:
                    xbmcgui.Dialog().ok("Invalid PIN", "PIN must be exactly 4 digits.")
        fetch_m3u(force_refresh=True)
        xbmcgui.Dialog().notification("IPTV-Org", "Channels updated.", xbmcgui.NOTIFICATION_INFO, 3000)
        open(SETUP_FILE, 'w').close()

def main_menu():
    run_first_time_setup()
    if is_developer_mode():
        dev_li = xbmcgui.ListItem(label='[B]Developer Mode[/B] [COLOR=green]ON[/COLOR]')
        xbmcplugin.addDirectoryItem(HANDLE, '', dev_li, False)

    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'favourites'}), xbmcgui.ListItem(label='Favourites'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'live_categories'}), xbmcgui.ListItem(label='Live TV'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'search'}), xbmcgui.ListItem(label='Search'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'settings'}), xbmcgui.ListItem(label='Settings'), True)
    xbmcplugin.endOfDirectory(HANDLE)

def fetch_m3u(force_refresh=False):
    url = base64.b64decode(M3U_URL_OBFUSCATED).decode('utf-8')
    cache_file = os.path.join(CACHE_PATH, "iptv_cache.m3u")
    if os.path.exists(cache_file) and not force_refresh:
        mtime = os.path.getmtime(cache_file)
        if time.time() - mtime < CACHE_EXPIRY:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()

    dialog = xbmcgui.DialogProgress()
    dialog.create("IPTV-Org", "Updating Channels...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.text
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(content)
        dialog.close()
        with open(os.path.join(CACHE_PATH, 'last_updated.txt'), 'w') as log:
            log.write(time.strftime('%d %b %Y - %I:%M %p'))
        return content
    except Exception as e:
        dialog.close()
        xbmcgui.Dialog().notification("Update Failed", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)
        return ""

def add_favourite(name, url, logo):
    favourites = []
    if os.path.exists(FAVOURITES_FILE):
        with open(FAVOURITES_FILE, 'r') as f:
            favourites = json.load(f)
    if not any(f['url'] == url for f in favourites):
        favourites.append({'name': name, 'url': url, 'logo': logo})
        with open(FAVOURITES_FILE, 'w') as f:
            json.dump(favourites, f)
    xbmc.executebuiltin("Container.Refresh")

def remove_favourite(url):
    if os.path.exists(FAVOURITES_FILE):
        with open(FAVOURITES_FILE, 'r') as f:
            favourites = json.load(f)
        favourites = [f for f in favourites if f['url'] != url]
        with open(FAVOURITES_FILE, 'w') as f:
            json.dump(favourites, f)
    xbmc.executebuiltin("Container.Refresh")

def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    mode = params.get('mode')

    if mode == 'settings':
        show_settings()
    elif mode == 'set_pin':
        set_pin_from_settings()
    elif mode == 'change_pin':
        change_pin()
    elif mode == 'reset_pin':
        reset_pin()
    elif mode == 'dev_toggle':
        toggle_developer_mode()
    elif mode == 'view_changelog':
        view_changelog()
    elif mode == 'update_tv':
        fetch_m3u(force_refresh=True)
        xbmcgui.Dialog().notification("IPTV-Org", "Channels updated.", xbmcgui.NOTIFICATION_INFO, 3000)
    elif mode == 'live_categories':
        list_m3u_group_category()
    elif mode == 'favourites':
        list_favourites()
    elif mode == 'm3u_group_items':
        list_m3u_group_items(params.get('group'))
    elif mode == 'search':
        search()
    elif mode == 'add_favourite':
        add_favourite(params.get('name'), params.get('url'), params.get('logo'))
    elif mode == 'remove_favourite':
        remove_favourite(params.get('url'))
    else:
        main_menu()

if __name__ == '__main__':
    router(sys.argv[2][1:])
        