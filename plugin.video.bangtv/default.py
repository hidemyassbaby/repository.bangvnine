# -*- coding: utf-8 -*-
"""
Bang TV Kodi plugin
Version 1.0.13
Kodi 21 and Kodi 22 friendly, Python 3 only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import sqlite3
import urllib.parse
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional, Tuple

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
import requests

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name") or "Bang TV"
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 else -1
BASE_URL = sys.argv[0] if len(sys.argv) > 0 else ""

SERVER = "http://freqdns.com"
DNS_URL = "http://freqdns.com/"
TMDB_PROXY = "https://bangtvkodi.thomasnz.workers.dev"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"
NZ_M3U_URL = "https://i.mjh.nz/nz/raw-tv.m3u8"
DEFAULT_NZ_EPG_URL = "https://i.mjh.nz/nz/epg.xml.gz"
NZ_USER_AGENT = "otg/1.5.1 (AppleTv Apple TV 4; tvOS16.0; appletv.client) libcurl/7.58.0 OpenSSL/1.0.2o zlib/1.2.11 clib/1.8.56"

HEADERS = {
    "User-Agent": "Kodi BangTV/1.0.13",
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
METADATA_DB_FILE = os.path.join(PROFILE_PATH, "metadata.db")
CACHE_TTL_SECONDS = 10 * 60
METADATA_TTL_SECONDS = 30 * 24 * 60 * 60
EPG_TTL_SECONDS = 6 * 60 * 60
PAGE_SIZE = 20
BACKGROUND_QUEUE_FILE = os.path.join(PROFILE_PATH, "metadata_queue.json")
ADDON_ICON = xbmcvfs.translatePath(ADDON.getAddonInfo("icon")) or "icon.png"
ADDON_VERSION = ADDON.getAddonInfo("version") or "1.0.13"
VERSION_MARKER_FILE = os.path.join(PROFILE_PATH, "installed_version.txt")
STARTUP_PRELOAD_FILE = os.path.join(PROFILE_PATH, "startup_preload.json")
PLAY_LINKS_FILE = os.path.join(PROFILE_PATH, "play_links.json")
LIVE_UPDATE_STATE_FILE = os.path.join(PROFILE_PATH, "live_update_state.json")
RECENT_LIVE_FILE = os.path.join(PROFILE_PATH, "recent_live.json")
HIDDEN_LIVE_CATEGORIES_FILE = os.path.join(PROFILE_PATH, "hidden_live_categories.json")
STREAM_HEALTH_FILE = os.path.join(PROFILE_PATH, "stream_health.json")
BACKUP_FILE = os.path.join(PROFILE_PATH, "bangtv_user_backup.json")
PVR_EXPORT_M3U_FILE = os.path.join(PROFILE_PATH, "bangtv_pvr_channels.m3u8")
PVR_EXPORT_INFO_FILE = os.path.join(PROFILE_PATH, "bangtv_pvr_guide_setup.txt")
LIVE_AUTO_CHECK_SECONDS = 30 * 60
LIVE_HIGH_ACTIVITY_SECONDS = 10 * 60
LIVE_HIGH_ACTIVITY_CHANGE_THRESHOLD = 20
LIVE_ACTIVE_CATEGORY_CHECK_SECONDS = 10 * 60
LIVE_RECENT_CATEGORY_CHECK_SECONDS = 30 * 60



def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def notify(message: str, title: str = ADDON_NAME, ms: int = 3000, icon: str = xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(title, message, icon, ms)


def build_url(params: Dict[str, Any]) -> str:
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def quote(value: Any) -> str:
    return urllib.parse.quote_plus(str(value or ""))


def safe_page(value: Any) -> int:
    try:
        page = int(value or 1)
        return page if page > 0 else 1
    except Exception:
        return 1


def paged_items(items: List[Dict[str, Any]], page: int, page_size: int = PAGE_SIZE) -> Tuple[List[Dict[str, Any]], bool]:
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return items[start:end], end < len(items)


def redact_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        safe_query = []
        for key, value in query:
            if key.lower() in {"username", "password"}:
                safe_query.append((key, "***"))
            else:
                safe_query.append((key, value))
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(safe_query), parsed.fragment))
    except Exception:
        return str(url).replace(get_setting("password"), "***")


def setting_bool(key: str, default: bool = False) -> bool:
    value = (ADDON.getSetting(key) or "").strip().lower()
    if not value:
        return default
    return value in {"true", "1", "yes", "on"}


def get_setting(key: str, default: str = "") -> str:
    value = ADDON.getSetting(key)
    return value if value not in (None, "") else default


def preview_metadata_on_browse() -> bool:
    # Fetch Xtream-only details for folder preview panes. This is much faster than TMDB
    # and gives Kodi plot, genre, director, cast, fanart, duration and trailer data.
    return setting_bool("preview_metadata_on_browse", True)


def full_metadata_on_browse() -> bool:
    # Default is fast browsing. Turning this on fetches full Xtream/TMDB info for
    # every item while opening a folder, which gives richer previews but can be slow.
    return setting_bool("full_metadata_on_browse", False)


def has_saved_login() -> bool:
    return bool(get_setting("username").strip() and get_setting("password").strip())


def get_effective_creds() -> Tuple[str, str, str]:
    user = get_setting("username").strip()
    pwd = get_setting("password").strip()
    if not user or not pwd:
        return "", "", "Not logged in"
    return user, pwd, "Logged in"


def login_prompt() -> None:
    current_user = get_setting("username").strip()
    user = xbmcgui.Dialog().input("Bang TV Login - Username", defaultt=current_user, type=xbmcgui.INPUT_ALPHANUM).strip()
    if not user:
        notify("Login cancelled")
        return
    pwd = xbmcgui.Dialog().input("Bang TV Login - Password", type=xbmcgui.INPUT_ALPHANUM, option=xbmcgui.ALPHANUM_HIDE_INPUT).strip()
    if not pwd:
        notify("Password not saved", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    ADDON.setSetting("username", user)
    ADDON.setSetting("password", pwd)
    clear_cache()
    mark_startup_preload_pending("login")
    notify("Login saved. Bang TV will preload channels and EPG in the background.")
    xbmc.executebuiltin("Container.Refresh")


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


def metadata_db() -> sqlite3.Connection:
    conn = sqlite3.connect(METADATA_DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS metadata_cache ("
        "cache_key TEXT PRIMARY KEY, "
        "content_type TEXT, "
        "item_id TEXT, "
        "updated INTEGER, "
        "data TEXT)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metadata_cache_type_id ON metadata_cache(content_type, item_id)")
    return conn


def metadata_cache_key(content_type: str, item_id: Any) -> str:
    return f"{content_type}:{item_id}"


def metadata_cache_get(content_type: str, item_id: Any, ttl: int = METADATA_TTL_SECONDS) -> Dict[str, Any]:
    if item_id in (None, ""):
        return {}
    try:
        key = metadata_cache_key(content_type, item_id)
        now = int(time.time())
        with metadata_db() as conn:
            row = conn.execute("SELECT updated, data FROM metadata_cache WHERE cache_key=?", (key,)).fetchone()
        if not row:
            return {}
        updated, raw = row
        if ttl > 0 and now - int(updated or 0) > ttl:
            return {}
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"SQLite metadata read failed: {exc}", xbmc.LOGWARNING)
        return {}


def metadata_cache_set(content_type: str, item_id: Any, data: Dict[str, Any]) -> None:
    if item_id in (None, "") or not isinstance(data, dict) or not data:
        return
    try:
        key = metadata_cache_key(content_type, item_id)
        payload = json.dumps(data, ensure_ascii=False)
        now = int(time.time())
        with metadata_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata_cache(cache_key, content_type, item_id, updated, data) VALUES (?, ?, ?, ?, ?)",
                (key, str(content_type), str(item_id), now, payload),
            )
    except Exception as exc:
        log(f"SQLite metadata save failed: {exc}", xbmc.LOGWARNING)



def read_background_queue() -> List[Dict[str, Any]]:
    try:
        if not os.path.exists(BACKGROUND_QUEUE_FILE):
            return []
        with open(BACKGROUND_QUEUE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception as exc:
        log(f"Metadata queue read failed: {exc}", xbmc.LOGWARNING)
        return []


def save_background_queue(items: List[Dict[str, Any]]) -> None:
    try:
        with open(BACKGROUND_QUEUE_FILE, "w", encoding="utf-8") as fh:
            json.dump(items[:5000], fh, ensure_ascii=False)
    except Exception as exc:
        log(f"Metadata queue save failed: {exc}", xbmc.LOGWARNING)


def enqueue_background_metadata(content_type: str, ids: List[Any], priority: bool = False) -> None:
    """Queue missing movie/show details for the background service.

    Folder browsing stays fast because this function never calls Xtream.
    The service.py worker fills metadata.db quietly in the background.
    """
    if not setting_bool("background_metadata_service", True) or not setting_bool("enhanced_metadata", True):
        return
    valid_types = {"vod", "series"}
    if content_type not in valid_types:
        return
    clean_ids = []
    for item_id in ids:
        if item_id in (None, ""):
            continue
        sid = str(item_id)
        # Skip anything already cached.
        if metadata_cache_get(content_type, sid):
            continue
        clean_ids.append(sid)
    if not clean_ids:
        return
    try:
        queue = read_background_queue()
        existing = {(str(i.get("type")), str(i.get("id"))) for i in queue if isinstance(i, dict)}
        now = int(time.time())
        new_items = []
        for sid in clean_ids:
            key = (content_type, sid)
            if key not in existing:
                new_items.append({"type": content_type, "id": sid, "queued": now, "priority": bool(priority)})
                existing.add(key)
        if priority:
            queue = new_items + queue
        else:
            queue.extend(new_items)
        save_background_queue(queue)
    except Exception as exc:
        log(f"Metadata queue add failed: {exc}", xbmc.LOGWARNING)

def metadata_cache_delete_file() -> None:
    try:
        if os.path.exists(METADATA_DB_FILE):
            os.remove(METADATA_DB_FILE)
    except Exception as exc:
        log(f"SQLite metadata delete failed: {exc}", xbmc.LOGWARNING)


def clear_cache() -> None:
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        metadata_cache_delete_file()
        notify("Cache cleared")
    except Exception as exc:
        log(f"Cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear cache", icon=xbmcgui.NOTIFICATION_ERROR)



def mark_startup_preload_pending(reason: str = "login") -> None:
    try:
        with open(STARTUP_PRELOAD_FILE, "w", encoding="utf-8") as fh:
            json.dump({"pending": True, "reason": reason, "time": int(time.time())}, fh)
    except Exception as exc:
        log(f"Could not queue startup preload: {exc}", xbmc.LOGWARNING)


def handle_version_update() -> None:
    try:
        old = ""
        if os.path.exists(VERSION_MARKER_FILE):
            with open(VERSION_MARKER_FILE, "r", encoding="utf-8") as fh:
                old = (fh.read() or "").strip()
        if old != ADDON_VERSION:
            with open(VERSION_MARKER_FILE, "w", encoding="utf-8") as fh:
                fh.write(ADDON_VERSION)
            clear_api_cache_only(False)
            mark_startup_preload_pending("version_update")
            notify(f"Bang TV updated to v{ADDON_VERSION}. Menus will refresh on next load.")
    except Exception as exc:
        log(f"Version update check failed: {exc}", xbmc.LOGWARNING)

def file_size(path: str) -> int:
    try:
        return os.path.getsize(path) if os.path.exists(path) else 0
    except Exception:
        return 0


def format_bytes(size: int) -> str:
    try:
        value = float(size or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024.0
    except Exception:
        return "0 B"


def sqlite_count(content_prefixes: Optional[Tuple[str, ...]] = None) -> int:
    if not os.path.exists(METADATA_DB_FILE):
        return 0
    try:
        with metadata_db() as conn:
            if not content_prefixes:
                row = conn.execute("SELECT COUNT(*) FROM metadata_cache").fetchone()
            else:
                clauses = " OR ".join(["content_type LIKE ?" for _ in content_prefixes])
                args = tuple(prefix + "%" for prefix in content_prefixes)
                row = conn.execute(f"SELECT COUNT(*) FROM metadata_cache WHERE {clauses}", args).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception as exc:
        log(f"Cache count failed: {exc}", xbmc.LOGWARNING)
        return 0


def delete_metadata_rows(content_prefixes: Optional[Tuple[str, ...]] = None) -> None:
    if not os.path.exists(METADATA_DB_FILE):
        return
    # VACUUM cannot run inside a transaction. Delete rows first, close/commit,
    # then reopen the database in autocommit mode for VACUUM.
    with metadata_db() as conn:
        if not content_prefixes:
            conn.execute("DELETE FROM metadata_cache")
        else:
            clauses = " OR ".join(["content_type LIKE ?" for _ in content_prefixes])
            args = tuple(prefix + "%" for prefix in content_prefixes)
            conn.execute(f"DELETE FROM metadata_cache WHERE {clauses}", args)
    try:
        vacuum_conn = sqlite3.connect(METADATA_DB_FILE, isolation_level=None)
        try:
            vacuum_conn.execute("VACUUM")
        finally:
            vacuum_conn.close()
    except Exception as exc:
        log(f"Cache vacuum skipped: {exc}", xbmc.LOGWARNING)


def clear_api_cache_only(show_notice: bool = True) -> None:
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        if show_notice:
            notify("API cache cleared")
    except Exception as exc:
        log(f"API cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear API cache", icon=xbmcgui.NOTIFICATION_ERROR)


def clear_metadata_cache_only(show_notice: bool = True) -> None:
    try:
        delete_metadata_rows(("vod", "series", "episode", "vod_full", "series_full", "tmdb"))
        if show_notice:
            notify("Metadata cache cleared")
    except Exception as exc:
        log(f"Metadata cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear metadata cache", icon=xbmcgui.NOTIFICATION_ERROR)


def clear_epg_cache_only(show_notice: bool = True) -> None:
    try:
        delete_metadata_rows(("epg",))
        if show_notice:
            notify("EPG cache cleared")
    except Exception as exc:
        log(f"EPG cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear EPG cache", icon=xbmcgui.NOTIFICATION_ERROR)


def clear_artwork_cache_only(show_notice: bool = True) -> None:
    # Artwork is currently stored as URLs in Kodi metadata rather than a separate artwork DB.
    # This keeps the Tools menu future-proof and clears any artwork-labelled rows if added later.
    try:
        delete_metadata_rows(("artwork", "image", "fanart", "poster"))
        if show_notice:
            notify("Artwork cache cleared")
    except Exception as exc:
        log(f"Artwork cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear artwork cache", icon=xbmcgui.NOTIFICATION_ERROR)


def clear_all_cache_confirmed() -> None:
    try:
        clear_api_cache_only(False)
        try:
            if os.path.exists(BACKGROUND_QUEUE_FILE):
                os.remove(BACKGROUND_QUEUE_FILE)
        except Exception:
            pass
        if os.path.exists(METADATA_DB_FILE):
            os.remove(METADATA_DB_FILE)
        metadata_db().close()
        notify("All caches cleared")
    except Exception as exc:
        log(f"All cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear all cache", icon=xbmcgui.NOTIFICATION_ERROR)


def rebuild_databases_confirmed() -> None:
    try:
        if os.path.exists(METADATA_DB_FILE):
            os.remove(METADATA_DB_FILE)
        metadata_db().close()
        notify("Databases rebuilt")
    except Exception as exc:
        log(f"Database rebuild failed: {exc}", xbmc.LOGERROR)
        notify("Could not rebuild databases", icon=xbmcgui.NOTIFICATION_ERROR)


def cache_stats_text() -> str:
    api_size = file_size(CACHE_FILE)
    queue_count = len(read_background_queue())
    db_size = file_size(METADATA_DB_FILE)
    metadata_rows = sqlite_count(("vod", "series", "episode", "vod_full", "series_full", "tmdb"))
    epg_rows = sqlite_count(("epg",))
    artwork_rows = sqlite_count(("artwork", "image", "fanart", "poster"))
    total = api_size + db_size
    return (
        f"Metadata DB: {format_bytes(db_size)}\n"
        f"API cache: {format_bytes(api_size)}\n"
        f"Background metadata queue: {queue_count} items\n"
        f"Total cache: {format_bytes(total)}\n\n"
        f"Movie/TV metadata rows: {metadata_rows}\n"
        f"EPG rows: {epg_rows}\n"
        f"Artwork rows: {artwork_rows}\n\n"
        "Login details and favourites are not included in cache size."
    )


def confirm_action(title: str, message: str) -> bool:
    # Kodi 21 changed Dialog.yesno positional arguments.
    # Keep this simple so strings are not passed into the autoclose integer slot.
    return xbmcgui.Dialog().yesno(ADDON_NAME, f"{title}\n\n{message}")



def build_full_metadata_cache() -> None:
    """Queue every movie and TV show for the background metadata service.

    This does not block normal browsing. The service fills metadata.db gradually.
    TV show processing also caches seasons and episode metadata where Xtream supplies it.
    """
    user, pwd, _label = get_effective_creds()
    if not user or not pwd:
        notify("Please login first", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    if not confirm_action("Build Full Metadata Cache?", "Bang TV will queue metadata for all Movies, TV Shows and Episodes. This can take a while, but it runs in the background and your login is kept."):
        return

    queued_movies = 0
    queued_series = 0

    vod = http_get_json(xc_api_url("player_api.php?action=get_vod_streams"), timeout=30, use_cache=True, silent=True)
    if isinstance(vod, list):
        ids = []
        for item in vod:
            if isinstance(item, dict):
                sid = item.get("stream_id")
                if sid not in (None, ""):
                    ids.append(sid)
        enqueue_background_metadata("vod", ids, priority=False)
        queued_movies = len(set(str(i) for i in ids))

    series = http_get_json(xc_api_url("player_api.php?action=get_series"), timeout=30, use_cache=True, silent=True)
    if isinstance(series, list):
        ids = []
        for item in series:
            if isinstance(item, dict):
                sid = item.get("series_id")
                if sid not in (None, ""):
                    ids.append(sid)
        enqueue_background_metadata("series", ids, priority=False)
        queued_series = len(set(str(i) for i in ids))

    notify(f"Metadata build queued: {queued_movies} movies, {queued_series} TV shows")
    xbmc.executebuiltin("Container.Refresh")

def cache_action(action: str) -> None:
    if action == "stats":
        xbmcgui.Dialog().textviewer("Bang TV Cache Statistics", cache_stats_text())
        return
    if action == "build_full":
        build_full_metadata_cache()
        return
    if action == "metadata":
        if confirm_action("Clear Metadata Cache?", "This removes cached movie and TV information. Your login, favourites and settings will not be affected."):
            clear_metadata_cache_only(True)
            xbmc.executebuiltin("Container.Refresh")
        return
    if action == "artwork":
        if confirm_action("Clear Artwork Cache?", "This removes cached poster and fanart records. Artwork will be refreshed when required."):
            clear_artwork_cache_only(True)
            xbmc.executebuiltin("Container.Refresh")
        return
    if action == "epg":
        if confirm_action("Clear EPG Cache?", "This removes cached TV guide data. The EPG will be refreshed from Xtream Codes."):
            clear_epg_cache_only(True)
            xbmc.executebuiltin("Container.Refresh")
        return
    if action == "api":
        if confirm_action("Clear API Cache?", "This removes temporary Xtream API responses. Your login, favourites and settings will not be affected."):
            clear_api_cache_only(True)
            xbmc.executebuiltin("Container.Refresh")
        return
    if action == "all":
        if confirm_action("Clear All Cache?", "This removes metadata, artwork, EPG and API cache. Your login, favourites and settings will not be affected."):
            clear_all_cache_confirmed()
            xbmc.executebuiltin("Container.Refresh")
        return
    if action == "rebuild":
        if confirm_action("Rebuild Databases?", "This recreates Bang TV cache databases and can fix corruption or missing information. Your login, favourites and settings will not be affected."):
            rebuild_databases_confirmed()
            xbmc.executebuiltin("Container.Refresh")
        return
    notify("Unknown cache action", icon=xbmcgui.NOTIFICATION_ERROR)


def http_get_json(url: str, timeout: int = 25, use_cache: bool = True, silent: bool = False) -> Optional[Any]:
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
        if not silent:
            notify("Connection timed out", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"Timeout: {redact_url(url)}", xbmc.LOGWARNING if silent else xbmc.LOGERROR)
    except requests.exceptions.RequestException as exc:
        if not silent:
            notify("Server connection failed", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"HTTP error: {redact_url(str(exc))}", xbmc.LOGWARNING if silent else xbmc.LOGERROR)
    except ValueError as exc:
        if not silent:
            notify("Server returned invalid JSON", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"JSON error: {exc}", xbmc.LOGWARNING if silent else xbmc.LOGERROR)
    return None





def get_cached_json_any_age(url: str) -> Optional[Any]:
    try:
        cache = load_cache()
        cached = cache.get(url)
        if isinstance(cached, dict) and "data" in cached:
            return cached.get("data")
    except Exception:
        pass
    return None


def mark_live_category_opened(cat_id: str, title: str = "") -> None:
    try:
        state = load_live_update_state()
        now = int(time.time())
        state["live_opened_at"] = now
        state["active_live_category_id"] = str(cat_id or "")
        state["active_live_category_title"] = title or "Live TV"
        state["active_live_category_opened_at"] = now
        save_live_update_state(state)
    except Exception:
        pass


def cached_json_is_fresh(url: str, ttl: int = CACHE_TTL_SECONDS) -> bool:
    try:
        cache = load_cache()
        cached = cache.get(url)
        if not isinstance(cached, dict):
            return False
        return int(time.time()) - int(cached.get("time", 0)) < ttl
    except Exception:
        return False


def save_json_to_cache(url: str, data: Any) -> None:
    try:
        cache = load_cache()
        cache[url] = {"time": int(time.time()), "data": data}
        save_cache(cache)
    except Exception as exc:
        log(f"Could not save forced API refresh: {exc}", xbmc.LOGWARNING)


def http_get_json_with_progress(url: str, label: str, timeout: int = 25, force_refresh: bool = False, silent: bool = False) -> Optional[Any]:
    if not force_refresh and cached_json_is_fresh(url):
        return http_get_json(url, timeout=timeout, use_cache=True, silent=silent)

    progress = xbmcgui.DialogProgress()
    try:
        progress.create(ADDON_NAME, label)
        progress.update(10, "Connecting to server...")
        if force_refresh:
            data = http_get_json(url, timeout=timeout, use_cache=False, silent=silent)
            if data is not None:
                save_json_to_cache(url, data)
        else:
            data = http_get_json(url, timeout=timeout, use_cache=True, silent=silent)
        progress.update(100, "Done")
        return data
    finally:
        try:
            progress.close()
        except Exception:
            pass


def clear_live_tv_cache(show_notice: bool = True) -> None:
    try:
        cache = load_cache()
        live_markers = (
            "action=get_live_categories",
            "action=get_live_streams",
            "action=get_short_epg",
            "text:" + xtream_xmltv_url(),
        )
        changed = False
        for key in list(cache.keys()):
            if any(marker in str(key) for marker in live_markers):
                cache.pop(key, None)
                changed = True
        if changed:
            save_cache(cache)
        delete_metadata_rows(("epg",))
        if show_notice:
            notify("Live TV will refresh from server")
    except Exception as exc:
        log(f"Live TV cache clear failed: {exc}", xbmc.LOGERROR)
        if show_notice:
            notify("Could not refresh Live TV", icon=xbmcgui.NOTIFICATION_ERROR)


def refresh_live_tv() -> None:
    progress = xbmcgui.DialogProgress()
    try:
        progress.create(ADDON_NAME, "Refresh Live TV")
        progress.update(5, "Starting smart playlist refresh...")
        clear_live_tv_cache(False)
        smart_live_check(force=True, show_notice=True, progress=progress)
        progress.update(100, "Done")
        xbmc.sleep(250)
    finally:
        try:
            progress.close()
        except Exception:
            pass
    xbmc.executebuiltin("Container.Refresh")

def live_cache_keys_for_category(cat_id: str) -> Tuple[str, str]:
    cat_url = xc_api_url("player_api.php?action=get_live_categories")
    streams_url = xc_api_url(f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}")
    return cat_url, streams_url


def load_live_update_state() -> Dict[str, Any]:
    try:
        if not os.path.exists(LIVE_UPDATE_STATE_FILE):
            return {}
        with open(LIVE_UPDATE_STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"Live update state read failed: {exc}", xbmc.LOGWARNING)
        return {}


def save_live_update_state(state: Dict[str, Any]) -> None:
    try:
        with open(LIVE_UPDATE_STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception as exc:
        log(f"Live update state save failed: {exc}", xbmc.LOGWARNING)


def live_item_id(item: Dict[str, Any], category: bool = False) -> str:
    if not isinstance(item, dict):
        return ""
    if category:
        return str(item.get("category_id") or item.get("id") or item.get("category_name") or item.get("name") or "").strip()
    return str(item.get("stream_id") or item.get("id") or item.get("name") or "").strip()


def live_item_signature(item: Dict[str, Any], category: bool = False) -> Dict[str, str]:
    if not isinstance(item, dict):
        return {}
    if category:
        return {
            "name": str(item.get("category_name") or item.get("name") or ""),
            "parent_id": str(item.get("parent_id") or ""),
        }
    return {
        "name": str(item.get("name") or ""),
        "category_id": str(item.get("category_id") or ""),
        "logo": str(item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""),
        "epg_channel_id": str(item.get("epg_channel_id") or item.get("tvg_id") or ""),
    }


def live_signature_map(items: Any, category: bool = False) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = live_item_id(item, category)
        if item_id:
            result[item_id] = live_item_signature(item, category)
    return result


def compare_live_maps(old: Dict[str, Dict[str, str]], new: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    old_ids = set(old.keys())
    new_ids = set(new.keys())
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    changed = sorted([item_id for item_id in (old_ids & new_ids) if old.get(item_id) != new.get(item_id)])
    return {"added": added, "removed": removed, "changed": changed, "added_count": len(added), "removed_count": len(removed), "changed_count": len(changed)}


def live_stats_summary() -> Dict[str, Any]:
    cache = load_cache()
    state = load_live_update_state()
    cat_url, _unused = live_cache_keys_for_category("")
    categories_entry = cache.get(cat_url) if isinstance(cache.get(cat_url), dict) else {}
    categories = categories_entry.get("data") if isinstance(categories_entry, dict) else []
    if not isinstance(categories, list):
        categories = []
    total_channels = 0
    category_cache_count = 0
    newest_update = cache_entry_time(cache, cat_url)
    oldest_update = newest_update
    for cat in categories:
        cat_id = str(cat.get("category_id") or "") if isinstance(cat, dict) else ""
        if not cat_id:
            continue
        _cat_url, streams_url = live_cache_keys_for_category(cat_id)
        entry = cache.get(streams_url)
        if isinstance(entry, dict):
            items = entry.get("data")
            if isinstance(items, list):
                total_channels += len(items)
                category_cache_count += 1
            ts = int(entry.get("time", 0) or 0)
            if ts:
                newest_update = max(newest_update, ts) if newest_update else ts
                oldest_update = min(oldest_update, ts) if oldest_update else ts
    now = int(time.time())
    last_check = int(state.get("last_check", 0) or 0)
    high_until = int(state.get("high_activity_until", 0) or 0)
    interval = LIVE_HIGH_ACTIVITY_SECONDS if high_until > now else LIVE_AUTO_CHECK_SECONDS
    next_check = last_check + interval if last_check else 0
    age = now - newest_update if newest_update else 0
    status = "Fresh" if newest_update and age <= LIVE_AUTO_CHECK_SECONDS else ("Old" if newest_update else "No cache yet")
    last_result = state.get("last_result") if isinstance(state.get("last_result"), dict) else {}
    return {
        "categories": categories,
        "total_categories": len(categories),
        "cached_categories": category_cache_count,
        "total_channels": total_channels,
        "newest_update": newest_update,
        "oldest_update": oldest_update,
        "last_check": last_check,
        "next_check": next_check,
        "status": status,
        "background_enabled": True,
        "high_activity": high_until > now,
        "active_category_id": state.get("active_live_category_id") or "",
        "active_category_title": state.get("active_live_category_title") or "None",
        "active_category_last_check": int((state.get("category_checks") if isinstance(state.get("category_checks"), dict) else {}).get(str(state.get("active_live_category_id") or ""), 0) or 0),
        "active_category_next_check": int((state.get("category_checks") if isinstance(state.get("category_checks"), dict) else {}).get(str(state.get("active_live_category_id") or ""), 0) or 0) + (LIVE_ACTIVE_CATEGORY_CHECK_SECONDS if high_until > now else LIVE_RECENT_CATEGORY_CHECK_SECONDS) if state.get("active_live_category_id") else 0,
        "last_result": last_result,
    }


def smart_live_check(force: bool = False, show_notice: bool = False, progress: Optional[Any] = None) -> Dict[str, Any]:
    now = int(time.time())
    state = load_live_update_state()
    high_until = int(state.get("high_activity_until", 0) or 0)
    interval = LIVE_HIGH_ACTIVITY_SECONDS if high_until > now else LIVE_AUTO_CHECK_SECONDS
    if not force and now - int(state.get("last_check", 0) or 0) < interval:
        return state.get("last_result") if isinstance(state.get("last_result"), dict) else {"checked": False, "reason": "Not due yet"}

    result: Dict[str, Any] = {"checked": True, "time": now, "category_changes": {}, "channel_changes": {}, "changed_category_ids": []}
    try:
        if progress:
            progress.update(15, "Checking latest Live TV categories...")
        cat_url, _unused = live_cache_keys_for_category("")
        cache = load_cache()
        old_categories = cache.get(cat_url, {}).get("data") if isinstance(cache.get(cat_url), dict) else []
        new_categories = http_get_json(cat_url, timeout=25, use_cache=False, silent=True)
        if isinstance(new_categories, list):
            result["category_changes"] = compare_live_maps(live_signature_map(old_categories, True), live_signature_map(new_categories, True))
            cache[cat_url] = {"time": now, "data": new_categories}
        else:
            new_categories = old_categories if isinstance(old_categories, list) else []

        if progress:
            progress.update(45, "Checking latest Live TV channels...")
        all_streams_url = xc_api_url("player_api.php?action=get_live_streams")
        old_streams = cache.get(all_streams_url, {}).get("data") if isinstance(cache.get(all_streams_url), dict) else []
        new_streams = http_get_json(all_streams_url, timeout=35, use_cache=False, silent=True)
        if isinstance(new_streams, list):
            channel_changes = compare_live_maps(live_signature_map(old_streams, False), live_signature_map(new_streams, False))
            result["channel_changes"] = channel_changes
            cache[all_streams_url] = {"time": now, "data": new_streams}
            changed_cat_ids = set()
            old_map = live_signature_map(old_streams, False)
            new_map = live_signature_map(new_streams, False)
            for sid in channel_changes.get("added", []) + channel_changes.get("changed", []):
                cid = (new_map.get(sid) or {}).get("category_id")
                if cid:
                    changed_cat_ids.add(str(cid))
            for sid in channel_changes.get("removed", []):
                cid = (old_map.get(sid) or {}).get("category_id")
                if cid:
                    changed_cat_ids.add(str(cid))
            result["changed_category_ids"] = sorted(changed_cat_ids)
            total_changes = int(channel_changes.get("added_count", 0)) + int(channel_changes.get("removed_count", 0)) + int(channel_changes.get("changed_count", 0))
            if total_changes >= LIVE_HIGH_ACTIVITY_CHANGE_THRESHOLD:
                state["high_activity_until"] = now + (3 * 60 * 60)
            # Update cached category folders for changed categories only.
            if progress:
                progress.update(70, "Updating changed categories...")
            for index, cid in enumerate(result["changed_category_ids"][:30]):
                _cu, streams_url = live_cache_keys_for_category(cid)
                items = [item for item in new_streams if isinstance(item, dict) and str(item.get("category_id") or "") == str(cid)]
                cache[streams_url] = {"time": now, "data": items}
                if progress and result["changed_category_ids"]:
                    progress.update(70 + min(20, int((index + 1) * 20 / max(1, len(result["changed_category_ids"])))), f"Updated category {index + 1} of {len(result['changed_category_ids'])}")
        else:
            result["error"] = "Could not read latest channel list"
        save_cache(cache)
    except Exception as exc:
        result["error"] = str(exc)
        log(f"Smart Live TV check failed: {exc}", xbmc.LOGWARNING)

    state["last_check"] = now
    state["last_result"] = result
    save_live_update_state(state)
    if show_notice:
        ch = result.get("channel_changes") if isinstance(result.get("channel_changes"), dict) else {}
        added = int(ch.get("added_count", 0) or 0)
        removed = int(ch.get("removed_count", 0) or 0)
        changed = int(ch.get("changed_count", 0) or 0)
        if added or removed or changed:
            notify(f"Live TV updated: +{added}, -{removed}, changed {changed}")
        elif result.get("error"):
            notify("Live TV check failed, using saved list", icon=xbmcgui.NOTIFICATION_WARNING)
        else:
            notify("Live TV already up to date")
    return result


def maybe_start_live_background_check() -> None:
    try:
        # Kodi plugin calls are short lived, so use the service for real background checks.
        # This marker lets service.py know the user opened Live TV recently.
        state = load_live_update_state()
        state["live_opened_at"] = int(time.time())
        save_live_update_state(state)
    except Exception:
        pass


def cache_entry_time(cache: Dict[str, Any], key: str) -> int:
    try:
        item = cache.get(key)
        if isinstance(item, dict):
            return int(item.get("time", 0) or 0)
    except Exception:
        pass
    return 0


def nice_time(ts: int) -> str:
    if not ts:
        return "Never"
    try:
        return datetime.fromtimestamp(ts).strftime("%a %d %b, %I:%M %p")
    except Exception:
        return "Unknown"


def live_tv_stats() -> None:
    stats = live_stats_summary()
    result = stats.get("last_result") if isinstance(stats.get("last_result"), dict) else {}
    ch = result.get("channel_changes") if isinstance(result.get("channel_changes"), dict) else {}
    cc = result.get("category_changes") if isinstance(result.get("category_changes"), dict) else {}
    lines = [
        f"Last updated: {nice_time(int(stats.get('newest_update', 0) or 0))}",
        f"Oldest category cache: {nice_time(int(stats.get('oldest_update', 0) or 0))}",
        f"Last server check: {nice_time(int(stats.get('last_check', 0) or 0))}",
        f"Next auto check: {nice_time(int(stats.get('next_check', 0) or 0)) if stats.get('next_check') else 'When Live TV is opened'}",
        f"Active category: {stats.get('active_category_title', 'None')}",
        f"Active category last checked: {nice_time(int(stats.get('active_category_last_check', 0) or 0))}",
        f"Active category next check: {nice_time(int(stats.get('active_category_next_check', 0) or 0)) if stats.get('active_category_next_check') else 'When opened again'}",
        f"Total categories: {stats.get('total_categories', 0)}",
        f"Cached categories: {stats.get('cached_categories', 0)}",
        f"Total cached channels: {stats.get('total_channels', 0)}",
        f"New channels found: {int(ch.get('added_count', 0) or 0)}",
        f"Removed channels: {int(ch.get('removed_count', 0) or 0)}",
        f"Changed channels: {int(ch.get('changed_count', 0) or 0)}",
        f"New categories found: {int(cc.get('added_count', 0) or 0)}",
        f"Removed categories: {int(cc.get('removed_count', 0) or 0)}",
        f"Changed categories: {int(cc.get('changed_count', 0) or 0)}",
        f"Cache status: {stats.get('status', 'Unknown')}",
        f"High activity mode: {'On' if stats.get('high_activity') else 'Off'}",
        "Background updates: Enabled",
    ]
    if result.get("error"):
        lines.append(f"Last check message: {result.get('error')}")
    xbmcgui.Dialog().textviewer("Live TV Stats", "\n".join(lines))

def clear_live_category_cache(cat_id: str, show_notice: bool = True) -> None:
    try:
        _cat_url, streams_url = live_cache_keys_for_category(cat_id)
        cache = load_cache()
        changed = False
        for key in list(cache.keys()):
            if str(key) == streams_url or f"category_id={quote(cat_id)}" in str(key):
                cache.pop(key, None)
                changed = True
        if changed:
            save_cache(cache)
        if show_notice:
            notify("Live TV category will refresh from server")
    except Exception as exc:
        log(f"Live TV category cache clear failed: {exc}", xbmc.LOGERROR)
        if show_notice:
            notify("Could not refresh category", icon=xbmcgui.NOTIFICATION_ERROR)


def refresh_live_category(cat_id: str, title: str = "") -> None:
    if not cat_id:
        notify("No Live TV category selected", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    endpoint = f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}"
    url = xc_api_url(endpoint)
    label = title or "Live TV category"
    progress = xbmcgui.DialogProgress()
    try:
        progress.create(ADDON_NAME, "Updating Category")
        progress.update(10, f"Preparing {label}...")
        clear_live_category_cache(cat_id, False)
        progress.update(35, "Contacting server for latest channels...")
        data = http_get_json(url, timeout=30, use_cache=False, silent=False)
        if data is not None:
            progress.update(65, "Comparing with saved category...")
            cache = load_cache()
            old_data = cache.get(url, {}).get("data") if isinstance(cache.get(url), dict) else []
            changes = compare_live_maps(live_signature_map(old_data, False), live_signature_map(data, False)) if isinstance(data, list) else {}
            progress.update(75, "Saving latest channel list...")
            save_json_to_cache(url, data)
            if isinstance(data, list):
                state = load_live_update_state()
                state["last_check"] = int(time.time())
                state["last_result"] = {"checked": True, "time": int(time.time()), "category_update": str(cat_id), "channel_changes": changes, "changed_category_ids": [str(cat_id)]}
                save_live_update_state(state)
                progress.update(95, f"Loaded {len(data)} channels")
            else:
                progress.update(95, "Latest category data saved")
        else:
            progress.update(95, "Server update failed, opening saved list...")
        xbmc.sleep(250)
    finally:
        try:
            progress.close()
        except Exception:
            pass

    list_streams("live", cat_id, title or "Live TV", 1)

def http_get_text(url: str, timeout: int = 20, use_cache: bool = True, ttl: int = CACHE_TTL_SECONDS, silent: bool = True) -> str:
    cache = load_cache() if use_cache else {}
    now = int(time.time())
    key = "text:" + url
    cached = cache.get(key)
    if use_cache and isinstance(cached, dict) and now - int(cached.get("time", 0)) < ttl:
        return str(cached.get("data") or "")
    try:
        response = SESSION.get(url, timeout=timeout)
        response.raise_for_status()
        text = response.text
        if use_cache:
            cache[key] = {"time": now, "data": text}
            save_cache(cache)
        return text
    except requests.exceptions.Timeout:
        if not silent:
            notify("Connection timed out", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"Timeout: {redact_url(url)}", xbmc.LOGWARNING)
    except requests.exceptions.RequestException as exc:
        if not silent:
            notify("Server connection failed", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"HTTP text error: {redact_url(str(exc))}", xbmc.LOGWARNING)
    return ""


def http_get_bytes(url: str, timeout: int = 25, use_cache: bool = True, ttl: int = EPG_TTL_SECONDS, silent: bool = True) -> bytes:
    cache = load_cache() if use_cache else {}
    now = int(time.time())
    key = "bytes:" + url
    cached = cache.get(key)
    if use_cache and isinstance(cached, dict) and now - int(cached.get("time", 0)) < ttl:
        try:
            import base64
            return base64.b64decode(str(cached.get("data") or ""))
        except Exception:
            return b""
    try:
        response = SESSION.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.content or b""
        if use_cache:
            import base64
            cache[key] = {"time": now, "data": base64.b64encode(data).decode("ascii")}
            save_cache(cache)
        return data
    except requests.exceptions.Timeout:
        log(f"Timeout: {redact_url(url)}", xbmc.LOGWARNING)
    except requests.exceptions.RequestException as exc:
        log(f"HTTP bytes error: {redact_url(str(exc))}", xbmc.LOGWARNING)
    return b""


def parse_m3u_attrs(line: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for match in re.finditer(r'([A-Za-z0-9_:-]+)="([^"]*)"', line or ""):
        attrs[match.group(1)] = match.group(2)
    return attrs


def parse_m3u_title(line: str) -> str:
    if "," in line:
        return line.rsplit(",", 1)[-1].strip()
    return "Unknown"


def nz_m3u_data() -> Tuple[List[Dict[str, Any]], str]:
    text = http_get_text(NZ_M3U_URL, timeout=20, use_cache=True, ttl=6 * 60 * 60, silent=True)
    if not text:
        return [], DEFAULT_NZ_EPG_URL
    first = text.splitlines()[0] if text.splitlines() else ""
    header_attrs = parse_m3u_attrs(first)
    epg_url = header_attrs.get("x-tvg-url") or DEFAULT_NZ_EPG_URL
    channels: List[Dict[str, Any]] = []
    pending: Dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = parse_m3u_attrs(line)
            pending = {
                "name": parse_m3u_title(line),
                "tvg_id": attrs.get("tvg-id") or attrs.get("channel-id") or "",
                "channel_id": attrs.get("channel-id") or attrs.get("tvg-id") or "",
                "logo": attrs.get("tvg-logo") or "",
                "group": attrs.get("group-title") or "Nz",
                "user_agent": NZ_USER_AGENT,
                "referrer": "",
            }
        elif line.startswith("#EXTVLCOPT") and pending:
            opt = line.split(":", 1)[-1]
            if opt.startswith("http-user-agent="):
                pending["user_agent"] = opt.split("=", 1)[-1]
            elif opt.startswith("http-referrer="):
                pending["referrer"] = opt.split("=", 1)[-1]
        elif not line.startswith("#") and pending:
            item = dict(pending)
            item["url"] = line
            channels.append(item)
            pending = {}
    return channels, epg_url


def parse_xmltv_time(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    # XMLTV usually uses: 20260613203000 +1200
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M%S%z", "%Y%m%d%H%M%S"):
        try:
            dt = datetime.strptime(text, fmt)
            return int(dt.timestamp())
        except Exception:
            continue
    return None


def format_local_time(ts: Any) -> str:
    try:
        return time.strftime("%I:%M %p", time.localtime(int(ts))).lstrip("0")
    except Exception:
        return ""


def xml_text(parent: Any, tag: str) -> str:
    try:
        elem = parent.find(tag)
        return (elem.text or "").strip() if elem is not None else ""
    except Exception:
        return ""


def nz_epg_map(epg_url: str) -> Dict[str, Dict[str, str]]:
    cached = metadata_cache_get("nz_epg", "all", ttl=EPG_TTL_SECONDS)
    if cached:
        return cached
    raw = http_get_bytes(epg_url or DEFAULT_NZ_EPG_URL, timeout=25, use_cache=True, ttl=EPG_TTL_SECONDS, silent=True)
    if not raw:
        return {}
    try:
        if (epg_url or "").endswith(".gz"):
            raw = gzip.decompress(raw)
    except Exception:
        pass
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        log(f"NZ EPG XML parse failed: {exc}", xbmc.LOGWARNING)
        return {}
    now_ts = int(time.time())
    by_channel: Dict[str, List[Tuple[int, int, str, str]]] = {}
    for prog in root.findall("programme"):
        ch = prog.get("channel") or ""
        start = parse_xmltv_time(prog.get("start"))
        stop = parse_xmltv_time(prog.get("stop"))
        if not ch or start is None or stop is None:
            continue
        if stop < now_ts - 60:
            continue
        title = xml_text(prog, "title")
        desc = xml_text(prog, "desc")
        by_channel.setdefault(ch, []).append((start, stop, title, desc))
    result: Dict[str, Dict[str, str]] = {}
    for ch, rows in by_channel.items():
        rows.sort(key=lambda r: r[0])
        current = None
        nxt = None
        for row in rows:
            if row[0] <= now_ts <= row[1]:
                current = row
            elif row[0] > now_ts and nxt is None:
                nxt = row
            if current and nxt:
                break
        lines: List[str] = []
        if current:
            lines.append(f"Now: {current[2]} ({format_local_time(current[0])} - {format_local_time(current[1])})")
            if current[3]:
                lines.append(current[3])
        if nxt:
            if lines:
                lines.append("")
            lines.append(f"Next: {nxt[2]} ({format_local_time(nxt[0])})")
        if lines:
            result[ch] = {"plot": "\n".join(lines)}
    if result:
        metadata_cache_set("nz_epg", "all", result)
    return result




def xtream_xmltv_url() -> str:
    user, pwd, _label = get_effective_creds()
    if not user or not pwd:
        return ""
    return f"{SERVER}/xmltv.php?username={quote(user)}&password={quote(pwd)}"


def norm_epg_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text


def xmltv_epg_map(epg_url: str, cache_key: str = "live_xmltv") -> Dict[str, Dict[str, str]]:
    """Build a reusable XMLTV Now/Next map, the same style used by New Zealand Streams."""
    if not epg_url or not setting_bool("show_epg", True):
        return {}
    cached = metadata_cache_get("epg_xmltv", cache_key, ttl=EPG_TTL_SECONDS)
    if cached:
        return cached
    raw = http_get_bytes(epg_url, timeout=30, use_cache=True, ttl=EPG_TTL_SECONDS, silent=True)
    if not raw:
        return {}
    try:
        if epg_url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    except Exception:
        pass
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        log(f"XMLTV EPG parse failed: {exc}", xbmc.LOGWARNING)
        return {}

    channel_names: Dict[str, List[str]] = {}
    for channel in root.findall("channel"):
        ch_id = channel.get("id") or ""
        if not ch_id:
            continue
        names = []
        for dn in channel.findall("display-name"):
            if dn.text and dn.text.strip():
                names.append(dn.text.strip())
        channel_names[ch_id] = names

    now_ts = int(time.time())
    by_channel: Dict[str, List[Tuple[int, int, str, str]]] = {}
    for prog in root.findall("programme"):
        ch = prog.get("channel") or ""
        start = parse_xmltv_time(prog.get("start"))
        stop = parse_xmltv_time(prog.get("stop"))
        if not ch or start is None or stop is None:
            continue
        if stop < now_ts - 60:
            continue
        title = xml_text(prog, "title")
        desc = xml_text(prog, "desc")
        by_channel.setdefault(ch, []).append((start, stop, title, desc))

    result: Dict[str, Dict[str, str]] = {}
    for ch, rows in by_channel.items():
        rows.sort(key=lambda r: r[0])
        current = None
        nxt = None
        for row in rows:
            if row[0] <= now_ts <= row[1]:
                current = row
            elif row[0] > now_ts and nxt is None:
                nxt = row
            if current and nxt:
                break
        lines: List[str] = []
        if current:
            lines.append(f"Now: {current[2]} ({format_local_time(current[0])} - {format_local_time(current[1])})")
            if current[3]:
                lines.append(current[3])
        if nxt:
            if lines:
                lines.append("")
            lines.append(f"Next: {nxt[2]} ({format_local_time(nxt[0])})")
        if not lines:
            continue
        value = {"plot": "\n".join(lines)}
        keys = [ch] + channel_names.get(ch, [])
        for key in keys:
            if key:
                result[key] = value
                nkey = norm_epg_key(key)
                if nkey:
                    result[nkey] = value
    if result:
        metadata_cache_set("epg_xmltv", cache_key, result)
    return result


def live_item_epg_from_map(item: Dict[str, Any], epg_map: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    if not epg_map:
        return {}
    name = item.get("name") or ""
    candidates = [
        item.get("epg_channel_id"),
        item.get("tvg_id"),
        item.get("channel_id"),
        item.get("stream_id"),
        name,
    ]
    # Some providers append quality tags to channel names while XMLTV keeps the clean name.
    clean_name = re.sub(r"\b(FHD|HD|SD|UHD|4K|HEVC|H265|H264|1080P|720P)\b", "", str(name or ""), flags=re.I)
    clean_name = " ".join(clean_name.replace("|", " ").split())
    candidates.append(clean_name)
    for key in candidates:
        if key in (None, ""):
            continue
        direct = epg_map.get(str(key))
        if direct:
            return direct
        normed = epg_map.get(norm_epg_key(key))
        if normed:
            return normed
    return {}

def nz_play_url(item: Dict[str, Any]) -> str:
    url = str(item.get("url") or "")
    params = []
    ua = str(item.get("user_agent") or NZ_USER_AGENT)
    ref = str(item.get("referrer") or "")
    if ua:
        params.append(("User-Agent", ua))
    if ref:
        params.append(("Referer", ref))
    if params:
        url += "|" + urllib.parse.urlencode(params)
    return url

def clean_title_for_search(title: Any) -> str:
    text = str(title or "")
    for token in ("1080p", "720p", "2160p", "4K", "UHD", "HD", "FHD", "CAM", "TS", "DVDRIP", "WEBRIP", "BLURAY", "x264", "x265", "HEVC"):
        text = text.replace(token, " ").replace(token.lower(), " ")
    import re
    text = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", text)
    text = re.sub(r"\b(19|20)\d{2}\b", " ", text)
    return " ".join(text.split()).strip()


def tmdb_image(path: Any) -> str:
    value = str(path or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return TMDB_IMAGE_BASE + value
    return value


def tmdb_proxy_json(endpoint: str, timeout: int = 10) -> Optional[Any]:
    if not setting_bool("tmdb_proxy_enabled", True):
        return None
    url = TMDB_PROXY.rstrip("/") + "/" + endpoint.lstrip("/")
    return http_get_json(url, timeout=timeout, use_cache=True)


def pick_youtube_trailer(data: Dict[str, Any]) -> str:
    videos = data.get("videos") if isinstance(data.get("videos"), dict) else {}
    results = videos.get("results") if isinstance(videos.get("results"), list) else []
    for wanted in ("Trailer", "Teaser", "Clip"):
        for video in results:
            if not isinstance(video, dict):
                continue
            if video.get("site") == "YouTube" and video.get("type") == wanted and video.get("key"):
                return str(video.get("key"))
    return ""


def youtube_trailer_url(value: Any) -> str:
    """Return a Kodi-playable YouTube trailer URL from an Xtream/TMDB value."""
    trailer = str(value or "").strip()
    if not trailer:
        return ""
    if trailer.startswith("plugin://"):
        return trailer
    if "youtube.com" in trailer or "youtu.be" in trailer:
        parsed = urllib.parse.urlparse(trailer)
        qs = urllib.parse.parse_qs(parsed.query)
        video_id = (qs.get("v") or [""])[0]
        if not video_id and "youtu.be" in parsed.netloc:
            video_id = parsed.path.strip("/").split("/")[0]
        trailer = video_id or trailer
    # Xtream usually gives just the YouTube video id, for example NQQqInahTAM.
    if "/" not in trailer and " " not in trailer and len(trailer) <= 64:
        return "plugin://plugin.video.youtube/play/?video_id=" + trailer
    return trailer


def meta_trailer(meta: Optional[Dict[str, Any]]) -> str:
    meta = meta or {}
    for key in ("youtube_trailer", "trailer", "youtube", "video", "key"):
        url = youtube_trailer_url(meta.get(key))
        if url:
            return url
    return ""


def add_trailer_context(li: xbmcgui.ListItem, meta: Optional[Dict[str, Any]] = None, content_type: str = "", item_id: Any = "") -> None:
    # Trailer is exposed through Kodi metadata/property, so skins show one clean "Trailer" entry.
    # Do not add a second "Watch trailer" context item here.
    return


def play_trailer(trailer: str = "", content_type: str = "", item_id: str = "") -> None:
    trailer_url = youtube_trailer_url(trailer)
    # If the folder list did not include a trailer, fetch only the selected item.
    if not trailer_url and content_type == "vod" and item_id:
        trailer_url = meta_trailer(vod_info(item_id))
    if not trailer_url and content_type == "series" and item_id:
        trailer_url = meta_trailer(series_info(item_id))
    if not trailer_url:
        notify("No trailer found", icon=xbmcgui.NOTIFICATION_WARNING)
        return
    xbmc.executebuiltin("PlayMedia(" + trailer_url + ")")


def tmdb_to_meta(data: Dict[str, Any], media_type: str) -> Dict[str, Any]:
    if not isinstance(data, dict) or data.get("success") is False:
        return {}
    title = data.get("title") or data.get("name") or ""
    overview = data.get("overview") or ""
    release_date = data.get("release_date") or data.get("first_air_date") or ""
    genres = data.get("genres") if isinstance(data.get("genres"), list) else []
    credits = data.get("credits") if isinstance(data.get("credits"), dict) else {}
    cast_list = credits.get("cast") if isinstance(credits.get("cast"), list) else []
    crew_list = credits.get("crew") if isinstance(credits.get("crew"), list) else []
    directors = [c.get("name") for c in crew_list if isinstance(c, dict) and c.get("job") in ("Director", "Creator") and c.get("name")]
    external = data.get("external_ids") if isinstance(data.get("external_ids"), dict) else {}
    meta = {
        "name": title,
        "plot": overview,
        "overview": overview,
        "releasedate": release_date,
        "releaseDate": release_date,
        "year": release_date[:4] if release_date else "",
        "genre": ", ".join([g.get("name") for g in genres if isinstance(g, dict) and g.get("name")]),
        "rating": data.get("vote_average") or "",
        "tmdb_id": data.get("id") or "",
        "imdb_id": data.get("imdb_id") or external.get("imdb_id") or "",
        "cast": [(c.get("name"), c.get("character") or "") for c in cast_list[:12] if isinstance(c, dict) and c.get("name")],
        "director": ", ".join(directors[:3]),
        "youtube_trailer": pick_youtube_trailer(data),
        "cover": tmdb_image(data.get("poster_path")),
        "cover_big": tmdb_image(data.get("poster_path")),
        "movie_image": tmdb_image(data.get("poster_path")),
        "backdrop_path": tmdb_image(data.get("backdrop_path")),
    }
    if media_type == "tv" and isinstance(data.get("episode_run_time"), list) and data.get("episode_run_time"):
        meta["duration"] = int(data.get("episode_run_time")[0]) * 60
    if media_type == "movie" and data.get("runtime"):
        meta["duration"] = int(data.get("runtime")) * 60
    return {k: v for k, v in meta.items() if v not in (None, "", [], {})}


def get_tmdb_id_from_meta(meta: Dict[str, Any]) -> str:
    for key in ("tmdb_id", "tmdb", "themoviedb", "tmdbid"):
        value = meta.get(key)
        if value not in (None, ""):
            return tmdb_image(value)
    return ""


def enrich_with_tmdb(meta: Dict[str, Any], media_type: str, title: str = "") -> Dict[str, Any]:
    if not setting_bool("tmdb_proxy_enabled", True):
        return meta
    tmdb_id = get_tmdb_id_from_meta(meta)
    data = None
    if tmdb_id:
        data = tmdb_proxy_json(("movie" if media_type == "movie" else "tv") + "?id=" + quote(tmdb_id))
    else:
        search_title = clean_title_for_search(title or meta.get("name") or meta.get("title"))
        if search_title:
            found = tmdb_proxy_json(("search/movie" if media_type == "movie" else "search/tv") + "?query=" + quote(search_title))
            if isinstance(found, dict):
                results = found.get("results") if isinstance(found.get("results"), list) else []
                if results:
                    first = results[0]
                    if isinstance(first, dict) and first.get("id"):
                        data = tmdb_proxy_json(("movie" if media_type == "movie" else "tv") + "?id=" + quote(first.get("id")))
    if isinstance(data, dict):
        tmdb_meta = tmdb_to_meta(data, "movie" if media_type == "movie" else "tv")
        # Xtream values win when already supplied, TMDB fills blanks.
        merged = dict(tmdb_meta)
        merged.update({k: v for k, v in meta.items() if v not in (None, "", [], {})})
        return merged
    return meta


def first_run_check() -> None:
    # No first-run pop-up. Bang TV opens to the menu and waits for Login or Settings.
    return


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def set_art(li: xbmcgui.ListItem, thumb: str = "", fanart: str = "") -> None:
    art = {"icon": thumb or ADDON_ICON, "thumb": thumb or ADDON_ICON}
    if thumb:
        art.update({"poster": thumb})
    if fanart:
        art["fanart"] = fanart
    li.setArt(art)


def normalize_cast(value: Any) -> List[tuple]:
    """Kodi setInfo requires cast/castandrole as a list of tuples."""
    if value in (None, "", []):
        return []
    fixed = []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
        return [(name, "") for name in parts]
    if not isinstance(value, list):
        return []
    for actor in value:
        try:
            if isinstance(actor, tuple):
                if len(actor) >= 2:
                    name, role = actor[0], actor[1]
                elif len(actor) == 1:
                    name, role = actor[0], ""
                else:
                    continue
                if name:
                    fixed.append((str(name), str(role or "")))
            elif isinstance(actor, list):
                if len(actor) >= 2 and actor[0]:
                    fixed.append((str(actor[0]), str(actor[1] or "")))
                elif len(actor) == 1 and actor[0]:
                    fixed.append((str(actor[0]), ""))
            elif isinstance(actor, dict):
                name = actor.get("name") or actor.get("actor") or actor.get("title") or ""
                role = actor.get("character") or actor.get("role") or ""
                if name:
                    fixed.append((str(name), str(role or "")))
            elif actor:
                fixed.append((str(actor), ""))
        except Exception:
            continue
    return fixed


def normalize_genre(value: Any) -> Any:
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item.get("name")))
            elif item:
                names.append(str(item))
        return ", ".join(names)
    return value



def set_video_info_tag(li: xbmcgui.ListItem, info: Dict[str, Any], meta: Dict[str, Any]) -> bool:
    """Set Kodi 20/21/22 InfoTag fields without using deprecated ListItem.setInfo()."""
    try:
        tag = li.getVideoInfoTag()
    except Exception:
        return False
    try:
        if info.get("title") and hasattr(tag, "setTitle"):
            tag.setTitle(str(info.get("title")))
        if info.get("originaltitle") and hasattr(tag, "setOriginalTitle"):
            tag.setOriginalTitle(str(info.get("originaltitle")))
        if info.get("plot") and hasattr(tag, "setPlot"):
            tag.setPlot(str(info.get("plot")))
        if info.get("plot") and hasattr(tag, "setPlotOutline"):
            tag.setPlotOutline(str(info.get("plot")))
        if info.get("year") and hasattr(tag, "setYear"):
            tag.setYear(safe_int(info.get("year")))
        if info.get("premiered") and hasattr(tag, "setPremiered"):
            tag.setPremiered(str(info.get("premiered")))
        if info.get("genre") and hasattr(tag, "setGenres"):
            genres = info.get("genre")
            if isinstance(genres, str):
                genres = [g.strip() for g in genres.split(",") if g.strip()]
            tag.setGenres(genres if isinstance(genres, list) else [str(genres)])
        if info.get("director") and hasattr(tag, "setDirectors"):
            directors = info.get("director")
            if isinstance(directors, str):
                directors = [d.strip() for d in directors.split(",") if d.strip()]
            tag.setDirectors(directors if isinstance(directors, list) else [str(directors)])
        if info.get("duration") and hasattr(tag, "setDuration"):
            tag.setDuration(safe_int(info.get("duration")))
        if info.get("rating") and hasattr(tag, "setRating"):
            try:
                tag.setRating(float(info.get("rating")))
            except Exception:
                pass
        if info.get("mediatype") and hasattr(tag, "setMediaType"):
            tag.setMediaType(str(info.get("mediatype")))
        if info.get("trailer") and hasattr(tag, "setTrailer"):
            tag.setTrailer(str(info.get("trailer")))
        return True
    except Exception as exc:
        log(f"InfoTagVideo set failed: {exc}", xbmc.LOGWARNING)
        return False

def set_video_info(li: xbmcgui.ListItem, title: str, plot: str = "", year: Any = None, meta: Optional[Dict[str, Any]] = None) -> None:
    meta = meta or {}
    info: Dict[str, Any] = {"title": title}
    plot_value = plot or meta.get("plot") or meta.get("description") or meta.get("overview") or ""
    if plot_value:
        info["plot"] = plot_value
        info["plotoutline"] = plot_value
        # Do not set tagline to the same value as plot. Some Kodi skins display
        # tagline above plot, which made the description appear twice.
    media_type = meta.get("mediatype") or meta.get("media_type")
    if media_type:
        info["mediatype"] = str(media_type)
    year_value = year or meta.get("year") or meta.get("releaseDate") or meta.get("releasedate")
    if year_value:
        info["year"] = safe_int(str(year_value)[:4])
    for src, dest in (("genre", "genre"), ("cast", "cast"), ("castandrole", "castandrole"), ("director", "director"), ("rating", "rating"), ("duration", "duration"), ("episode_run_time", "duration"), ("releasedate", "premiered"), ("releaseDate", "premiered"), ("name", "originaltitle")):
        value = meta.get(src)
        if value not in (None, "", []):
            if dest == "rating":
                try:
                    value = float(value)
                except Exception:
                    continue
            elif dest == "duration":
                value = safe_int(value)
            elif dest in ("cast", "castandrole"):
                value = normalize_cast(value)
                if not value:
                    continue
            elif dest == "genre":
                value = normalize_genre(value)
            info[dest] = value
    tag_ok = set_video_info_tag(li, info, meta)
    if not tag_ok:
        try:
            li.setInfo("video", info)
        except TypeError:
            # Never let one bad metadata field stop folders from opening.
            info.pop("cast", None)
            info.pop("castandrole", None)
            li.setInfo("video", info)
    unique_ids = {}
    for key in ("imdb_id", "imdb", "tmdb_id", "tmdb"):
        value = meta.get(key)
        if value not in (None, ""):
            unique_ids["imdb" if "imdb" in key else "tmdb"] = str(value)
    if unique_ids and hasattr(li, "setUniqueIDs"):
        try:
            li.setUniqueIDs(unique_ids, next(iter(unique_ids)))
        except Exception:
            pass
    trailer_url = meta_trailer(meta)
    if trailer_url:
        # This lets Kodi skins show a Trailer button in the movie/show info window.
        li.setProperty("Trailer", trailer_url)
        try:
            tag = li.getVideoInfoTag()
            if hasattr(tag, "setTrailer"):
                tag.setTrailer(trailer_url)
        except Exception:
            pass


def add_folder(label: str, mode: str, extra: Optional[Dict[str, Any]] = None, thumb: str = "", plot: str = "", context_items: Optional[List[Tuple[str, str]]] = None) -> None:
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    set_art(li, thumb or ADDON_ICON)
    if plot:
        set_video_info(li, label, plot, None, {"plot": plot})
    # Replace external/global context menus so Debrid add-ons do not inject entries here.
    li.addContextMenuItems(context_items or [], replaceItems=True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, True)


def add_action(label: str, mode: str, extra: Optional[Dict[str, Any]] = None, thumb: str = "", plot: str = "") -> None:
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    set_art(li, thumb or ADDON_ICON)
    if plot:
        set_video_info(li, label, plot, None, {"plot": plot})
    # Replace external/global context menus so Debrid add-ons do not inject entries here.
    li.addContextMenuItems([], replaceItems=True)
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




def recent_live_load() -> List[Dict[str, str]]:
    data = read_json_file(RECENT_LIVE_FILE, [])
    return data if isinstance(data, list) else []


def recent_live_add(name: str, stream_id: Any, url: str, thumb: str = "", category_id: str = "", epg_plot: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
    sid = str(stream_id or "").strip()
    if not sid:
        return
    items = [i for i in recent_live_load() if str(i.get("stream_id") or "") != sid]
    saved_meta = meta if isinstance(meta, dict) else {}
    if epg_plot and not saved_meta.get("plot"):
        saved_meta["plot"] = epg_plot
    saved_meta["mediatype"] = "video"
    items.insert(0, {
        "name": name or "Unknown",
        "stream_id": sid,
        "url": url or "",
        "thumb": thumb or "",
        "category_id": str(category_id or ""),
        "epg_plot": epg_plot or saved_meta.get("plot") or "",
        "meta": saved_meta,
        "time": int(time.time()),
    })
    write_json_file(RECENT_LIVE_FILE, items[:50])


def recent_live_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Recently Watched")
    xbmcplugin.setContent(HANDLE, "videos")
    items = recent_live_load()
    if not items:
        add_action("No recently watched channels yet", "live_categories")
    for item in items:
        sid = str(item.get("stream_id") or "")
        cached_plot = item.get("epg_plot") or (item.get("meta") or {}).get("plot") or ""
        fresh_epg = live_epg(sid) if sid else {}
        plot = fresh_epg.get("plot") or cached_plot or "Recently watched Live TV channel."
        meta = dict(item.get("meta") or {})
        meta["plot"] = plot
        meta["mediatype"] = "video"
        add_playable(item.get("name") or "Unknown", item.get("url") or "", item.get("thumb") or "", plot, None, meta, "", "", "", sid, item.get("category_id") or "")
    xbmcplugin.endOfDirectory(HANDLE)


def hidden_live_load() -> Dict[str, Dict[str, str]]:
    data = read_json_file(HIDDEN_LIVE_CATEGORIES_FILE, {})
    return data if isinstance(data, dict) else {}


def hidden_live_is_hidden(cat_id: str) -> bool:
    return str(cat_id or "") in hidden_live_load()


def hidden_live_add(cat_id: str, name: str) -> None:
    data = hidden_live_load()
    cid = str(cat_id or "").strip()
    if cid:
        data[cid] = {"name": name or cid, "time": int(time.time())}
        write_json_file(HIDDEN_LIVE_CATEGORIES_FILE, data)
        notify("Category hidden")


def hidden_live_remove(cat_id: str) -> None:
    data = hidden_live_load()
    data.pop(str(cat_id or ""), None)
    write_json_file(HIDDEN_LIVE_CATEGORIES_FILE, data)
    notify("Category restored")


def hidden_live_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Hidden Live TV Categories")
    data = hidden_live_load()
    if not data:
        add_action("No hidden categories", "live_categories")
    for cid, item in sorted(data.items(), key=lambda kv: (kv[1].get("name") or "").lower() if isinstance(kv[1], dict) else kv[0]):
        name = item.get("name") if isinstance(item, dict) else cid
        add_action(f"Unhide: {name}", "live_category_unhide", {"cat_id": cid}, plot="Restores this category to the main Live TV category list.")
    xbmcplugin.endOfDirectory(HANDLE)


def stream_health_load() -> Dict[str, Dict[str, Any]]:
    data = read_json_file(STREAM_HEALTH_FILE, {})
    return data if isinstance(data, dict) else {}


def stream_health_status(stream_id: Any) -> str:
    sid = str(stream_id or "")
    data = stream_health_load().get(sid, {})
    if not isinstance(data, dict):
        return "Unknown"
    fails = int(data.get("fails", 0) or 0)
    last_ok = int(data.get("last_ok", 0) or 0)
    if fails >= 3:
        return "Offline or failing"
    if fails:
        return "Slow or unstable"
    if last_ok:
        return "Working"
    return "Unknown"


def stream_health_mark(stream_id: Any, ok: bool) -> None:
    sid = str(stream_id or "").strip()
    if not sid:
        return
    data = stream_health_load()
    item = data.get(sid) if isinstance(data.get(sid), dict) else {}
    if ok:
        item["last_ok"] = int(time.time())
        item["fails"] = 0
    else:
        item["last_fail"] = int(time.time())
        item["fails"] = int(item.get("fails", 0) or 0) + 1
    data[sid] = item
    write_json_file(STREAM_HEALTH_FILE, data)


def live_dashboard() -> None:
    stats = live_stats_summary()
    state = load_live_update_state()
    ch = (state.get("last_result") or {}).get("channel_changes") if isinstance(state.get("last_result"), dict) else {}
    text = "Bang TV Server Dashboard\n\n"
    text += f"Server: {SERVER}\n"
    text += f"Last update: {nice_time(int(stats.get('newest_update', 0) or 0))}\n"
    text += f"Last server check: {nice_time(int(stats.get('last_check', 0) or 0))}\n"
    text += f"Categories: {stats.get('total_categories', 0)}\n"
    text += f"Cached categories: {stats.get('cached_categories', 0)}\n"
    text += f"Cached channels: {stats.get('total_channels', 0)}\n"
    text += f"Changes last check: +{int((ch or {}).get('added_count', 0) or 0)}, -{int((ch or {}).get('removed_count', 0) or 0)}, changed {int((ch or {}).get('changed_count', 0) or 0)}\n"
    text += f"High Activity Mode: {'On' if stats.get('high_activity') else 'Off'}\n"
    text += f"Cache health: {stats.get('status', 'Unknown')}\n"
    text += f"Background updates: {'Enabled' if stats.get('background_enabled') else 'Disabled'}\n"
    xbmcgui.Dialog().textviewer("Bang TV Dashboard", text)


def live_auto_cleanup(show_notice: bool = True) -> None:
    now = int(time.time())
    try:
        # trim API cache entries older than 30 days, keeping login/settings/favourites alone
        cache = load_cache()
        new_cache = {}
        for key, value in cache.items():
            if not isinstance(value, dict) or now - int(value.get("time", 0) or 0) <= 30 * 24 * 60 * 60:
                new_cache[key] = value
        save_cache(new_cache)
        # trim recent and stream health
        write_json_file(RECENT_LIVE_FILE, recent_live_load()[:50])
        health = stream_health_load()
        health = {k: v for k, v in health.items() if isinstance(v, dict) and now - max(int(v.get("last_ok", 0) or 0), int(v.get("last_fail", 0) or 0)) <= 30 * 24 * 60 * 60}
        write_json_file(STREAM_HEALTH_FILE, health)
        if show_notice:
            notify("Bang TV cleanup complete")
    except Exception as exc:
        log(f"Auto cleanup failed: {exc}", xbmc.LOGWARNING)
        if show_notice:
            notify("Cleanup failed", icon=xbmcgui.NOTIFICATION_ERROR)


def backup_settings() -> None:
    data = {
        "created": int(time.time()),
        "favourites": fav_load(),
        "recent_live": recent_live_load(),
        "hidden_live_categories": hidden_live_load(),
        "stream_health": stream_health_load(),
        "live_update_state": load_live_update_state(),
    }
    write_json_file(BACKUP_FILE, data)
    xbmcgui.Dialog().ok(ADDON_NAME, f"Backup saved to:\n{BACKUP_FILE}")


def restore_settings() -> None:
    data = read_json_file(BACKUP_FILE, {})
    if not isinstance(data, dict) or not data:
        notify("No backup found", icon=xbmcgui.NOTIFICATION_WARNING)
        return
    if not xbmcgui.Dialog().yesno(ADDON_NAME, "Restore favourites, hidden categories, recent channels and Live TV update state from backup?"):
        return
    if isinstance(data.get("favourites"), list):
        fav_save(data.get("favourites"))
    if isinstance(data.get("recent_live"), list):
        write_json_file(RECENT_LIVE_FILE, data.get("recent_live"))
    if isinstance(data.get("hidden_live_categories"), dict):
        write_json_file(HIDDEN_LIVE_CATEGORIES_FILE, data.get("hidden_live_categories"))
    if isinstance(data.get("stream_health"), dict):
        write_json_file(STREAM_HEALTH_FILE, data.get("stream_health"))
    if isinstance(data.get("live_update_state"), dict):
        save_live_update_state(data.get("live_update_state"))
    notify("Backup restored")



def save_play_link(url: str) -> str:
    """Store direct stream URLs outside the visible Kodi item/context URL."""
    if not url:
        return ""
    try:
        import hashlib
        token = hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()
        data = read_json_file(PLAY_LINKS_FILE, {})
        if not isinstance(data, dict):
            data = {}
        data[token] = {"url": url, "time": int(time.time())}
        if len(data) > 1000:
            newest = sorted(data.items(), key=lambda kv: int((kv[1] or {}).get("time", 0)), reverse=True)[:800]
            data = dict(newest)
        write_json_file(PLAY_LINKS_FILE, data)
        return token
    except Exception as exc:
        log(f"Could not save play link: {exc}", xbmc.LOGWARNING)
        return ""


def get_play_link(token: str) -> str:
    if not token:
        return ""
    try:
        data = read_json_file(PLAY_LINKS_FILE, {})
        if isinstance(data, dict):
            item = data.get(token)
            if isinstance(item, dict):
                return item.get("url") or ""
            if isinstance(item, str):
                return item
    except Exception as exc:
        log(f"Could not read play link: {exc}", xbmc.LOGWARNING)
    return ""


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


def fav_category_key(content_type: str, cat_id: str) -> str:
    return f"category:{content_type}:{cat_id}"


def fav_category_is_saved(content_type: str, cat_id: str) -> bool:
    key = fav_category_key(content_type, cat_id)
    return any((item.get("url") or "") == key for item in fav_load())


def fav_category_add(name: str, content_type: str, cat_id: str, thumb: str = "") -> None:
    clean_id = str(cat_id or "").strip()
    if not clean_id:
        notify("Cannot favourite this category", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    key = fav_category_key(content_type or "live", clean_id)
    items = fav_load()
    if any((item.get("url") or "") == key for item in items):
        notify("Category already in favourites")
        return
    items.append({
        "name": name or "Live TV Category",
        "url": key,
        "thumb": thumb or "",
        "type": "category",
        "content_type": content_type or "live",
        "cat_id": clean_id,
    })
    fav_save(items)
    notify("Category added to favourites")


def fav_category_remove(content_type: str, cat_id: str) -> None:
    key = fav_category_key(content_type or "live", str(cat_id or "").strip())
    fav_save([item for item in fav_load() if (item.get("url") or "") != key])
    notify("Category removed from favourites")


def clear_favourites() -> None:
    if xbmcgui.Dialog().yesno(ADDON_NAME, "Remove all saved favourites?"):
        fav_save([])
        notify("Favourites cleared")


def safe_image_url(value: Any) -> str:
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        value = value.get("url") or value.get("path") or ""
    text = str(value or "").strip()
    if not text:
        return ""
    low = text.lower()
    if low.startswith(("script://", "plugin://")):
        return ""
    # Wikimedia thumb URLs generated from SVGs can return HTTP 400 in Kodi.
    # Skip them so Kodi uses the add-on icon instead of spamming CCurlFile errors.
    if "upload.wikimedia.org/wikipedia" in low and ".svg/" in low:
        return ""
    if "sky_sports_logo_2020.svg" in low:
        return ""
    return tmdb_image(text)


def best_image(*values: Any) -> str:
    for value in values:
        image = safe_image_url(value)
        if image:
            return image
    return ""


def vod_info_xtream_only(stream_id: Any) -> Dict[str, Any]:
    """Fast preview metadata from Xtream only, backed by SQLite cache."""
    if not stream_id or not setting_bool("enhanced_metadata", True):
        return {}
    cached = metadata_cache_get("vod", stream_id)
    if cached:
        return cached
    data = http_get_json(xc_api_url(f"player_api.php?action=get_vod_info&vod_id={quote(stream_id)}"), timeout=4, use_cache=False, silent=True)
    if not isinstance(data, dict):
        return {}
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    movie_data = data.get("movie_data") if isinstance(data.get("movie_data"), dict) else {}
    merged = dict(movie_data)
    merged.update(info)
    if merged:
        metadata_cache_set("vod", stream_id, merged)
    return merged


def series_info_xtream_only(series_id: Any) -> Dict[str, Any]:
    """Fast preview metadata from Xtream only, backed by SQLite cache."""
    if not series_id or not setting_bool("enhanced_metadata", True):
        return {}
    cached = metadata_cache_get("series", series_id)
    if cached:
        return cached
    data = http_get_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={quote(series_id)}"), timeout=4, use_cache=False, silent=True)
    if not isinstance(data, dict):
        return {}
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    meta = dict(info)
    if meta:
        metadata_cache_set("series", series_id, meta)
    return meta


def batch_preview_metadata(content_type: str, ids: List[Any], limit: int = PAGE_SIZE) -> Dict[str, Dict[str, Any]]:
    """Load preview metadata for the visible page with a progress dialog.

    Cached rows appear instantly. Missing rows are fetched for the current page
    only, so Kodi can show movie, TV show and episode descriptions as soon as
    the folder opens. Any cancelled or failed rows are queued for the background
    service and will be ready next time.
    """
    if not ids or not preview_metadata_on_browse() or full_metadata_on_browse():
        return {}
    ids = [i for i in ids if i not in (None, "")][:limit]
    results: Dict[str, Dict[str, Any]] = {}
    missing: List[Any] = []
    for item_id in ids:
        cached = metadata_cache_get(content_type, item_id)
        if cached:
            results[str(item_id)] = cached
        else:
            missing.append(item_id)

    if not missing:
        return results

    label = "movies" if content_type == "vod" else "TV shows" if content_type == "series" else "episodes"
    progress = xbmcgui.DialogProgress()
    try:
        progress.create(ADDON_NAME, f"Loading {label} metadata...")
        total = len(missing)
        for index, item_id in enumerate(missing, start=1):
            if progress.iscanceled():
                enqueue_background_metadata(content_type, missing[index-1:], priority=True)
                break
            percent = int((index - 1) * 100 / max(total, 1))
            progress.update(percent, f"Loading {label} metadata, item {index} of {total}")
            try:
                if content_type == "vod":
                    meta = vod_info_xtream_only(item_id)
                elif content_type == "series":
                    meta = series_info_xtream_only(item_id)
                else:
                    meta = metadata_cache_get(content_type, item_id) or {}
                if meta:
                    results[str(item_id)] = meta
                else:
                    enqueue_background_metadata(content_type, [item_id], priority=True)
            except Exception as exc:
                log(f"Preview metadata failed for {content_type} {item_id}: {exc}", xbmc.LOGWARNING)
                enqueue_background_metadata(content_type, [item_id], priority=True)
        progress.update(100, f"Loading {label} metadata, done")
    finally:
        try:
            progress.close()
        except Exception:
            pass
    return results

def vod_info(stream_id: Any) -> Dict[str, Any]:
    if not stream_id or not setting_bool("enhanced_metadata", True):
        return {}
    cached = metadata_cache_get("vod_full", stream_id)
    if cached:
        return cached
    merged = vod_info_xtream_only(stream_id)
    if not merged:
        return {}
    enriched = enrich_with_tmdb(merged, "movie", merged.get("name") or merged.get("title") or "")
    metadata_cache_set("vod_full", stream_id, enriched)
    return enriched


def series_info(series_id: Any) -> Dict[str, Any]:
    if not series_id or not setting_bool("enhanced_metadata", True):
        return {}
    cached = metadata_cache_get("series_full", series_id)
    if cached:
        return cached
    meta = series_info_xtream_only(series_id)
    if not meta:
        return {}
    enriched = enrich_with_tmdb(meta, "tv", meta.get("name") or meta.get("title") or "")
    metadata_cache_set("series_full", series_id, enriched)
    return enriched


def live_epg(stream_id: Any) -> Dict[str, str]:
    if not stream_id or not setting_bool("show_epg", True):
        return {}
    cached = metadata_cache_get("epg", stream_id, ttl=EPG_TTL_SECONDS)
    if cached:
        return cached
    data = http_get_json(xc_api_url(f"player_api.php?action=get_short_epg&stream_id={quote(stream_id)}&limit=2"), timeout=5, use_cache=False, silent=True)
    if not isinstance(data, dict):
        return {}
    listings = data.get("epg_listings") or []
    if not isinstance(listings, list) or not listings:
        return {}
    def decode_text(v: Any) -> str:
        text = str(v or "")
        try:
            import base64
            raw = base64.b64decode(text + "===")
            decoded = raw.decode("utf-8", "ignore").strip()
            return decoded or text
        except Exception:
            return text
    now = listings[0] if isinstance(listings[0], dict) else {}
    nxt = listings[1] if len(listings) > 1 and isinstance(listings[1], dict) else {}
    plot = ""
    if now:
        plot = "Now: " + decode_text(now.get("title"))
        start = now.get("start") or now.get("start_timestamp") or ""
        end = now.get("end") or now.get("stop") or now.get("end_timestamp") or ""
        if start or end:
            
            start_text = format_local_time(start) if str(start).isdigit() else str(start)
            end_text = format_local_time(end) if str(end).isdigit() else str(end)
            plot += f" ({start_text} - {end_text})"
        desc = decode_text(now.get("description"))
        if desc:
            plot += "\n" + desc
    if nxt:
        next_title = decode_text(nxt.get("title"))
        if next_title:
            plot += "\n\nNext: " + next_title
    result = {"plot": plot}
    if plot:
        metadata_cache_set("epg", stream_id, result)
    return result


def logout() -> None:
    if not xbmcgui.Dialog().yesno(ADDON_NAME, "Log out and clear the saved IPTV username and password?"):
        return
    ADDON.setSetting("username", "")
    ADDON.setSetting("password", "")
    clear_cache()
    notify("Logged out")
    xbmc.executebuiltin("Container.Refresh")


def play_url(url: str) -> None:
    if not url:
        notify("No stream URL", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    li = xbmcgui.ListItem(path=url)
    try:
        li.setProperty("inputstream", "")
    except Exception:
        pass
    xbmcplugin.setResolvedUrl(HANDLE, True, li)


def add_fav_context(li: xbmcgui.ListItem, name: str, play_url: str, thumb: str = "") -> None:
    if not play_url:
        return
    if fav_is_saved(play_url):
        cmd = f'RunPlugin({build_url({"mode": "fav_remove", "url": play_url})})'
        li.addContextMenuItems([("Remove from Bang TV favourites", cmd)], replaceItems=True)
    else:
        cmd = f'RunPlugin({build_url({"mode": "fav_add", "name": name, "url": play_url, "thumb": thumb})})'
        li.addContextMenuItems([("Add to Bang TV favourites", cmd)], replaceItems=True)


def add_playable(name: str, play_url: str, thumb: str = "", plot: str = "", year: Any = None, meta: Optional[Dict[str, Any]] = None, fanart: str = "", trailer_content_type: str = "", trailer_item_id: Any = "", live_stream_id: Any = "", live_category_id: str = "") -> None:
    li = xbmcgui.ListItem(label=name)
    set_art(li, thumb, fanart)
    set_video_info(li, name, plot, year, meta)

    # Use a Bang TV plugin playback route instead of exposing direct .mkv/.ts URLs as the item URL.
    # This reduces global Real-Debrid/third-party context menu injection on Movies and TV Shows.
    token = save_play_link(play_url)
    if live_stream_id:
        plugin_play_url = build_url({"mode": "play", "id": token, "live_id": str(live_stream_id), "name": name, "thumb": thumb or "", "cat_id": live_category_id or "", "epg_plot": (plot or "")[:1500]}) if token else build_url({"mode": "play"})
    else:
        plugin_play_url = build_url({"mode": "play", "id": token}) if token else build_url({"mode": "play"})
    li.setProperty("IsPlayable", "true")
    li.setPath(plugin_play_url)

    context_items = []
    if live_stream_id:
        context_items.append((f"Stream health: {stream_health_status(live_stream_id)}", f'Notification({ADDON_NAME},Stream health: {stream_health_status(live_stream_id)},2500)'))
    if play_url:
        if fav_is_saved(play_url):
            context_items.append(("Remove from Bang TV favourites", f'RunPlugin({build_url({"mode": "fav_remove_token", "id": token})})'))
        else:
            context_items.append(("Add to Bang TV favourites", f'RunPlugin({build_url({"mode": "fav_add_token", "name": name, "id": token, "thumb": thumb})})'))
    # Replace custom/global context items where Kodi allows it. External context add-ons may still add
    # their own entries, but the direct stream URL is hidden behind Bang TV's play route.
    li.addContextMenuItems(context_items, replaceItems=True)
    xbmcplugin.addDirectoryItem(HANDLE, plugin_play_url, li, False)


def sorted_items(items: Iterable[Dict[str, Any]], name_key: str = "name") -> List[Dict[str, Any]]:
    return sorted(list(items), key=lambda i: (i.get(name_key) or i.get("category_name") or "").lower())




def xmltv_guide_data(epg_url: str, cache_key: str = "xtream_7day_guide") -> Dict[str, Any]:
    """Parse XMLTV into a 7 day guide map for TV Guide folders."""
    if not epg_url or not setting_bool("show_epg", True):
        return {"channels": {}, "programmes": {}}
    cached = metadata_cache_get("epg_guide", cache_key, ttl=EPG_TTL_SECONDS)
    if cached and isinstance(cached, dict):
        return cached
    raw = http_get_bytes(epg_url, timeout=35, use_cache=True, ttl=EPG_TTL_SECONDS, silent=True)
    if not raw:
        return {"channels": {}, "programmes": {}}
    try:
        if epg_url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    except Exception:
        pass
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        log(f"TV Guide XMLTV parse failed: {exc}", xbmc.LOGWARNING)
        return {"channels": {}, "programmes": {}}

    channels: Dict[str, List[str]] = {}
    for channel in root.findall("channel"):
        ch_id = channel.get("id") or ""
        if not ch_id:
            continue
        names = []
        for dn in channel.findall("display-name"):
            if dn.text and dn.text.strip():
                names.append(dn.text.strip())
        channels[ch_id] = names

    now_ts = int(time.time())
    end_ts = now_ts + 7 * 24 * 60 * 60
    programmes: Dict[str, List[Dict[str, Any]]] = {}
    for prog in root.findall("programme"):
        ch = prog.get("channel") or ""
        start = parse_xmltv_time(prog.get("start"))
        stop = parse_xmltv_time(prog.get("stop"))
        if not ch or start is None or stop is None:
            continue
        if stop < now_ts - 300 or start > end_ts:
            continue
        row = {
            "start": int(start),
            "stop": int(stop),
            "title": xml_text(prog, "title") or "Programme",
            "desc": xml_text(prog, "desc"),
            "category": xml_text(prog, "category"),
        }
        programmes.setdefault(ch, []).append(row)
    for rows in programmes.values():
        rows.sort(key=lambda r: int(r.get("start") or 0))
    result = {"channels": channels, "programmes": programmes, "updated": now_ts}
    if programmes:
        metadata_cache_set("epg_guide", cache_key, result)
    return result


def guide_match_ids(item: Dict[str, Any], guide: Dict[str, Any]) -> List[str]:
    channels = guide.get("channels") if isinstance(guide, dict) else {}
    if not isinstance(channels, dict):
        channels = {}
    name = item.get("name") or ""
    clean_name = re.sub(r"\b(FHD|HD|SD|UHD|4K|HEVC|H265|H264|1080P|720P)\b", "", str(name or ""), flags=re.I)
    clean_name = " ".join(clean_name.replace("|", " ").split())
    direct_candidates = [
        item.get("epg_channel_id"), item.get("tvg_id"), item.get("channel_id"), item.get("stream_id"), name, clean_name,
    ]
    matches: List[str] = []
    for cand in direct_candidates:
        if cand in (None, ""):
            continue
        text = str(cand)
        if text in channels and text not in matches:
            matches.append(text)
        ntext = norm_epg_key(text)
        for ch_id, names in channels.items():
            if norm_epg_key(ch_id) == ntext and ch_id not in matches:
                matches.append(ch_id)
            for dn in names or []:
                if norm_epg_key(dn) == ntext and ch_id not in matches:
                    matches.append(ch_id)
    return matches


def guide_programmes_for_item(item: Dict[str, Any], guide: Dict[str, Any]) -> List[Dict[str, Any]]:
    programmes = guide.get("programmes") if isinstance(guide, dict) else {}
    if not isinstance(programmes, dict):
        return []
    rows: List[Dict[str, Any]] = []
    for ch_id in guide_match_ids(item, guide):
        for row in programmes.get(ch_id, []) or []:
            if isinstance(row, dict):
                rows.append(row)
    rows.sort(key=lambda r: int(r.get("start") or 0))
    return rows


def guide_now_next_text(rows: List[Dict[str, Any]]) -> str:
    now_ts = int(time.time())
    current = None
    nxt = None
    for row in rows:
        start = int(row.get("start") or 0)
        stop = int(row.get("stop") or 0)
        if start <= now_ts <= stop:
            current = row
        elif start > now_ts and nxt is None:
            nxt = row
        if current and nxt:
            break
    lines: List[str] = []
    if current:
        lines.append(f"Now: {current.get('title') or 'Programme'} ({format_local_time(current.get('start'))} - {format_local_time(current.get('stop'))})")
        if current.get("desc"):
            lines.append(str(current.get("desc")))
    if nxt:
        if lines:
            lines.append("")
        lines.append(f"Next: {nxt.get('title') or 'Programme'} ({format_local_time(nxt.get('start'))})")
    return "\n".join(lines)



def m3u_escape(value: Any) -> str:
    return str(value or "").replace('"', "'").replace("\n", " ").strip()


def export_native_pvr_files(show_dialog: bool = True) -> bool:
    """Export a local M3U playlist and XMLTV setup note for Kodi IPTV Simple PVR."""
    if not has_saved_login():
        notify("Login needed first", icon=xbmcgui.NOTIFICATION_ERROR)
        return False
    progress = xbmcgui.DialogProgress()
    if show_dialog:
        progress.create("Bang TV Native Guide", "Preparing PVR-style TV guide files...")
    try:
        if show_dialog:
            progress.update(10, "Loading Live TV categories...")
        cats = http_get_json(xc_api_url("player_api.php?action=get_live_categories"), timeout=25, use_cache=False)
        cat_names: Dict[str, str] = {}
        if isinstance(cats, list):
            for cat in cats:
                cat_id = str(cat.get("category_id") or "")
                cat_names[cat_id] = str(cat.get("category_name") or "Live TV")
        if show_dialog:
            progress.update(35, "Loading latest Live TV channels...")
        streams = http_get_json(xc_api_url("player_api.php?action=get_live_streams"), timeout=45, use_cache=False)
        if not isinstance(streams, list) or not streams:
            if show_dialog:
                progress.close()
            notify("No Live TV channels found", icon=xbmcgui.NOTIFICATION_ERROR)
            return False
        user, pwd, _label = get_effective_creds()
        total = max(1, len(streams))
        lines = ["#EXTM3U x-tvg-url=\"{}\"".format(m3u_escape(xtream_xmltv_url()))]
        for idx, item in enumerate(streams):
            if show_dialog and idx % 250 == 0:
                progress.update(35 + int((idx / total) * 55), f"Writing channel {idx + 1} of {total}...")
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            name = m3u_escape(item.get("name") or "Unknown")
            logo = m3u_escape(item.get("stream_icon") or "")
            cat_id = str(item.get("category_id") or "")
            group = m3u_escape(cat_names.get(cat_id) or cat_id or "Live TV")
            tvg_id = m3u_escape(item.get("epg_channel_id") or item.get("tv_archive_id") or stream_id)
            url = f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{stream_id}.ts"
            lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}",{name}')
            lines.append(url)
        os.makedirs(PROFILE_PATH, exist_ok=True)
        with open(PVR_EXPORT_M3U_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        info = [
            "Bang TV Native PVR Guide Setup",
            "",
            "Use these with IPTV Simple Client if you want the real Kodi PVR grid guide:",
            "",
            "M3U playlist:",
            PVR_EXPORT_M3U_FILE,
            "",
            "XMLTV guide URL:",
            xtream_xmltv_url(),
            "",
            "After setting IPTV Simple Client, restart Kodi or reload PVR data, then open TV Guide again.",
        ]
        with open(PVR_EXPORT_INFO_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(info))
        if show_dialog:
            progress.update(100, "Done")
            progress.close()
            xbmcgui.Dialog().ok("Bang TV Native Guide", "Kodi's real PVR guide needs IPTV Simple Client.\n\nBang TV exported the files for it.\n\nM3U:\n{}\n\nXMLTV URL:\n{}\n\nAfter IPTV Simple is set up, this TV Guide button will open Kodi's native PVR guide.".format(PVR_EXPORT_M3U_FILE, xtream_xmltv_url()))
        return True
    except Exception as exc:
        try:
            if show_dialog:
                progress.close()
        except Exception:
            pass
        log(f"PVR export failed: {exc}", xbmc.LOGERROR)
        notify("Native guide export failed", icon=xbmcgui.NOTIFICATION_ERROR)
        return False


def open_native_tv_guide() -> None:
    """Deprecated wrapper kept for old shortcuts. The guide now stays inside Bang TV."""
    list_tv_guide_categories()



# -----------------------------------------------------------------------------
# In-add-on visual TV guide
# -----------------------------------------------------------------------------

def guide_time_label(ts: int) -> str:
    try:
        return time.strftime("%I:%M %p", time.localtime(int(ts))).lstrip("0")
    except Exception:
        return ""


def guide_current_program(rows: List[Dict[str, Any]], at_time: Optional[int] = None) -> Dict[str, Any]:
    now = int(at_time or time.time())
    for row in rows or []:
        try:
            if int(row.get("start") or 0) <= now < int(row.get("stop") or 0):
                return row
        except Exception:
            continue
    for row in rows or []:
        try:
            if int(row.get("stop") or 0) >= now:
                return row
        except Exception:
            continue
    return {}



def get_live_guide_categories_quick() -> List[Dict[str, str]]:
    """Return Live TV categories for the in-window guide category picker.

    Uses existing API cache first so the visual guide can open immediately and the
    category picker does not force a full directory reload.
    """
    out: List[Dict[str, str]] = [{"category_id": "", "category_name": "All Channels"}]
    try:
        url = xc_api_url("player_api.php?action=get_live_categories")
        data = get_cached_json_any_age(url)
        if data is None:
            data = http_get_json(url, timeout=15, use_cache=True, silent=True)
        if isinstance(data, list):
            for cat in sorted_items(data, "category_name"):
                cat_id = str(cat.get("category_id") or "")
                name = str(cat.get("category_name") or "Unknown")
                if cat_id and not hidden_live_is_hidden(cat_id):
                    out.append({"category_id": cat_id, "category_name": name})
    except Exception as exc:
        log(f"Guide category picker failed: {exc}", xbmc.LOGWARNING)
    return out



def guide_skin_safe_dimensions(win: Any) -> Tuple[int, int]:
    """Return safe guide dimensions for different Kodi skins and resolutions."""
    try:
        w = int(win.getWidth() or 0)
        h = int(win.getHeight() or 0)
    except Exception:
        w, h = 0, 0
    if w < 800 or h < 480:
        try:
            w = int(xbmc.getInfoLabel('System.ScreenWidth') or 0)
            h = int(xbmc.getInfoLabel('System.ScreenHeight') or 0)
        except Exception:
            w, h = 0, 0
    if w < 800 or h < 480:
        w, h = 1280, 720
    return w, h

def guide_font(name: str = 'font12') -> str:
    """Keep font use conservative so the custom guide works across skins."""
    return name or 'font12'

class BangTVGuideWindow(xbmcgui.WindowDialog):
    """A TiviMate/PVR-style visual guide rendered inside the add-on.

    v1.0.17 changes the guide from a full redraw model to persistent controls.
    Moving up/down or left/right now updates existing labels and the selected
    highlight only, instead of removing and rebuilding the whole window.
    """

    def __init__(self, channels: List[Dict[str, Any]], title: str = "TV Guide", categories: Optional[List[Dict[str, str]]] = None, cat_id: str = ""):
        super(BangTVGuideWindow, self).__init__()
        self.channels = channels or []
        self.title = title or "TV Guide"
        self.controls: List[Any] = []
        self.selected = 0
        self.offset = 0
        self.window_start = self._round_half_hour(int(time.time()))
        self.slot_minutes = 30
        self.visible_rows = 9
        self.visible_slots = 6
        self._closed_by_play = False
        self.categories = categories or []
        self.cat_id = str(cat_id or "")
        self.next_category_id = None
        self.next_category_title = None
        self._built = False
        self._layout = {}
        self._row_controls: List[Dict[str, Any]] = []
        self._slot_controls: List[Any] = []
        self._panel = {}
        self._time_labels: List[Any] = []
        self._selected_bar = None
        self._now_marker = None

    def _round_half_hour(self, ts: int) -> int:
        return ts - (ts % (30 * 60))

    def _add(self, control: Any) -> Any:
        self.addControl(control)
        self.controls.append(control)
        return control

    def _safe_set_label(self, control: Any, text: str) -> None:
        try:
            control.setLabel(text or "")
        except Exception:
            pass

    def _safe_set_image(self, control: Any, image: str) -> None:
        try:
            control.setImage(image or ADDON_ICON)
        except Exception:
            pass

    def _safe_set_visible(self, control: Any, visible: bool) -> None:
        try:
            control.setVisible(bool(visible))
        except Exception:
            pass

    def _safe_set_pos(self, control: Any, x: int, y: int, w: Optional[int] = None, h: Optional[int] = None) -> None:
        try:
            if w is not None and h is not None:
                control.setPosition(x, y)
                control.setWidth(w)
                control.setHeight(h)
            else:
                control.setPosition(x, y)
        except Exception:
            try:
                control.setPosition(x, y)
            except Exception:
                pass

    def _label(self, x: int, y: int, w: int, h: int, text: str, color: str = "0xFFFFFFFF", font: str = "font12", align: int = 0) -> Any:
        return self._add(xbmcgui.ControlLabel(x, y, w, h, text, font=font, textColor=color, alignment=align))

    def _image(self, x: int, y: int, w: int, h: int, img: str, color: Optional[str] = None) -> Any:
        if color:
            return self._add(xbmcgui.ControlImage(x, y, w, h, img or ADDON_ICON, colorDiffuse=color))
        return self._add(xbmcgui.ControlImage(x, y, w, h, img or ADDON_ICON))

    def onInit(self):
        self._build_once()
        self._update_all()

    def _build_once(self) -> None:
        if self._built:
            return
        w, h = guide_skin_safe_dimensions(self)
        panel_h = max(128, min(190, int(h * 0.26)))
        y0 = panel_h
        time_h = max(32, int(h * 0.052))
        row_h = max(38, min(52, int((h - y0 - time_h - 10) / 9)))
        self.visible_rows = max(5, min(12, int((h - y0 - time_h - 10) / row_h)))
        self.visible_slots = 5 if w < 1100 else 6
        idx_w = max(34, int(w * 0.035))
        chan_w = max(205, min(310, int(w * 0.235)))
        grid_x = idx_w + chan_w
        grid_w = max(360, w - grid_x - 18)
        slot_w = max(90, int(grid_w / float(self.visible_slots)))
        self._layout = {"w": w, "h": h, "y0": y0, "time_h": time_h, "row_h": row_h, "idx_w": idx_w, "chan_w": chan_w, "grid_x": grid_x, "grid_w": grid_w, "slot_w": slot_w}

        self._image(0, 0, w, y0, "special://home/addons/plugin.video.bangtv/icon.png", "0x88202A2E")
        self._panel["icon"] = self._image(16, 10, max(220, int(w * 0.28)), max(96, y0 - 28), ADDON_ICON)
        panel_x = max(260, int(w * 0.32))
        self._panel["title"] = self._label(panel_x, 18, w - panel_x - 25, 32, "", "0xFFFFFFFF", guide_font("font16"))
        self._panel["time"] = self._label(panel_x, 55, max(260, int(w * 0.36)), 26, "", "0xFFB8C0C4", guide_font("font12"))
        self._panel["cat"] = self._label(max(panel_x, w - 360), 55, 330, 26, "", "0xFFFFFFFF", guide_font("font12"), align=2)
        self._panel["desc"] = self._label(panel_x, 84, w - panel_x - 25, max(42, y0 - 102), "", "0xFFB8C0C4", guide_font("font12"))
        self._panel["help"] = self._label(max(panel_x, w - 430), 18, 400, 28, "OK Play  |  Left/Right Time  |  Menu Categories", "0xFFB8C0C4", guide_font("font10"), align=2)

        self._image(0, y0, w, h - y0, "special://home/addons/plugin.video.bangtv/icon.png", "0xDD142024")
        self._panel["date"] = self._label(16, y0 + 8, 220, 26, "", "0xFF8CCBFF", "font12")
        for i in range(self.visible_slots):
            x = grid_x + i * slot_w
            self._time_labels.append(self._label(x, y0 + 8, slot_w - 4, 26, "", "0xFFB8C0C4", "font12"))
        self._image(0, y0 + time_h - 1, w, 1, "special://home/addons/plugin.video.bangtv/icon.png", "0xFF62717A")

        # One movable selected overlay, this avoids changing every row background on navigation.
        self._selected_bar = self._image(0, y0 + time_h, w, row_h - 1, "special://home/addons/plugin.video.bangtv/icon.png", "0xAA1F5A82")

        for r in range(self.visible_rows):
            y = y0 + time_h + r * row_h
            bg = "0x99223039" if r % 2 == 0 else "0x9918252B"
            self._image(0, y, w, row_h - 1, "special://home/addons/plugin.video.bangtv/icon.png", bg)
            row = {
                "idx": self._label(16, y + 11, 30, 24, "", "0xFFFFFFFF", "font12"),
                "icon": self._image(52, y + 7, 48, 30, ADDON_ICON),
                "name": self._label(108, y + 10, chan_w - 70, 25, "", "0xFFFFFFFF", "font12"),
                "slots": []
            }
            for c in range(self.visible_slots):
                x = grid_x + c * slot_w
                cell_bg = self._image(x, y + 1, slot_w - 2, row_h - 3, "special://home/addons/plugin.video.bangtv/icon.png", "0x66304045")
                cell_label = self._label(x + 8, y + 12, slot_w - 14, 22, "", "0xFFB8C0C4", "font12")
                row["slots"].append((cell_bg, cell_label))
            self._row_controls.append(row)

        self._now_marker = self._image(grid_x, y0 + time_h, 2, self.visible_rows * row_h, "special://home/addons/plugin.video.bangtv/icon.png", "0xFF4AA3FF")
        self._built = True

    def _program_for_slot(self, rows: List[Dict[str, Any]], slot_start: int, slot_stop: int) -> Dict[str, Any]:
        best = {}
        best_overlap = 0
        for row in rows or []:
            try:
                start = int(row.get("start") or 0)
                stop = int(row.get("stop") or 0)
            except Exception:
                continue
            overlap = max(0, min(stop, slot_stop) - max(start, slot_start))
            if overlap > best_overlap:
                best = row
                best_overlap = overlap
        return best

    def _update_panel(self) -> None:
        channel = self.channels[self.selected] if self.channels else {}
        rows = channel.get("guide_rows") or []
        current = guide_current_program(rows, int(time.time()))
        icon = str(channel.get("stream_icon") or ADDON_ICON)
        prog_title = str(current.get("title") or "No current EPG")
        start = int(current.get("start") or 0)
        stop = int(current.get("stop") or 0)
        desc = str(current.get("desc") or "")
        cat = str(channel.get("category_name") or self.title or "Live TV")
        mins = max(0, int((stop - start) / 60)) if start and stop else 0
        time_line = f"{guide_time_label(start)} - {guide_time_label(stop)}        {mins} min" if start and stop else ""
        self._safe_set_image(self._panel.get("icon"), icon)
        self._safe_set_label(self._panel.get("title"), prog_title[:90])
        self._safe_set_label(self._panel.get("time"), time_line)
        self._safe_set_label(self._panel.get("cat"), cat[:42])
        self._safe_set_label(self._panel.get("desc"), desc[:260])

    def _update_time_header(self) -> None:
        now = int(time.time())
        self._safe_set_label(self._panel.get("date"), time.strftime("%a, %b %d, %I:%M %p", time.localtime(now)).replace(" 0", " "))
        for i, lbl in enumerate(self._time_labels):
            ts = self.window_start + i * self.slot_minutes * 60
            self._safe_set_label(lbl, guide_time_label(ts))
        lay = self._layout
        total_secs = self.visible_slots * self.slot_minutes * 60
        if self.window_start <= now <= self.window_start + total_secs:
            x = lay["grid_x"] + int(((now - self.window_start) / float(total_secs)) * lay["grid_w"])
            self._safe_set_pos(self._now_marker, x, lay["y0"] + lay["time_h"])
            self._safe_set_visible(self._now_marker, True)
        else:
            self._safe_set_visible(self._now_marker, False)

    def _update_selected_overlay(self) -> None:
        lay = self._layout
        visible_index = self.selected - self.offset
        y = lay["y0"] + lay["time_h"] + max(0, min(self.visible_rows - 1, visible_index)) * lay["row_h"]
        self._safe_set_pos(self._selected_bar, 0, y)

    def _update_rows(self) -> None:
        lay = self._layout
        slot_seconds = self.slot_minutes * 60
        for r, row_ctrl in enumerate(self._row_controls):
            absolute = self.offset + r
            if absolute >= len(self.channels):
                self._safe_set_label(row_ctrl["idx"], "")
                self._safe_set_label(row_ctrl["name"], "")
                self._safe_set_image(row_ctrl["icon"], "")
                for bg, lbl in row_ctrl["slots"]:
                    self._safe_set_label(lbl, "")
                    self._safe_set_visible(bg, False)
                continue
            channel = self.channels[absolute]
            self._safe_set_label(row_ctrl["idx"], str(absolute + 1))
            self._safe_set_image(row_ctrl["icon"], str(channel.get("stream_icon") or ADDON_ICON))
            self._safe_set_label(row_ctrl["name"], str(channel.get("name") or "Live TV")[:32])
            guide_rows = channel.get("guide_rows") or []
            for c, (bg, lbl) in enumerate(row_ctrl["slots"]):
                slot_start = self.window_start + c * slot_seconds
                slot_stop = slot_start + slot_seconds
                prog = self._program_for_slot(guide_rows, slot_start, slot_stop)
                title = str(prog.get("title") or "") if prog else ""
                self._safe_set_label(lbl, title[:26] if title else "")
                self._safe_set_visible(bg, bool(title))

    def _update_all(self) -> None:
        self._update_time_header()
        self._update_rows()
        self._update_selected_overlay()
        self._update_panel()

    def _move(self, delta: int) -> None:
        if not self.channels:
            return
        old_offset = self.offset
        self.selected = max(0, min(len(self.channels) - 1, self.selected + delta))
        if self.selected < self.offset:
            self.offset = self.selected
        if self.selected >= self.offset + self.visible_rows:
            self.offset = self.selected - self.visible_rows + 1
        if self.offset != old_offset:
            self._update_rows()
        self._update_selected_overlay()
        self._update_panel()

    def _shift_time(self, delta_slots: int) -> None:
        self.window_start += delta_slots * self.slot_minutes * 60
        min_start = self._round_half_hour(int(time.time()) - 60 * 60)
        max_start = self._round_half_hour(int(time.time()) + 7 * 24 * 60 * 60)
        self.window_start = max(min_start, min(max_start, self.window_start))
        self._update_time_header()
        self._update_rows()
        self._update_panel()

    def _choose_category(self) -> None:
        """Switch guide category without going back through plugin folders."""
        if not self.categories:
            notify("No categories available", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        labels = []
        current_index = 0
        for i, cat in enumerate(self.categories):
            name = str(cat.get("category_name") or "Live TV")
            cid = str(cat.get("category_id") or "")
            if cid == self.cat_id:
                current_index = i
                labels.append(f"[B]{name}[/B]")
            else:
                labels.append(name)
        idx = xbmcgui.Dialog().select("TV Guide Categories", labels, preselect=current_index)
        if idx < 0 or idx >= len(self.categories):
            return
        chosen = self.categories[idx]
        new_id = str(chosen.get("category_id") or "")
        new_title = str(chosen.get("category_name") or "TV Guide")
        if new_id == self.cat_id:
            return
        self.next_category_id = new_id
        self.next_category_title = new_title
        self.close()

    def _play_selected(self) -> None:
        if not self.channels:
            return
        channel = self.channels[self.selected]
        url = channel.get("play_url") or ""
        if not url:
            notify("No stream URL for this channel", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        recent_live_add(str(channel.get("name") or "Live TV"), channel.get("stream_id") or "", url, str(channel.get("stream_icon") or ""), str(channel.get("category_id") or ""), "", {"plot": "", "mediatype": "video"})
        stream_health_mark(channel.get("stream_id") or "", True)
        self._closed_by_play = True
        self.close()
        xbmc.Player().play(url)

    def onAction(self, action):
        aid = action.getId()
        if aid in (9, 10, 92):  # back/menu/escape
            self.close()
        elif aid in (7,):  # select
            self._play_selected()
        elif aid in (11, 117):  # info/context menu opens category picker
            self._choose_category()
        elif aid in (1,):  # left
            self._shift_time(-1)
        elif aid in (2,):  # right
            self._shift_time(1)
        elif aid in (3,):  # up
            self._move(-1)
        elif aid in (4,):  # down
            self._move(1)
        elif aid in (5,):  # page up
            self._move(-self.visible_rows)
        elif aid in (6,):  # page down
            self._move(self.visible_rows)


def get_cached_metadata_any_age(content_type: str, item_id: Any) -> Dict[str, Any]:
    """Read metadata cache without TTL so the TV Guide can open instantly.

    The visual guide should never block on downloading/parsing XMLTV before the
    window appears. Fresh guide rows can be filled by normal EPG/background
    cache later, but opening the frame must be instant.
    """
    if item_id in (None, ""):
        return {}
    try:
        key = metadata_cache_key(content_type, item_id)
        with metadata_db() as conn:
            row = conn.execute("SELECT data FROM metadata_cache WHERE cache_key=?", (key,)).fetchone()
        if not row:
            return {}
        data = json.loads(row[0] or "{}")
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"SQLite metadata any-age read failed: {exc}", xbmc.LOGWARNING)
        return {}


def build_fast_visual_guide_channels(cat_id: str = "", title: str = "TV Guide", limit: int = 450) -> List[Dict[str, Any]]:
    """Build the visual guide from already cached channel data only.

    v1.0.18: opening the TV Guide must not fetch server data or parse the full
    7 day XMLTV file. That caused the long wait before the guide appeared. This
    function creates a lightweight grid immediately from cached live streams,
    then uses any previously prepared programme rows if they already exist.
    """
    endpoint = "player_api.php?action=get_live_streams"
    if cat_id:
        endpoint += f"&category_id={quote(str(cat_id))}"
    url = xc_api_url(endpoint)
    data = get_cached_json_any_age(url)
    if data is None:
        # Last resort, a short cached API call. This is only for first ever guide
        # use when nothing exists yet. It still avoids XMLTV parsing.
        data = http_get_json(url, timeout=12, use_cache=True, silent=True)
    if not isinstance(data, list):
        data = []

    prepared = get_cached_metadata_any_age("visual_guide_ready", cat_id or "all")
    prepared_rows = {}
    try:
        for old in prepared.get("channels") or []:
            sid = str(old.get("stream_id") or "")
            if sid:
                prepared_rows[sid] = old.get("guide_rows") or []
    except Exception:
        prepared_rows = {}

    user, pwd, _label = get_effective_creds()
    out: List[Dict[str, Any]] = []
    for item in sorted_items(data)[:limit]:
        stream_id = item.get("stream_id")
        if stream_id is None:
            continue
        new_item = dict(item)
        sid = str(stream_id)
        new_item["guide_rows"] = prepared_rows.get(sid, [])
        new_item["play_url"] = f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{stream_id}.ts"
        if title and not new_item.get("category_name"):
            new_item["category_name"] = title
        out.append(new_item)
    return out


def open_visual_tv_guide(cat_id: str = "", title: str = "TV Guide") -> None:
    if not has_saved_login():
        notify("Login needed first", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    cat_id = str(cat_id or "")
    title = title or ("All Channels" if not cat_id else "TV Guide")
    try:
        categories = get_live_guide_categories_quick()
        out = build_fast_visual_guide_channels(cat_id, title)
        if not out:
            notify("Guide cache is empty. Open Live TV or press Refresh Live TV first.", icon=xbmcgui.NOTIFICATION_INFO)
            return

        # Save lightweight guide cache so the next open is instant too. Do not
        # force XMLTV parsing here, that belongs in background/update paths.
        metadata_cache_set("visual_guide_ready", cat_id or "all", {"channels": out, "title": title, "saved": int(time.time()), "fast_open": True})

        win = BangTVGuideWindow(out, title or "TV Guide", categories=categories, cat_id=cat_id)
        win.doModal()
        next_id = win.next_category_id
        next_title = win.next_category_title
        del win
        if next_id is not None:
            open_visual_tv_guide(next_id, next_title or "TV Guide")
    except Exception as exc:
        log(f"Visual TV guide failed, falling back to folder guide: {exc}", xbmc.LOGERROR)
        notify("Visual guide fallback mode", icon=xbmcgui.NOTIFICATION_INFO)
        try:
            list_tv_guide_channels(cat_id, title or "TV Guide")
        except Exception:
            notify("TV Guide could not open", icon=xbmcgui.NOTIFICATION_ERROR)


def list_tv_guide_categories() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "TV Guide")
    xbmcplugin.setContent(HANDLE, "videos")
    add_action("[B]All Channels Guide[/B]", "tv_guide_category", {"cat_id": "", "title": "All Channels"}, plot="Open the skin-safe guide view using normal Kodi controls. Works on all skins.")
    add_action("Visual Grid Guide (experimental)", "tv_guide_visual", {"cat_id": "", "title": "All Channels"}, plot="Experimental custom visual guide. If your skin does not show it properly, use the normal TV Guide above.")
    data = http_get_json_with_progress(xc_api_url("player_api.php?action=get_live_categories"), "Loading TV Guide categories...", timeout=25)
    if isinstance(data, list):
        for cat in sorted_items(data, "category_name"):
            name = cat.get("category_name") or "Unknown"
            cat_id = str(cat.get("category_id") or "")
            if cat_id and not hidden_live_is_hidden(cat_id):
                add_action(name, "tv_guide_category", {"cat_id": cat_id, "title": name}, plot="Open this category in the skin-safe TV Guide.")
    xbmcplugin.endOfDirectory(HANDLE)



def tv_guide_grid_label(channel_name: str, rows: List[Dict[str, Any]]) -> str:
    """Build a PVR/TiviMate-inspired row label that stays inside Kodi plugin lists."""
    now = int(time.time())
    upcoming = []
    for row in rows or []:
        start = int(row.get("start") or 0)
        stop = int(row.get("stop") or 0)
        if stop >= now:
            upcoming.append(row)
        if len(upcoming) >= 3:
            break
    def fmt(row: Dict[str, Any], fallback: str) -> str:
        if not row:
            return fallback
        start = int(row.get("start") or 0)
        title = str(row.get("title") or "Programme")
        return f"{format_local_time(start)} {title}"
    col1 = fmt(upcoming[0], "No current EPG") if len(upcoming) > 0 else "No current EPG"
    col2 = fmt(upcoming[1], "No next EPG") if len(upcoming) > 1 else "No next EPG"
    col3 = fmt(upcoming[2], "") if len(upcoming) > 2 else ""
    return f"[B]{channel_name}[/B]   |   {col1}   |   {col2}" + (f"   |   {col3}" if col3 else "")


def tv_guide_grid_plot(channel_name: str, rows: List[Dict[str, Any]]) -> str:
    lines = [channel_name, "", "TV Guide row layout:", "Channel | Now | Next | Later", ""]
    if not rows:
        lines.append("No XMLTV 7 day guide data found for this channel yet.")
        return "\n".join(lines)
    last_day = ""
    for row in rows[:20]:
        start = int(row.get("start") or 0)
        stop = int(row.get("stop") or 0)
        day = time.strftime("%A %d %b", time.localtime(start))
        if day != last_day:
            lines.append(day)
            last_day = day
        lines.append(f"  {format_local_time(start)} - {format_local_time(stop)}  {row.get('title') or 'Programme'}")
    return "\n".join(lines)

def list_tv_guide_channels(cat_id: str = "", title: str = "TV Guide", page: int = 1) -> None:
    xbmcplugin.setPluginCategory(HANDLE, "TV Guide - " + (title or "Live TV"))
    xbmcplugin.setContent(HANDLE, "videos")
    endpoint = "player_api.php?action=get_live_streams"
    if cat_id:
        endpoint += f"&category_id={quote(cat_id)}"
    url = xc_api_url(endpoint)
    data = get_cached_json_any_age(url)
    if data is None:
        data = http_get_json_with_progress(url, "Loading TV Guide channels...", timeout=30, force_refresh=False)
    if not isinstance(data, list) or not data:
        add_action("No TV Guide channels found", "tv_guide")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    guide = xmltv_guide_data(xtream_xmltv_url(), "xtream_7day_guide")
    all_items = sorted_items(data)
    page = safe_page(page)
    items, has_next = paged_items(all_items, page)
    user, pwd, _label = get_effective_creds()
    for item in items:
        stream_id = item.get("stream_id")
        if stream_id is None:
            continue
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or ADDON_ICON
        rows = guide_programmes_for_item(item, guide)
        plot = tv_guide_grid_plot(name, rows)
        label = tv_guide_grid_label(name, rows)
        context = [("Play Channel", f'RunPlugin({build_url({"mode": "play", "id": save_play_link(f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{stream_id}.ts"), "live_id": str(stream_id), "name": name, "thumb": icon, "cat_id": cat_id, "epg_plot": plot[:1500]})})')]
        add_folder(label, "tv_guide_channel", {"stream_id": stream_id, "cat_id": cat_id, "title": name, "thumb": icon}, icon, plot, context_items=context)
    if has_next:
        add_folder(f"Next page ({page + 1})", "tv_guide_category", {"cat_id": cat_id, "title": title or "TV Guide", "page": page + 1}, ADDON_ICON, "Show the next page of TV Guide channels.")
    xbmcplugin.endOfDirectory(HANDLE)


def list_tv_guide_channel(stream_id: Any, cat_id: str = "", title: str = "Live TV", thumb: str = "") -> None:
    xbmcplugin.setPluginCategory(HANDLE, "TV Guide - " + (title or "Live TV"))
    xbmcplugin.setContent(HANDLE, "videos")
    user, pwd, _label = get_effective_creds()
    stream_id_text = str(stream_id or "")
    if not stream_id_text:
        add_action("No channel selected", "tv_guide")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    play = f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{stream_id_text}.ts"
    guide = xmltv_guide_data(xtream_xmltv_url(), "xtream_7day_guide")
    item = {"stream_id": stream_id_text, "name": title}
    # Add richer matching data from the cached channel row when possible.
    endpoint = "player_api.php?action=get_live_streams"
    if cat_id:
        endpoint += f"&category_id={quote(cat_id)}"
    cached = get_cached_json_any_age(xc_api_url(endpoint))
    if isinstance(cached, list):
        for row in cached:
            if str(row.get("stream_id") or "") == stream_id_text:
                item.update(row)
                thumb = thumb or row.get("stream_icon") or ""
                break
    rows = guide_programmes_for_item(item, guide)
    now_plot = guide_now_next_text(rows)
    add_playable("▶ Play Channel Now", play, thumb or ADDON_ICON, now_plot or "Play this Live TV channel.", None, {"plot": now_plot or "Play this Live TV channel.", "mediatype": "video"}, live_stream_id=stream_id_text, live_category_id=cat_id)
    if not rows:
        short = live_epg(stream_id_text)
        if short.get("plot"):
            add_action("Current EPG", "tv_guide_channel", {"stream_id": stream_id_text, "cat_id": cat_id, "title": title, "thumb": thumb}, thumb or ADDON_ICON, short.get("plot") or "")
        else:
            add_action("No 7 day EPG found for this channel", "tv_guide", plot="The provider has not supplied XMLTV guide data for this channel yet.")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    last_day = ""
    for row in rows:
        start = int(row.get("start") or 0)
        stop = int(row.get("stop") or 0)
        day = time.strftime("%A %d %b", time.localtime(start))
        prefix = ""
        if day != last_day:
            prefix = f"[B]{day}[/B] - "
            last_day = day
        label = f"{prefix}{format_local_time(start)} - {format_local_time(stop)}  {row.get('title') or 'Programme'}"
        plot_lines = [label.replace("[B]", "").replace("[/B]", "")]
        if row.get("category"):
            plot_lines.append("Category: " + str(row.get("category")))
        if row.get("desc"):
            plot_lines.append("")
            plot_lines.append(str(row.get("desc")))
        add_action(label, "tv_guide_channel", {"stream_id": stream_id_text, "cat_id": cat_id, "title": title, "thumb": thumb}, thumb or ADDON_ICON, "\n".join(plot_lines))
    xbmcplugin.endOfDirectory(HANDLE)

def list_nz_streams() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "New Zealand Streams")
    xbmcplugin.setContent(HANDLE, "videos")
    channels, epg_url = nz_m3u_data()
    if not channels:
        add_action("No New Zealand streams found", "live_categories", plot="Could not load the New Zealand public streams list at the moment.")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    epg = nz_epg_map(epg_url)
    for item in channels:
        name = item.get("name") or "Unknown"
        logo = item.get("logo") or ADDON_ICON
        tvg_id = item.get("tvg_id") or item.get("channel_id") or name
        plot = epg.get(tvg_id, {}).get("plot") or "New Zealand stream from i.mjh.nz with channel logo and XMLTV EPG where available. EPG times are shown in your Kodi local timezone."
        meta = {"plot": plot, "genre": item.get("group") or "Nz", "mediatype": "video"}
        add_playable(name, nz_play_url(item), logo, plot, None, meta, "")
    xbmcplugin.endOfDirectory(HANDLE)

def list_categories(action: str, next_mode: str, title: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, title)
    xbmcplugin.setContent(HANDLE, "videos")
    url = xc_api_url(f"player_api.php?action={action}")
    if action == "get_live_categories":
        maybe_start_live_background_check()
        data = http_get_json_with_progress(url, "Loading Live TV categories...", timeout=25)
    else:
        data = http_get_json(url)
    if not isinstance(data, list) or not data:
        add_action("No categories found", "main")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    if action == "get_live_categories":
        add_action("Live TV Stats", "live_stats", plot="Show last update, next check, changed channels, changed categories and cache status.")
        add_action("Refresh Live TV", "live_refresh", plot="Force Bang TV to get the latest Live TV categories, channels and EPG from the server.")
        add_folder("Recently Watched", "recent_live", plot="Open recent Live TV channels.")
        add_folder("Hidden Categories", "hidden_live", plot="Restore Live TV categories you have hidden.")
        add_folder("New Zealand Streams", "nz_streams", plot="Official free-to-air New Zealand streams.\nGeo-blocked to New Zealand.")
    if action == "get_vod_categories":
        add_folder("Recently Added Movies", "recent_vod")
    for cat in sorted_items(data, "category_name"):
        name = cat.get("category_name") or "Unknown"
        cat_id = str(cat.get("category_id") or "")
        if cat_id:
            if action == "get_live_categories" and hidden_live_is_hidden(cat_id):
                continue
            context_items = []
            if action == "get_live_categories":
                context_items.append(("Update Category", f'Container.Update({build_url({"mode": "live_refresh_category", "cat_id": cat_id, "title": name})})'))
                context_items.append(("Hide Category", f'RunPlugin({build_url({"mode": "live_category_hide", "cat_id": cat_id, "title": name})})'))
                if fav_category_is_saved("live", cat_id):
                    context_items.append(("Remove category from Bang TV favourites", f'RunPlugin({build_url({"mode": "fav_category_remove", "content_type": "live", "cat_id": cat_id})})'))
                else:
                    context_items.append(("Add category to Bang TV favourites", f'RunPlugin({build_url({"mode": "fav_category_add", "name": name, "content_type": "live", "cat_id": cat_id})})'))
            add_folder(name, next_mode, {"cat_id": cat_id}, context_items=context_items)
    xbmcplugin.endOfDirectory(HANDLE)


def list_streams(content_type: str, cat_id: str = "", title: str = "", page: int = 1) -> None:
    xbmcplugin.setPluginCategory(HANDLE, title or "Bang TV")
    if content_type == "vod":
        xbmcplugin.setContent(HANDLE, "movies")
    elif content_type == "series":
        xbmcplugin.setContent(HANDLE, "tvshows")
    else:
        xbmcplugin.setContent(HANDLE, "videos")
    if content_type == "live":
        endpoint = f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}"
    elif content_type == "vod":
        endpoint = f"player_api.php?action=get_vod_streams&category_id={quote(cat_id)}"
    else:
        endpoint = f"player_api.php?action=get_series&category_id={quote(cat_id)}"

    url = xc_api_url(endpoint)
    if content_type == "live":
        mark_live_category_opened(cat_id, title or "Live TV")
        # For Live TV categories, show saved channels immediately even when the cache is old.
        # The background service refreshes and compares the folder after opening/after playback,
        # so returning from a long watch can show newly added streams without blocking the UI.
        data = get_cached_json_any_age(url)
        if data is None:
            data = http_get_json_with_progress(url, "Loading Live TV channels...", timeout=25, force_refresh=True)
    else:
        data = http_get_json(url)
    if not isinstance(data, list) or not data:
        add_action("Nothing found", "main")
        xbmcplugin.endOfDirectory(HANDLE)
        return

    all_items = sorted_items(data)
    page = safe_page(page)
    items, has_next = paged_items(all_items, page)
    preview_meta: Dict[str, Dict[str, Any]] = {}
    live_xmltv_epg: Dict[str, Dict[str, str]] = {}
    if content_type == "vod":
        preview_meta = batch_preview_metadata("vod", [item.get("stream_id") for item in items], PAGE_SIZE)
    elif content_type == "series":
        preview_meta = batch_preview_metadata("series", [item.get("series_id") for item in items], PAGE_SIZE)
    elif content_type == "live":
        live_xmltv_epg = xmltv_epg_map(xtream_xmltv_url(), "xtream_live")

    user, pwd, _label = get_effective_creds()
    for item in items:
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
        plot = item.get("plot") or item.get("description") or ""
        year = item.get("year") or item.get("releaseDate") or None
        if content_type == "live":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            # Prefer the same XMLTV Now/Next method used by New Zealand Streams because it works
            # consistently in more Kodi skins/themes. Fall back to Xtream short EPG if XMLTV has no match.
            epg = live_item_epg_from_map(item, live_xmltv_epg) or live_epg(stream_id)
            live_meta = dict(item)
            live_meta["plot"] = epg.get("plot") or plot
            live_meta["mediatype"] = "video"
            health = stream_health_status(stream_id)
            extra_plot = (epg.get("plot") or plot or "")
            if health != "Unknown":
                extra_plot = (extra_plot + "\n\n" if extra_plot else "") + "Stream health: " + health
            add_playable(name, f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{stream_id}.ts", icon, extra_plot, year, live_meta, live_stream_id=stream_id, live_category_id=cat_id)
        elif content_type == "vod":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            ext = item.get("container_extension") or "mp4"
            if full_metadata_on_browse():
                meta = vod_info(stream_id)
            else:
                meta = preview_meta.get(str(stream_id), {})
            merged = dict(item)
            merged.update(meta)
            merged["mediatype"] = "movie"
            icon2 = best_image(meta.get("movie_image"), meta.get("cover_big"), meta.get("cover"), item.get("stream_icon"), icon)
            fanart = best_image(meta.get("backdrop_path"), meta.get("backdrop"), meta.get("background"), item.get("backdrop_path"), item.get("backdrop"))
            add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{stream_id}.{ext}", icon2, merged.get("plot") or merged.get("description") or plot, year, merged, fanart, "vod", stream_id)
        else:
            series_id = str(item.get("series_id") or "")
            if not series_id:
                continue
            if full_metadata_on_browse():
                meta = series_info(series_id)
            else:
                meta = preview_meta.get(str(series_id), {})
            merged = dict(item)
            merged.update(meta)
            merged["mediatype"] = "tvshow"
            icon2 = best_image(meta.get("cover"), meta.get("cover_big"), item.get("cover"), item.get("cover_big"), icon)
            fanart = best_image(meta.get("backdrop_path"), meta.get("backdrop"), meta.get("background"), item.get("backdrop_path"), item.get("backdrop"))
            li = xbmcgui.ListItem(label=name)
            set_art(li, icon2, fanart)
            set_video_info(li, name, merged.get("plot") or merged.get("description") or plot, year, merged)
            add_trailer_context(li, merged, "series", series_id)
            li.addContextMenuItems([], replaceItems=True)
            xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_seasons", "series_id": series_id}), li, True)
    if has_next:
        add_folder(f"Next page ({page + 1})", f"{content_type}_streams" if content_type == "vod" else ("series_list" if content_type == "series" else "live_streams"), {"cat_id": cat_id, "page": page + 1}, ADDON_ICON, "Show the next page of results.")
    xbmcplugin.endOfDirectory(HANDLE)


def list_recent_vod(page: int = 1) -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Recently Added Movies")
    xbmcplugin.setContent(HANDLE, "movies")
    data = http_get_json(xc_api_url("player_api.php?action=get_vod_streams"))
    if not isinstance(data, list):
        data = []
    user, pwd, _label = get_effective_creds()
    recent_all = sorted(data, key=lambda i: safe_int(i.get("added")), reverse=True)[:300]
    page = safe_page(page)
    recent, has_next = paged_items(recent_all, page)
    preview_meta = batch_preview_metadata("vod", [item.get("stream_id") for item in recent], PAGE_SIZE)
    for item in recent:
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or ""
        ext = item.get("container_extension") or "mp4"
        stream_id = item.get("stream_id")
        if stream_id is not None:
            meta = vod_info(stream_id) if full_metadata_on_browse() else preview_meta.get(str(stream_id), {})
            merged = dict(item)
            merged.update(meta)
            merged["mediatype"] = "movie"
            icon2 = best_image(meta.get("movie_image"), meta.get("cover_big"), meta.get("cover"), item.get("stream_icon"), icon)
            fanart = best_image(meta.get("backdrop_path"), meta.get("backdrop"), meta.get("background"), item.get("backdrop_path"), item.get("backdrop"))
            add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{stream_id}.{ext}", icon2, merged.get("plot") or merged.get("description") or item.get("plot") or "", merged.get("year") or item.get("year"), merged, fanart, "vod", stream_id)
    if has_next:
        add_folder(f"Next page ({page + 1})", "recent_vod", {"page": page + 1}, ADDON_ICON, "Show the next page of recently added movies.")
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
        set_art(li, season.get("cover") or cover, best_image(info.get("backdrop_path"), info.get("backdrop")))
        set_video_info(li, label, info.get("plot") or "", None, info)
        add_trailer_context(li, info, "series", series_id)
        # Ensure only Bang TV context menu items appear on season folders.
        if not meta_trailer(info):
            li.addContextMenuItems([], replaceItems=True)
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
    show_info = data.get("info") if isinstance(data.get("info"), dict) else {}
    show_fanart = best_image(show_info.get("backdrop_path"), show_info.get("backdrop"), show_info.get("background"))
    show_cover = best_image(show_info.get("cover"), show_info.get("cover_big"), show_info.get("movie_image"))
    progress = None
    if episodes:
        progress = xbmcgui.DialogProgress()
        try:
            progress.create(ADDON_NAME, "Loading episode metadata...")
        except Exception:
            progress = None
    for ep_index, ep in enumerate(episodes, start=1):
        if progress:
            if progress.iscanceled():
                break
            progress.update(int((ep_index - 1) * 100 / max(len(episodes), 1)), f"Loading episode metadata, episode {ep_index} of {len(episodes)}")
        title = ep.get("title") or ep.get("name") or "Episode"
        ep_num = ep.get("episode_num") or ep.get("episode")
        label = f"{ep_num}. {title}" if ep_num not in (None, "") else title
        ep_id = ep.get("id") or ep.get("episode_id")
        if not ep_id:
            continue
        info = ep.get("info") if isinstance(ep.get("info"), dict) else {}
        merged = dict(show_info)
        merged.update(info)
        merged.update({
            "title": title,
            "name": title,
            "mediatype": "episode",
            "season": safe_int(season_num),
            "episode": safe_int(ep_num),
            "episode_num": safe_int(ep_num),
            "plot": info.get("plot") or info.get("description") or ep.get("plot") or ep.get("description") or show_info.get("plot") or show_info.get("description") or "",
            "year": info.get("year") or show_info.get("year") or "",
            "releasedate": info.get("releasedate") or info.get("releaseDate") or info.get("air_date") or "",
        })
        metadata_cache_set("episode", ep_id, merged)
        thumb = best_image(info.get("movie_image"), info.get("cover_big"), info.get("cover"), ep.get("stream_icon"), show_cover)
        fanart = best_image(info.get("backdrop_path"), info.get("backdrop"), show_fanart)
        ext = ep.get("container_extension") or "mp4"
        add_playable(label, f"{SERVER}/series/{quote(user)}/{quote(pwd)}/{ep_id}.{ext}", thumb, merged.get("plot") or "", merged.get("year"), merged, fanart, "series", series_id)
    if progress:
        try:
            progress.update(100, "Loading episode metadata, done")
            progress.close()
        except Exception:
            pass
    xbmcplugin.endOfDirectory(HANDLE)


def favourites_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Favourites")
    xbmcplugin.setContent(HANDLE, "videos")
    items = fav_load()
    if not items:
        add_action("No favourites yet", "main")
    else:
        for item in items:
            if item.get("type") == "category":
                content_type = item.get("content_type") or "live"
                cat_id = item.get("cat_id") or ""
                if content_type == "live" and cat_id:
                    context_items = [
                        ("Update Category", f'Container.Update({build_url({"mode": "live_refresh_category", "cat_id": cat_id, "title": item.get("name") or "Live TV"})})'),
                        ("Remove category from Bang TV favourites", f'RunPlugin({build_url({"mode": "fav_category_remove", "content_type": "live", "cat_id": cat_id})})'),
                    ]
                    add_folder(item.get("name") or "Live TV Category", "live_streams", {"cat_id": cat_id}, item.get("thumb") or "", "Favourite Live TV category", context_items=context_items)
                continue
            add_playable(item.get("name") or "Unknown", item.get("url") or "", item.get("thumb") or "")
        add_action("Clear all favourites", "clear_favourites")
    xbmcplugin.endOfDirectory(HANDLE)


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    # Keep matching simple and reliable for channel names like
    # "Sky Sport 1", "SKY Sports News", "Sky-Sport-Select".
    for char in "._-:/\\|()[]{}+,&'\"":
        text = text.replace(char, " ")
    return " ".join(text.split())


def item_search_text(item: Dict[str, Any]) -> str:
    parts: List[str] = []
    keys = (
        "name", "title", "category_name", "plot", "description", "year",
        "releaseDate", "director", "cast", "genre", "rating", "tmdb_id",
        "stream_id", "series_id", "num", "container_extension"
    )
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    info = item.get("info")
    if isinstance(info, dict):
        for value in info.values():
            if isinstance(value, (str, int, float)) and value not in (None, ""):
                parts.append(str(value))
    return normalize_text(" ".join(parts))


def matches_term(item: Dict[str, Any], term: str) -> bool:
    query = normalize_text(term)
    words = [w for w in query.split() if w]
    if not words:
        return False
    text = item_search_text(item)
    # Exact phrase first, then all words anywhere. This makes
    # "sky sport" match "Sky Sport 1" and related channel names.
    return query in text or all(word in text for word in words)


def add_search_result(label: str, kind: str, item: Dict[str, Any], user: str, pwd: str) -> bool:
    raw_name = item.get("name") or item.get("title") or "Unknown"
    name = f"{label}: {raw_name}"
    icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
    plot = item.get("plot") or item.get("description") or ""
    year = item.get("year") or item.get("releaseDate") or None
    if kind == "live" and item.get("stream_id") is not None:
        add_playable(name, f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.ts", icon, plot, year)
        return True
    if kind == "vod" and item.get("stream_id") is not None:
        ext = item.get("container_extension") or "mp4"
        add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.{ext}", icon, plot, year)
        return True
    if kind == "series" and item.get("series_id"):
        li = xbmcgui.ListItem(label=name)
        set_art(li, icon)
        set_video_info(li, name, plot, year)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_seasons", "series_id": str(item.get("series_id"))}), li, True)
        return True
    return False


def search_menu(kind_filter: str = "all") -> None:
    term = xbmcgui.Dialog().input("Search Bang TV", type=xbmcgui.INPUT_ALPHANUM).strip()
    if not term:
        xbmcplugin.endOfDirectory(HANDLE)
        return

    xbmcplugin.setPluginCategory(HANDLE, f"Search: {term}")
    xbmcplugin.setContent(HANDLE, "videos")
    user, pwd, _label = get_effective_creds()
    all_sources = [
        ("Live", "player_api.php?action=get_live_streams", "live"),
        ("Movies", "player_api.php?action=get_vod_streams", "vod"),
        ("Series", "player_api.php?action=get_series", "series"),
    ]
    sources = [source for source in all_sources if kind_filter in ("all", source[2])]
    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, "Searching...")
    found = 0

    try:
        for index, (label, endpoint, kind) in enumerate(sources):
            if progress.iscanceled():
                break
            progress.update(int((index / max(len(sources), 1)) * 100), f"Searching {label}...")
            data = http_get_json(xc_api_url(endpoint), use_cache=False)
            if not isinstance(data, list):
                continue
            matches = [item for item in data if isinstance(item, dict) and matches_term(item, term)]
            for item in sorted_items(matches)[:120]:
                if add_search_result(label, kind, item, user, pwd):
                    found += 1
        progress.update(100, "Done")
    finally:
        progress.close()

    if found == 0:
        add_action(f"No results for: {term}", "main")
        add_action("Tip: try one word only, like Batman, News, Sport, or 2025", "main")
        notify("No search results found")
    xbmcplugin.endOfDirectory(HANDLE)


def search_type_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Search")
    # These must be folders, not plain action items. On some Kodi builds,
    # non-playable action items do not open the keyboard/search route.
    add_folder("Search Everything", "search_all")
    add_folder("Search Live TV Channels", "search_live")
    add_folder("Search Movies", "search_vod")
    add_folder("Search Series", "search_series")
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
    add_action("Account status", "account_status", plot="Shows your IPTV account status, expiry date and connection limits.")
    add_action("Test connection", "connection_test", plot="Checks that Bang TV can connect to the Xtream Codes server with your saved login.")
    add_action("Live TV Help", "live_help", plot="Explains Live TV cache, background updates, High Activity Mode, Refresh Live TV and Update Category.")
    add_action("Server Dashboard", "live_dashboard", plot="Shows server, cache, update, change and High Activity Mode status.")
    add_folder("Bang TV TV Guide", "tv_guide", plot="Opens the add-on TV Guide. This stays inside Bang TV and uses a grid-style Channel | Now | Next | Later layout.")
    add_action("Auto cleanup now", "auto_cleanup", plot="Removes old cache records, old health records and trims recent channel history.")
    add_action("Backup Bang TV settings", "backup_settings", plot="Backs up favourites, hidden categories, recent channels and Live TV update state.")
    add_action("Restore Bang TV settings", "restore_settings", plot="Restores the saved Bang TV user backup if one exists.")
    add_folder("Cache", "cache_menu", plot="View cache size, clear cached metadata, clear EPG data, and rebuild Bang TV databases.")
    add_action("Clear favourites", "clear_favourites", plot="Removes all saved Bang TV favourites. Your login and cache are not affected.")
    add_action("Settings", "open_settings", plot="Open Bang TV settings for login, metadata, preview and add-on options.")
    add_action("Logout", "logout", plot="Logs out of Bang TV and removes your saved IPTV username and password.")
    xbmcplugin.endOfDirectory(HANDLE)



def live_update_help() -> None:
    text = """Bang TV Live TV Help

