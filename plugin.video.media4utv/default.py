# -*- coding: utf-8 -*-
"""
Media4u TV Kodi plugin
Version 4.5.0
Kodi 21 and Kodi 22 friendly, Python 3 only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Tuple

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
import requests

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name") or "Media4u TV"
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 else -1
BASE_URL = sys.argv[0] if len(sys.argv) > 0 else ""

SERVER = "https://tv.media4u.top"
FREE_USER = "media4u"
FREE_PASS = "media4u"
FIRST_RUN_KEY = "first_run_done"

HEADERS = {
    "User-Agent": "Kodi Media4uTV/4.5.0",
    "Accept": "application/json,text/plain,*/*",
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile")).rstrip("/\\")
if not xbmcvfs.exists(PROFILE_PATH):
    xbmcvfs.mkdirs(PROFILE_PATH)

FAV_FILE = os.path.join(PROFILE_PATH, "favorites.json")
CACHE_FILE = os.path.join(PROFILE_PATH, "api_cache.json")
CACHE_TTL_SECONDS = 10 * 60


def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def notify(message: str, title: str = ADDON_NAME, ms: int = 3000, icon: str = xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(title, message, icon, ms)


def build_url(params: Dict[str, Any]) -> str:
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def quote(value: Any) -> str:
    return urllib.parse.quote_plus(str(value or ""))


def setting_bool(key: str, default: bool = False) -> bool:
    value = (ADDON.getSetting(key) or "").strip().lower()
    if not value:
        return default
    return value in {"true", "1", "yes", "on"}


def get_setting(key: str, default: str = "") -> str:
    value = ADDON.getSetting(key)
    return value if value not in (None, "") else default


def get_effective_creds() -> Tuple[str, str, str]:
    if not setting_bool("use_paid_login", False):
        return FREE_USER, FREE_PASS, "Free Access"

    user = get_setting("username").strip()
    pwd = get_setting("password").strip()
    if not user or not pwd:
        xbmcgui.Dialog().ok(ADDON_NAME, "Paid login is selected, but the username or password is missing.\n\nFree Access will be used for now.")
        ADDON.setSetting("use_paid_login", "false")
        return FREE_USER, FREE_PASS, "Free Access"

    return user, pwd, "Paid Login"


def xc_api_url(endpoint: str) -> str:
    user, pwd, _label = get_effective_creds()
    sep = "&" if "?" in endpoint else "?"
    return f"{SERVER}/{endpoint}{sep}username={quote(user)}&password={quote(pwd)}"


def load_cache() -> Dict[str, Any]:
    try:
        if not os.path.exists(CACHE_FILE):
            return {}
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"Cache read failed: {exc}", xbmc.LOGWARNING)
        return {}


def save_cache(cache: Dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
    except Exception as exc:
        log(f"Cache save failed: {exc}", xbmc.LOGWARNING)


def clear_cache() -> None:
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        notify("Cache cleared")
    except Exception as exc:
        log(f"Cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear cache", icon=xbmcgui.NOTIFICATION_ERROR)


def http_get_json(url: str, timeout: int = 25, use_cache: bool = True) -> Optional[Any]:
    cache = load_cache() if use_cache else {}
    now = int(time.time())
    cached = cache.get(url)
    if use_cache and isinstance(cached, dict) and now - int(cached.get("time", 0)) < CACHE_TTL_SECONDS:
        return cached.get("data")

    try:
        response = SESSION.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if use_cache:
            cache[url] = {"time": now, "data": data}
            save_cache(cache)
        return data
    except requests.exceptions.Timeout:
        notify("Connection timed out", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"Timeout: {url}", xbmc.LOGERROR)
    except requests.exceptions.RequestException as exc:
        notify("Server connection failed", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"HTTP error: {exc}", xbmc.LOGERROR)
    except ValueError as exc:
        notify("Server returned invalid JSON", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"JSON error: {exc}", xbmc.LOGERROR)
    return None


def first_run_check() -> None:
    if setting_bool(FIRST_RUN_KEY, False):
        return
    choice = xbmcgui.Dialog().select("Media4u TV setup", ["Use Free Access", "Use Paid Login"])
    if choice == 1:
        ADDON.setSetting("use_paid_login", "true")
        ADDON.openSettings()
    else:
        ADDON.setSetting("use_paid_login", "false")
    ADDON.setSetting(FIRST_RUN_KEY, "true")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def set_art(li: xbmcgui.ListItem, thumb: str = "") -> None:
    if thumb:
        li.setArt({"thumb": thumb, "icon": thumb, "poster": thumb})


def set_video_info(li: xbmcgui.ListItem, title: str, plot: str = "", year: Any = None) -> None:
    info = {"title": title}
    if plot:
        info["plot"] = plot
    if year:
        info["year"] = safe_int(year)
    li.setInfo("video", info)


def add_folder(label: str, mode: str, extra: Optional[Dict[str, Any]] = None, thumb: str = "") -> None:
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    set_art(li, thumb)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, True)


def add_action(label: str, mode: str, extra: Optional[Dict[str, Any]] = None) -> None:
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, False)


def read_json_file(path: str, fallback: Any) -> Any:
    try:
        if not os.path.exists(path):
            return fallback
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data
    except Exception as exc:
        log(f"Could not read {path}: {exc}", xbmc.LOGWARNING)
        return fallback


def write_json_file(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"Could not write {path}: {exc}", xbmc.LOGERROR)


def fav_load() -> List[Dict[str, str]]:
    data = read_json_file(FAV_FILE, [])
    return data if isinstance(data, list) else []


def fav_save(items: List[Dict[str, str]]) -> None:
    write_json_file(FAV_FILE, items)


def fav_is_saved(url: str) -> bool:
    clean_url = (url or "").strip()
    return any((item.get("url") or "").strip() == clean_url for item in fav_load())


def fav_add(name: str, url: str, thumb: str = "") -> None:
    clean_url = (url or "").strip()
    if not clean_url:
        notify("Cannot add an empty stream", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    items = fav_load()
    if any((item.get("url") or "").strip() == clean_url for item in items):
        notify("Already in favourites")
        return
    items.append({"name": name or "Unknown", "url": clean_url, "thumb": thumb or ""})
    fav_save(items)
    notify("Added to favourites")


def fav_remove(url: str) -> None:
    clean_url = (url or "").strip()
    fav_save([item for item in fav_load() if (item.get("url") or "").strip() != clean_url])
    notify("Removed from favourites")


def clear_favourites() -> None:
    if xbmcgui.Dialog().yesno(ADDON_NAME, "Remove all saved favourites?"):
        fav_save([])
        notify("Favourites cleared")


def add_fav_context(li: xbmcgui.ListItem, name: str, play_url: str, thumb: str = "") -> None:
    if not play_url:
        return
    if fav_is_saved(play_url):
        cmd = f'RunPlugin({build_url({"mode": "fav_remove", "url": play_url})})'
        li.addContextMenuItems([("Remove from Media4u favourites", cmd)], replaceItems=False)
    else:
        cmd = f'RunPlugin({build_url({"mode": "fav_add", "name": name, "url": play_url, "thumb": thumb})})'
        li.addContextMenuItems([("Add to Media4u favourites", cmd)], replaceItems=False)


def add_playable(name: str, play_url: str, thumb: str = "", plot: str = "", year: Any = None) -> None:
    li = xbmcgui.ListItem(label=name)
    set_art(li, thumb)
    set_video_info(li, name, plot, year)
    li.setProperty("IsPlayable", "true")
    li.setPath(play_url)
    add_fav_context(li, name, play_url, thumb)
    xbmcplugin.addDirectoryItem(HANDLE, play_url, li, False)


def sorted_items(items: Iterable[Dict[str, Any]], name_key: str = "name") -> List[Dict[str, Any]]:
    return sorted(list(items), key=lambda i: (i.get(name_key) or i.get("category_name") or "").lower())


def list_categories(action: str, next_mode: str, title: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, title)
    xbmcplugin.setContent(HANDLE, "videos")
    data = http_get_json(xc_api_url(f"player_api.php?action={action}"))
    if not isinstance(data, list) or not data:
        add_action("No categories found", "main")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    for cat in sorted_items(data, "category_name"):
        name = cat.get("category_name") or "Unknown"
        cat_id = str(cat.get("category_id") or "")
        if cat_id:
            add_folder(name, next_mode, {"cat_id": cat_id})
    xbmcplugin.endOfDirectory(HANDLE)


def list_streams(content_type: str, cat_id: str = "", title: str = "") -> None:
    xbmcplugin.setPluginCategory(HANDLE, title or "Media4u TV")
    xbmcplugin.setContent(HANDLE, "videos")
    if content_type == "live":
        endpoint = f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}"
    elif content_type == "vod":
        endpoint = f"player_api.php?action=get_vod_streams&category_id={quote(cat_id)}"
    else:
        endpoint = f"player_api.php?action=get_series&category_id={quote(cat_id)}"

    data = http_get_json(xc_api_url(endpoint))
    if not isinstance(data, list) or not data:
        add_action("Nothing found", "main")
        xbmcplugin.endOfDirectory(HANDLE)
        return

    user, pwd, _label = get_effective_creds()
    for item in sorted_items(data):
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
        plot = item.get("plot") or item.get("description") or ""
        year = item.get("year") or item.get("releaseDate") or None
        if content_type == "live":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            add_playable(name, f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{stream_id}.ts", icon, plot, year)
        elif content_type == "vod":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            ext = item.get("container_extension") or "mp4"
            add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{stream_id}.{ext}", icon, plot, year)
        else:
            series_id = str(item.get("series_id") or "")
            if not series_id:
                continue
            li = xbmcgui.ListItem(label=name)
            set_art(li, icon)
            set_video_info(li, name, plot, year)
            xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_seasons", "series_id": series_id}), li, True)
    xbmcplugin.endOfDirectory(HANDLE)


def list_recent_vod() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Recently Added Movies")
    xbmcplugin.setContent(HANDLE, "movies")
    data = http_get_json(xc_api_url("player_api.php?action=get_vod_streams"))
    if not isinstance(data, list):
        data = []
    user, pwd, _label = get_effective_creds()
    recent = sorted(data, key=lambda i: safe_int(i.get("added")), reverse=True)[:100]
    for item in recent:
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or ""
        ext = item.get("container_extension") or "mp4"
        stream_id = item.get("stream_id")
        if stream_id is not None:
            add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{stream_id}.{ext}", icon, item.get("plot") or "", item.get("year"))
    xbmcplugin.endOfDirectory(HANDLE)


def list_series_seasons(series_id: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Series Seasons")
    xbmcplugin.setContent(HANDLE, "tvshows")
    data = http_get_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={quote(series_id)}"))
    if not isinstance(data, dict):
        data = {}
    seasons = data.get("seasons") or []
    info = data.get("info") or {}
    cover = info.get("cover") or info.get("cover_big") or ""
    for season in seasons:
        season_num = str(season.get("season_number") or "")
        if not season_num:
            continue
        label = season.get("name") or f"Season {season_num}"
        li = xbmcgui.ListItem(label=label)
        set_art(li, season.get("cover") or cover)
        set_video_info(li, label, info.get("plot") or "")
        xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_episodes", "series_id": series_id, "season": season_num}), li, True)
    xbmcplugin.endOfDirectory(HANDLE)


def list_series_episodes(series_id: str, season_num: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, f"Season {season_num}")
    xbmcplugin.setContent(HANDLE, "episodes")
    data = http_get_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={quote(series_id)}"))
    if not isinstance(data, dict):
        data = {}
    episodes = (data.get("episodes") or {}).get(str(season_num)) or []
    user, pwd, _label = get_effective_creds()
    for ep in episodes:
        title = ep.get("title") or "Episode"
        ep_num = ep.get("episode_num")
        label = f"{ep_num}. {title}" if ep_num not in (None, "") else title
        ep_id = ep.get("id") or ep.get("episode_id")
        if not ep_id:
            continue
        info = ep.get("info") or {}
        thumb = info.get("movie_image") or info.get("cover_big") or info.get("cover") or ""
        ext = ep.get("container_extension") or "mp4"
        add_playable(label, f"{SERVER}/series/{quote(user)}/{quote(pwd)}/{ep_id}.{ext}", thumb, info.get("plot") or "", info.get("year"))
    xbmcplugin.endOfDirectory(HANDLE)


def favourites_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Favourites")
    xbmcplugin.setContent(HANDLE, "videos")
    items = fav_load()
    if not items:
        add_action("No favourites yet", "main")
    else:
        for item in items:
            add_playable(item.get("name") or "Unknown", item.get("url") or "", item.get("thumb") or "")
        add_action("Clear all favourites", "clear_favourites")
    xbmcplugin.endOfDirectory(HANDLE)


def search_menu() -> None:
    term = xbmcgui.Dialog().input("Search Media4u TV", type=xbmcgui.INPUT_ALPHANUM).strip()
    if not term:
        return
    xbmcplugin.setPluginCategory(HANDLE, f"Search: {term}")
    xbmcplugin.setContent(HANDLE, "videos")
    lowered = term.lower()
    user, pwd, _label = get_effective_creds()
    sources = [
        ("Live", "player_api.php?action=get_live_streams", "live"),
        ("Movies", "player_api.php?action=get_vod_streams", "vod"),
        ("Series", "player_api.php?action=get_series", "series"),
    ]
    found = 0
    for label, endpoint, kind in sources:
        data = http_get_json(xc_api_url(endpoint))
        if not isinstance(data, list):
            continue
        matches = [item for item in data if lowered in (item.get("name") or "").lower()]
        for item in sorted_items(matches)[:80]:
            name = f"{label}: {item.get('name') or 'Unknown'}"
            icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
            if kind == "live" and item.get("stream_id") is not None:
                add_playable(name, f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.ts", icon)
                found += 1
            elif kind == "vod" and item.get("stream_id") is not None:
                ext = item.get("container_extension") or "mp4"
                add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.{ext}", icon)
                found += 1
            elif kind == "series" and item.get("series_id"):
                li = xbmcgui.ListItem(label=name)
                set_art(li, icon)
                xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_seasons", "series_id": str(item.get("series_id"))}), li, True)
                found += 1
    if found == 0:
        add_action("No search results found", "main")
    xbmcplugin.endOfDirectory(HANDLE)


def account_status() -> None:
    data = http_get_json(xc_api_url("player_api.php"), use_cache=False)
    user, _pwd, label = get_effective_creds()
    lines = [f"Mode: {label}", f"Username: {user}"]
    if isinstance(data, dict):
        info = data.get("user_info") or {}
        if info:
            lines.extend([
                f"Status: {info.get('status', 'Unknown')}",
                f"Active connections: {info.get('active_cons', 'Unknown')}",
                f"Max connections: {info.get('max_connections', 'Unknown')}",
            ])
            exp = safe_int(info.get("exp_date"))
            if exp:
                lines.append("Expires: " + time.strftime("%Y-%m-%d", time.localtime(exp)))
    xbmcgui.Dialog().ok(ADDON_NAME, "\n".join(lines))


def connection_test() -> None:
    data = http_get_json(xc_api_url("player_api.php"), timeout=12, use_cache=False)
    if isinstance(data, dict):
        notify("Connection OK")
    else:
        notify("Connection failed", icon=xbmcgui.NOTIFICATION_ERROR)


def tools_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Tools")
    add_action("Account status", "account_status")
    add_action("Test connection", "connection_test")
    add_action("Clear API cache", "clear_cache")
    add_action("Clear favourites", "clear_favourites")
    add_action("Settings", "open_settings")
    xbmcplugin.endOfDirectory(HANDLE)


def main_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, ADDON_NAME)
    xbmcplugin.setContent(HANDLE, "videos")
    if setting_bool("show_account_status", True):
        _user, _pwd, label = get_effective_creds()
        add_action(f"Account: {label}", "account_status")
    add_folder("Live TV", "live_categories")
    add_folder("Movies", "vod_categories")
    add_folder("Recently Added Movies", "recent_vod")
    add_folder("Series", "series_categories")
    add_action("Search", "search")
    add_folder("Favourites", "favourites")
    add_folder("Tools", "tools")
    xbmcplugin.endOfDirectory(HANDLE)


def router(paramstring: str) -> None:
    params = dict(urllib.parse.parse_qsl(paramstring or ""))
    mode = params.get("mode") or "main"
    if mode == "main":
        main_menu()
    elif mode == "open_settings":
        ADDON.openSettings()
    elif mode == "tools":
        tools_menu()
    elif mode == "account_status":
        account_status()
    elif mode == "connection_test":
        connection_test()
    elif mode == "clear_cache":
        clear_cache()
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "clear_favourites":
        clear_favourites()
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "favourites":
        favourites_menu()
    elif mode == "fav_add":
        fav_add(params.get("name") or "Unknown", params.get("url") or "", params.get("thumb") or "")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "fav_remove":
        fav_remove(params.get("url") or "")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "search":
        search_menu()
    elif mode == "live_categories":
        list_categories("get_live_categories", "live_streams", "Live TV")
    elif mode == "vod_categories":
        list_categories("get_vod_categories", "vod_streams", "Movies")
    elif mode == "series_categories":
        list_categories("get_series_categories", "series_list", "Series")
    elif mode == "live_streams":
        list_streams("live", params.get("cat_id") or "", "Live TV")
    elif mode == "vod_streams":
        list_streams("vod", params.get("cat_id") or "", "Movies")
    elif mode == "series_list":
        list_streams("series", params.get("cat_id") or "", "Series")
    elif mode == "recent_vod":
        list_recent_vod()
    elif mode == "series_seasons":
        list_series_seasons(params.get("series_id") or "")
    elif mode == "series_episodes":
        list_series_episodes(params.get("series_id") or "", params.get("season") or "")
    else:
        main_menu()


if __name__ == "__main__":
    first_run_check()
    router(sys.argv[2][1:] if len(sys.argv) > 2 else "")
