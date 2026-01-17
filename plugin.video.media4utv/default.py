# default.py  (XC only, Favorites, Settings at bottom, Search placeholder)
# Kodi 20+ compatible, server URL locked to https://tv.media4u.top
# Search removed for now, shows "Search coming soon"

# -*- coding: utf-8 -*-

import sys
import os
import json
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
from xbmcvfs import translatePath

import requests

addon = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

FIRST_RUN_KEY = "first_run_done"

# Locked server
SERVER = "https://tv.media4u.top"

# Free defaults
FREE_USER = "media4u"
FREE_PASS = "media4u"

HEADERS = {
    "User-Agent": "Kodi/21 Media4uTV",
    "Accept": "*/*",
    "Connection": "keep-alive",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

PROFILE_PATH = translatePath(addon.getAddonInfo("profile")).rstrip("/\\")
if not os.path.exists(PROFILE_PATH):
    os.makedirs(PROFILE_PATH)

FAV_FILE = os.path.join(PROFILE_PATH, "favorites.json")


def build_url(query):
    return BASE_URL + "?" + urllib.parse.urlencode(query)


def notify(title, msg, ms=3000):
    xbmcgui.Dialog().notification(title, msg, xbmcgui.NOTIFICATION_INFO, ms)


def q(s):
    return urllib.parse.quote_plus(str(s))


def first_run_check():
    if (addon.getSetting(FIRST_RUN_KEY) or "").strip().lower() == "true":
        return

    choice = xbmcgui.Dialog().select("Login type", ["Free Access", "Paid login"])
    if choice == 1:
        addon.setSetting("use_paid_login", "true")
        addon.openSettings()
    else:
        addon.setSetting("use_paid_login", "false")

    addon.setSetting(FIRST_RUN_KEY, "true")


def get_effective_creds():
    use_paid = (addon.getSetting("use_paid_login") or "").strip().lower() == "true"

    if not use_paid:
        return FREE_USER, FREE_PASS, "Free Access"

    user = (addon.getSetting("username") or "").strip()
    pwd = (addon.getSetting("password") or "").strip()

    if not user or not pwd:
        xbmcgui.Dialog().ok(
            "Paid login not set",
            "Username or password missing.\nUsing Free Access for now."
        )
        addon.setSetting("use_paid_login", "false")
        return FREE_USER, FREE_PASS, "Free Access"

    return user, pwd, "Paid login"


def xc_api_url(endpoint):
    user, pwd, _label = get_effective_creds()
    sep = "&" if "?" in endpoint else "?"
    return f"{SERVER}/{endpoint}{sep}username={q(user)}&password={q(pwd)}"


def http_get_json(url, timeout=25):
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        xbmc.log(f"[Media4uTV] HTTP JSON error: {e}", xbmc.LOGERROR)
        return None


# -------------------------
# Favorites
# -------------------------

def fav_load():
    try:
        if not os.path.exists(FAV_FILE):
            return []
        with open(FAV_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def fav_save(items):
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fav_is_saved(url):
    url = (url or "").strip()
    if not url:
        return False
    for it in fav_load():
        if (it.get("url") or "").strip() == url:
            return True
    return False


def fav_add(name, url, thumb=""):
    url = (url or "").strip()
    if not url:
        notify("Media4uTV", "Cannot add empty stream")
        return

    items = fav_load()
    for it in items:
        if (it.get("url") or "").strip() == url:
            notify("Media4uTV", "Already in Favorites")
            return

    items.append({"name": name or "Unknown", "url": url, "thumb": thumb or ""})
    fav_save(items)
    notify("Media4uTV", "Added to Favorites")


def fav_remove(url):
    url = (url or "").strip()
    if not url:
        return
    items = fav_load()
    new_items = [it for it in items if (it.get("url") or "").strip() != url]
    fav_save(new_items)
    notify("Media4uTV", "Removed from Favorites")


def favorites_menu():
    xbmcplugin.setPluginCategory(HANDLE, "Media4uTV Favorites")
    xbmcplugin.setContent(HANDLE, "videos")

    items = fav_load()
    if not items:
        li = xbmcgui.ListItem(label="No favorites yet")
        xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "open_settings"}), li, False)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    for it in items:
        name = it.get("name") or "Unknown"
        url = it.get("url") or ""
        thumb = it.get("thumb") or ""

        li = xbmcgui.ListItem(label=name)
        if thumb:
            li.setArt({"thumb": thumb, "icon": thumb, "poster": thumb})
        li.setInfo("video", {"title": name})
        li.setProperty("IsPlayable", "true")
        li.setPath(url)

        cm = [
            ("Remove from Media4uTV Favorites", f'RunPlugin({build_url({"mode":"fav_remove","url":url})})')
        ]
        li.addContextMenuItems(cm, replaceItems=False)

        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)

    xbmcplugin.endOfDirectory(HANDLE)