Speed and cache

Live TV categories now try to open from saved cache first. This means a category should load faster after it has been opened once. If the folder still feels slow, it usually means Kodi is building the visible channel list, loading logos, EPG now/next data, or that the category has not been cached yet.

How background updates work

When you open Live TV, Bang TV marks Live TV as recently used. The background service then checks the playlist without blocking browsing. It compares the latest server playlist with the saved cache, using category IDs and stream IDs first, then names as a backup.

Normal update timing

Main Live TV category list: about every 30 minutes while Live TV is being used, otherwise less often.

Live TV category channels: about every 30 minutes for recently opened folders.

Active or recently changed category: about every 10 minutes.

Manual Refresh Live TV: anytime from the main Live TV screen.

Update Category: anytime from a category context menu.

High Activity Mode

High Activity Mode turns on when Bang TV notices lots of playlist movement, such as new channels, removed channels, renamed streams, changed logos, changed stream URLs, or a big channel count change.

When this happens, Bang TV checks changed or active categories more often for a while, so sports, match day, event, and temporary live streams are picked up faster. If things stop changing, it goes back to normal checking.

After watching TV for a long time

Playback is not interrupted. While you are watching, Bang TV can still keep update state in the background. When you stop playback or go back into a Live TV category, the add-on can show the cached folder quickly, then refresh the folder if the server has newer channels.

