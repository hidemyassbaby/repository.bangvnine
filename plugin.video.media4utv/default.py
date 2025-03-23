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
from xbmcvfs import translatePath
from collections import defaultdict

addon = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

USE_M3U = addon.getSettingBool("use_m3u_mode")
SERVER = addon.getSetting("server_url").strip() or "https://m3ufilter.media4u.top"
USERNAME = addon.getSetting("username").strip() or "media4u"
PASSWORD = addon.getSetting("password").strip() or "media4u"
CACHE_EXPIRY = 3600  # 1 hour
CACHE_PATH = translatePath(addon.getAddonInfo('profile')).rstrip('/')
if not os.path.exists(CACHE_PATH):
    os.makedirs(CACHE_PATH)

M3U_URL = f"{SERVER}/get.php?username={USERNAME}&password={PASSWORD}&type=m3u_plus"

HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; Android 9) IPTV",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Connection": "Keep-Alive"
}

def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def fetch_api(endpoint):
    sep = '&' if '?' in endpoint else '?'
    url = f"{SERVER}/{endpoint}{sep}username={USERNAME}&password={PASSWORD}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        xbmc.log(f"[Media4u] API error: {e}", xbmc.LOGERROR)
        return {}

def get_cache_filename(url):
    key = hashlib.md5(url.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_PATH, f"cache_{key}.txt")

def fetch_m3u(url):
    cache_file = get_cache_filename(url)
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        if time.time() - mtime < CACHE_EXPIRY:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.text
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return content
    except Exception as e:
        xbmc.log(f"[Media4u] M3U error: {e}", xbmc.LOGERROR)
        return ""

def parse_m3u(data):
    pattern = re.compile(r'#EXTINF:-1.*?tvg-logo="([^"]*)".*?group-title="([^"]*)".*?,(.*?)\n(.*?)\n', re.DOTALL)
    return pattern.findall(data)

def list_m3u_group_category(group_type):
    raw_data = fetch_m3u(M3U_URL)
    streams = parse_m3u(raw_data)
    grouped = defaultdict(list)
    for logo, group, name, url in streams:
        key = group.strip().lower()
        if group_type.lower() == "live" and not any(x in key for x in ["vod", "movie", "series", "show"]):
            grouped[group].append((logo, name, url))
        elif group_type.lower() == "vod" and ("vod" in key or "movie" in key):
            grouped[group].append((logo, name, url))
        elif group_type.lower() == "series" and ("series" in key or "show" in key):
            grouped[group].append((logo, name, url))

    for group, items in sorted(grouped.items()):
        li = xbmcgui.ListItem(label=f"{group} (M3U)")
        url = build_url({'mode': 'm3u_group_items', 'group': group})
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_m3u_items_by_group(group):
    raw_data = fetch_m3u(M3U_URL)
    streams = parse_m3u(raw_data)
    for logo, g, name, url in streams:
        if g != group:
            continue
        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': logo, 'icon': logo, 'poster': logo})
        li.setInfo('video', {'title': name})
        li.setPath(url)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def list_categories(action, next_mode):
    data = fetch_api(f"player_api.php?action={action}")
    for cat in data:
        name = cat.get("category_name")
        cat_id = cat.get("category_id")
        li = xbmcgui.ListItem(label=name)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': next_mode, 'cat_id': cat_id}), li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_streams(content_type, cat_id):
    all_data = fetch_api("player_api.php")
    key_map = {'live': 'live_streams', 'vod': 'movie_streams', 'series': 'series'}
    streams = all_data.get(key_map.get(content_type, ''), [])
    for item in streams:
        if str(item.get("category_id")) != str(cat_id):
            continue
        name = item.get("name")
        stream_id = item.get("stream_id")
        icon = item.get("stream_icon", "")
        url = f"{SERVER}/{content_type}/{USERNAME}/{PASSWORD}/{stream_id}.ts"
        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': icon, 'icon': icon, 'poster': icon})
        li.setInfo('video', {'title': name})
        li.setPath(url)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def main_menu():
    xbmcplugin.setPluginCategory(HANDLE, 'Media4u IPTV')
    xbmcplugin.setContent(HANDLE, 'videos')
    suffix = " (M3U)" if USE_M3U else ""
    items = [
        (f'Live TV{suffix}', 'live_categories'),
        (f'Movies{suffix}', 'vod_categories'),
        (f'Series{suffix}', 'series_categories'),
    ]
    for label, mode in items:
        li = xbmcgui.ListItem(label=label)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': mode}), li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    mode = params.get('mode')

    if USE_M3U:
        if mode == 'live_categories':
            list_m3u_group_category('live')
        elif mode == 'vod_categories':
            list_m3u_group_category('vod')
        elif mode == 'series_categories':
            list_m3u_group_category('series')
        elif mode == 'm3u_group_items':
            list_m3u_items_by_group(params.get('group'))
        else:
            main_menu()
        return

    cat_id = params.get('cat_id')
    if mode == 'live_categories':
        list_categories('get_live_categories', 'live')
    elif mode == 'vod_categories':
        list_categories('get_vod_categories', 'vod')
    elif mode == 'series_categories':
        list_categories('get_series_categories', 'series')
    elif mode in ['live', 'vod', 'series']:
        list_streams(mode, cat_id)
    else:
        main_menu()

if __name__ == '__main__':
    router(sys.argv[2][1:])