def add_fav_context_menu(li, name, play_url, thumb=""):
    if not play_url:
        return

    already = fav_is_saved(play_url)

    if not already:
        cmd = f'RunPlugin({build_url({"mode":"fav_add","name":name,"url":play_url,"thumb":thumb})})'
        li.addContextMenuItems([("Add to Media4uTV Favorites", cmd)], replaceItems=False)
    else:
        cmd = f'RunPlugin({build_url({"mode":"fav_remove","url":play_url})})'
        li.addContextMenuItems([("Remove from Media4uTV Favorites", cmd)], replaceItems=False)


# -------------------------
# Helpers
# -------------------------

def add_folder(label, mode, extra=None):
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, True)


def add_action(label, mode, extra=None):
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, False)


def add_playable(name, play_url, thumb=""):
    li = xbmcgui.ListItem(label=name)
    if thumb:
        li.setArt({"thumb": thumb, "icon": thumb, "poster": thumb})
    li.setInfo("video", {"title": name})
    li.setProperty("IsPlayable", "true")
    li.setPath(play_url)

    add_fav_context_menu(li, name, play_url, thumb)

    xbmcplugin.addDirectoryItem(HANDLE, play_url, li, False)


# -------------------------
# XC categories and browsing
# -------------------------

def list_categories(action, next_mode):
    data = http_get_json(xc_api_url(f"player_api.php?action={action}"))
    if not isinstance(data, list):
        data = []

    for cat in data:
        name = cat.get("category_name") or "Unknown"
        cat_id = str(cat.get("category_id") or "")
        li = xbmcgui.ListItem(label=name)
        xbmcplugin.addDirectoryItem(
            HANDLE,
            build_url({"mode": next_mode, "cat_id": cat_id}),
            li,
            True
        )

    xbmcplugin.endOfDirectory(HANDLE)


def list_streams(content_type, cat_id):
    if content_type == "live":
        data = http_get_json(xc_api_url(f"player_api.php?action=get_live_streams&category_id={q(cat_id)}"))
    elif content_type == "vod":
        data = http_get_json(xc_api_url(f"player_api.php?action=get_vod_streams&category_id={q(cat_id)}"))
    else:
        data = http_get_json(xc_api_url(f"player_api.php?action=get_series&category_id={q(cat_id)}"))

    if not isinstance(data, list):
        data = []

    user, pwd, _label = get_effective_creds()

    for item in data:
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or item.get("cover") or ""

        if content_type == "live":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            play_url = f"{SERVER}/live/{user}/{pwd}/{stream_id}.ts"
            add_playable(name, play_url, icon)

        elif content_type == "vod":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            ext = item.get("container_extension") or "mp4"
            play_url = f"{SERVER}/movie/{user}/{pwd}/{stream_id}.{ext}"
            add_playable(name, play_url, icon)

        else:
            series_id = str(item.get("series_id") or "")
            if not series_id:
                continue
            li = xbmcgui.ListItem(label=name)
            if icon:
                li.setArt({"thumb": icon, "icon": icon, "poster": icon})
            xbmcplugin.addDirectoryItem(
                HANDLE,
                build_url({"mode": "series_seasons", "series_id": series_id}),
                li,
                True
            )

    xbmcplugin.endOfDirectory(HANDLE)