Live TV Stats

The Live TV Stats button shows last update time, last server check, next check, cached categories, total cached channels, active category update info, new channels, removed channels, changed channels, and whether High Activity Mode is on.

Best buttons to use

Use Refresh Live TV when the whole playlist looks old.

Use Update Category when only one folder needs a fresh update.

Use Live TV Stats when you want to check when the add-on last updated itself.

Recently Watched, hidden categories, health and backups

Recently Watched keeps your last 50 Live TV channels so you can jump back quickly. Hidden Categories lets you remove folders you never use from the main Live TV list and restore them later. Stream Health marks channels as working after playback and keeps a small local health history. Backup saves favourites, hidden categories, recent channels and update state into your Kodi profile.

Scheduled refresh

The background service checks Live TV roughly every 30 minutes while Live TV is being used, every 10 minutes in High Activity Mode, and backs off when you are not using Live TV. The manual Refresh Live TV and Update Category buttons still force an immediate update.
"""
    xbmcgui.Dialog().textviewer("Live TV Help", text)

def cache_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Tools / Cache")
    add_action("Cache statistics", "cache_action", {"action": "stats"}, plot="Shows the current size of the Bang TV API and SQLite metadata cache.")
    add_action("Build full metadata cache", "cache_action", {"action": "build_full"}, plot="Queues all Movies, TV Shows, seasons and episodes for background metadata caching. This can take a while, but browsing stays usable.")
    add_action("Clear metadata cache", "cache_action", {"action": "metadata"}, plot="Clears cached movie, TV show and episode descriptions, cast, genre, fanart and ratings.")
    add_action("Clear artwork cache", "cache_action", {"action": "artwork"}, plot="Clears cached poster and fanart records. Artwork will be refreshed when needed.")
    add_action("Clear EPG cache", "cache_action", {"action": "epg"}, plot="Clears cached Live TV guide data so the EPG can refresh from Xtream Codes.")
    add_action("Clear API cache", "cache_action", {"action": "api"}, plot="Clears temporary Xtream API responses. This can help if categories or lists look stale.")
    add_action("Clear all cache", "cache_action", {"action": "all"}, plot="Clears metadata, artwork, EPG and API cache. Login, settings and favourites are kept.")
    add_action("Rebuild databases", "cache_action", {"action": "rebuild"}, plot="Recreates Bang TV SQLite cache databases. Use this if metadata or cache looks corrupted.")
    xbmcplugin.endOfDirectory(HANDLE)


def main_menu() -> None:
    handle_version_update()
    xbmcplugin.setPluginCategory(HANDLE, ADDON_NAME)
    xbmcplugin.setContent(HANDLE, "videos")
    if not has_saved_login():
        add_action("Login", "login", plot="Enter your Bang TV IPTV username and password to unlock Live TV, Movies and Series.")
        add_action("Settings", "open_settings", plot="Open Bang TV settings for login, metadata, EPG and background service options.")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    if setting_bool("show_account_status", True):
        _user, _pwd, label = get_effective_creds()
        add_action(f"Account: {label}", "account_status", plot="Shows your IPTV account status, expiry date and connection limits.")
    add_folder("Live TV", "live_categories", plot="Browse live IPTV channels with channel logos and Xtream EPG information.")
    add_folder("TV Guide", "tv_guide", plot="Open the skin-safe Bang TV guide that works across Kodi skins. Uses normal Kodi folder controls with Channel | Now | Next | Later rows.")
    add_folder("Recently Watched", "recent_live", plot="Quickly reopen your recent Live TV channels.")
    add_folder("Movies", "vod_categories", plot="Browse movie categories, recently added movies, posters, descriptions, ratings and trailers.")
    add_folder("Series", "series_categories", plot="Browse TV show categories, seasons and episodes with cached metadata and episode descriptions.")
    add_folder("Search", "search", plot="Search across Bang TV Movies, TV Shows and Live TV channels.")
    add_folder("Favourites", "favourites", plot="Open your saved Bang TV favourite movies, shows and channels.")
    add_folder("Tools", "tools", plot="Account tools, cache controls, connection test, settings and maintenance options.")
    add_action("Logout", "logout", plot="Logs out of Bang TV and removes your saved IPTV username and password.")
    xbmcplugin.endOfDirectory(HANDLE)


def router(paramstring: str) -> None:
    params = dict(urllib.parse.parse_qsl(paramstring or ""))
    mode = params.get("mode") or "main"
    if mode == "main":
        main_menu()
    elif mode == "login":
        login_prompt()
    elif mode == "open_settings":
        ADDON.openSettings()
    elif mode == "logout":
        logout()
    elif mode == "tools":
        tools_menu()
    elif mode == "cache_menu":
        cache_menu()
    elif mode == "live_help":
        live_update_help()
    elif mode == "live_dashboard":
        live_dashboard()
    elif mode == "setup_native_pvr_guide":
        export_native_pvr_files(show_dialog=True)
    elif mode == "native_tv_guide":
        list_tv_guide_categories()
    elif mode == "auto_cleanup":
        live_auto_cleanup(True)
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "backup_settings":
        backup_settings()
    elif mode == "restore_settings":
        restore_settings()
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "cache_action":
        cache_action(params.get("action") or "")
    elif mode == "account_status":
        account_status()
    elif mode == "connection_test":
        connection_test()
    elif mode == "play_trailer":
        play_trailer(params.get("trailer") or "", params.get("content_type") or "", params.get("item_id") or "")
    elif mode == "play":
        live_id = params.get("live_id") or ""
        url = get_play_link(params.get("id") or "") or params.get("url") or ""
        if live_id:
            recent_live_add(params.get("name") or "Live TV", live_id, url, params.get("thumb") or "", params.get("cat_id") or "", params.get("epg_plot") or "", {"plot": params.get("epg_plot") or "", "mediatype": "video"})
            stream_health_mark(live_id, True)
        play_url(url)
    elif mode == "fav_add_token":
        url = get_play_link(params.get("id") or "")
        if url:
            fav_add(params.get("name") or "Favourite", url, params.get("thumb") or "")
    elif mode == "fav_remove_token":
        url = get_play_link(params.get("id") or "")
        if url:
            fav_remove(url)
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
    elif mode == "fav_category_add":
        fav_category_add(params.get("name") or "Live TV Category", params.get("content_type") or "live", params.get("cat_id") or "", params.get("thumb") or "")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "fav_category_remove":
        fav_category_remove(params.get("content_type") or "live", params.get("cat_id") or "")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "search":
        search_type_menu()
    elif mode == "search_all":
        search_menu("all")
    elif mode == "search_live":
        search_menu("live")
    elif mode == "search_vod":
        search_menu("vod")
    elif mode == "search_series":
        search_menu("series")
    elif mode == "live_categories":
        list_categories("get_live_categories", "live_streams", "Live TV")
    elif mode == "tv_guide":
        list_tv_guide_categories()
        xbmcplugin.endOfDirectory(HANDLE)
    elif mode == "tv_guide_fallback":
        list_tv_guide_categories()
    elif mode == "tv_guide_category":
        list_tv_guide_channels(params.get("cat_id") or "", params.get("title") or "TV Guide", int(params.get("page") or 1))
        xbmcplugin.endOfDirectory(HANDLE)
    elif mode == "tv_guide_visual":
        open_visual_tv_guide(params.get("cat_id") or "", params.get("title") or "TV Guide")
        xbmcplugin.endOfDirectory(HANDLE)
    elif mode == "tv_guide_channel":
        list_tv_guide_channel(params.get("stream_id") or "", params.get("cat_id") or "", params.get("title") or "Live TV", params.get("thumb") or "")
    elif mode == "live_refresh":
        refresh_live_tv()
    elif mode == "live_stats":
        live_tv_stats()
    elif mode == "live_refresh_category":
        refresh_live_category(params.get("cat_id") or "", params.get("title") or "Live TV")
    elif mode == "recent_live":
        recent_live_menu()
    elif mode == "hidden_live":
        hidden_live_menu()
    elif mode == "live_category_hide":
        hidden_live_add(params.get("cat_id") or "", params.get("title") or "Live TV")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "live_category_unhide":
        hidden_live_remove(params.get("cat_id") or "")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "nz_streams":
        list_nz_streams()
    elif mode == "vod_categories":
        list_categories("get_vod_categories", "vod_streams", "Movies")
    elif mode == "series_categories":
        list_categories("get_series_categories", "series_list", "Series")
    elif mode == "live_streams":
        list_streams("live", params.get("cat_id") or "", "Live TV", safe_page(params.get("page")))
    elif mode == "vod_streams":
        list_streams("vod", params.get("cat_id") or "", "Movies", safe_page(params.get("page")))
    elif mode == "series_list":
        list_streams("series", params.get("cat_id") or "", "Series", safe_page(params.get("page")))
    elif mode == "recent_vod":
        list_recent_vod(safe_page(params.get("page")))
    elif mode == "series_seasons":
        list_series_seasons(params.get("series_id") or "")
    elif mode == "series_episodes":
        list_series_episodes(params.get("series_id") or "", params.get("season") or "")
    else:
        main_menu()


def safe_router(paramstring: str) -> None:
    try:
        router(paramstring)
    except Exception as exc:
        log(f"Directory failed: {exc}", xbmc.LOGERROR)
        try:
            xbmcplugin.setContent(HANDLE, "videos")
            add_action("Could not load this folder", "main", plot="Bang TV hit a provider or metadata error. Go back and try again, or clear cache from Tools.")
            xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
        except Exception:
            pass


if __name__ == "__main__":
    first_run_check()
    safe_router(sys.argv[2][1:] if len(sys.argv) > 2 else "")
