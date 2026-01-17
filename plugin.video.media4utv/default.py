# -*- coding: utf-8 -*-

import sys
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

import requests


addon = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

FIRST_RUN_KEY = "first_run_done"

# Locked server, users cannot change it in settings
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


def build_url(query):
    return BASE_URL + "?" + urllib.parse.urlencode(query)


def notify(title, msg, ms=3000):
    xbmcgui.Dialog().notification(title, msg, xbmcgui.NOTIFICATION_INFO, ms)


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


def q(s):
    return urllib.parse.quote_plus(str(s))


def xc_api_url(endpoint):
    user, pwd, _label = get_effective_creds()
    sep = "&" if "?" in endpoint else "?"
    return f"{SERVER}/{endpoint}{sep}username={q(user)}&password={q(pwd)}"


def http_get_json(url, timeout=20):
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


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
    xbmcplugin.addDirectoryItem(HANDLE, play_url, li, False)


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
            play_url = f"{SERVER}/live/{user}/{pwd}/{stream_id}.ts"
            add_playable(name, play_url, icon)

        elif content_type == "vod":
            stream_id = item.get("stream_id")
            ext = item.get("container_extension") or "mp4"
            play_url = f"{SERVER}/movie/{user}/{pwd}/{stream_id}.{ext}"
            add_playable(name, play_url, icon)

        else:
            series_id = str(item.get("series_id") or "")
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
        info = ep.get("info") or {}
        thumb = info.get("movie_image") or info.get("cover_big") or ""

        play_url = f"{SERVER}/series/{user}/{pwd}/{ep_id}.mp4"
        add_playable(name, play_url, thumb)

    xbmcplugin.endOfDirectory(HANDLE)


def main_menu():
    xbmcplugin.setPluginCategory(HANDLE, "Media4uTV")
    xbmcplugin.setContent(HANDLE, "videos")

    if (addon.getSetting("show_account_status") or "").strip().lower() == "true":
        _u, _p, label = get_effective_creds()
        # Make it clickable so they can jump into settings to change login
        add_action(f"Account: {label}", "open_settings")

    add_folder("Live TV", "live_categories")
    add_folder("Movies", "vod_categories")
    add_folder("Series", "series_categories")

    # Always at bottom
    add_action("Settings", "open_settings")

    xbmcplugin.endOfDirectory(HANDLE)


def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    mode = params.get("mode")

    if mode == "open_settings":
        addon.openSettings()
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