def list_series_seasons(series_id):
    data = http_get_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={q(series_id)}"))
    if not isinstance(data, dict):
        data = {}

    seasons = data.get("seasons") or []
    info = data.get("info") or {}
    cover = info.get("cover") or ""

    for s in seasons:
        season_num = str(s.get("season_number"))
        label = s.get("name") or f"Season {season_num}"
        li = xbmcgui.ListItem(label=label)
        if cover:
            li.setArt({"thumb": cover, "icon": cover, "poster": cover})
        xbmcplugin.addDirectoryItem(
            HANDLE,
            build_url({"mode": "series_episodes", "series_id": str(series_id), "season": season_num}),
            li,
            True
        )

    xbmcplugin.endOfDirectory(HANDLE)


def list_series_episodes(series_id, season_num):
    data = http_get_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={q(series_id)}"))
    if not isinstance(data, dict):
        data = {}

    episodes = data.get("episodes") or {}
    season_eps = episodes.get(str(season_num)) or []

    user, pwd, _label = get_effective_creds()

    for ep in season_eps:
        title = ep.get("title") or "Episode"
        ep_num = ep.get("episode_num")
        name = f"{ep_num}. {title}" if ep_num is not None else title

        ep_id = ep.get("id") or ep.get("episode_id")
        if not ep_id:
            continue

        info = ep.get("info") or {}
        thumb = info.get("movie_image") or info.get("cover_big") or ""

        play_url = f"{SERVER}/series/{user}/{pwd}/{ep_id}.mp4"
        add_playable(name, play_url, thumb)

    xbmcplugin.endOfDirectory(HANDLE)


# -------------------------
# Search placeholder
# -------------------------

def search_menu():
    notify("Media4uTV", "Search coming soon")


# -------------------------
# Main menu
# -------------------------

def main_menu():
    xbmcplugin.setPluginCategory(HANDLE, "Media4uTV")
    xbmcplugin.setContent(HANDLE, "videos")

    if (addon.getSetting("show_account_status") or "").strip().lower() == "true":
        _u, _p, label = get_effective_creds()
        add_action(f"Account: {label}", "open_settings")

    add_folder("Live TV", "live_categories")
    add_folder("Movies", "vod_categories")
    add_folder("Series", "series_categories")

    add_action("Search", "search")
    add_folder("Favorites", "favorites")

    add_action("Settings", "open_settings")

    xbmcplugin.endOfDirectory(HANDLE)


def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    mode = params.get("mode")

    if mode == "open_settings":
        addon.openSettings()
        return

    if mode == "favorites":
        favorites_menu()
        return

    if mode == "fav_add":
        name = params.get("name") or "Unknown"
        url = params.get("url") or ""
        thumb = params.get("thumb") or ""
        fav_add(name, url, thumb)
        xbmc.executebuiltin("Container.Refresh")
        return

    if mode == "fav_remove":
        url = params.get("url") or ""
        fav_remove(url)
        xbmc.executebuiltin("Container.Refresh")
        return

    if mode == "search":
        search_menu()
        return

    if mode == "live_categories":
        list_categories("get_live_categories", "live_streams")
        return
    if mode == "vod_categories":
        list_categories("get_vod_categories", "vod_streams")
        return
    if mode == "series_categories":
        list_categories("get_series_categories", "series_list")
        return

    if mode == "live_streams":
        list_streams("live", params.get("cat_id"))
        return
    if mode == "vod_streams":
        list_streams("vod", params.get("cat_id"))
        return
    if mode == "series_list":
        list_streams("series", params.get("cat_id"))
        return

    if mode == "series_seasons":
        list_series_seasons(params.get("series_id"))
        return
    if mode == "series_episodes":
        list_series_episodes(params.get("series_id"), params.get("season"))
        return

    main_menu()


if __name__ == "__main__":
    first_run_check()
    router(sys.argv[2][1:])
