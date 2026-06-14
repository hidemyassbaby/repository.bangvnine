# -*- coding: utf-8 -*-
"""
Bang TV Kodi plugin
Version 1.0.49
Kodi 21 and Kodi 22 friendly, Python 3 only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import sqlite3
import urllib.parse
from html import unescape as html_unescape
import gzip
import re
import hashlib
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
SKYGO_EPG_URL = "https://i.mjh.nz/SkyGo/epg.xml.gz"
SKYGO_EPG_CATEGORY_IDS = {"317"}  # VIP | Sky Sport NZ
NZ_USER_AGENT = "otg/1.5.1 (AppleTv Apple TV 4; tvOS16.0; appletv.client) libcurl/7.58.0 OpenSSL/1.0.2o zlib/1.2.11 clib/1.8.56"

HEADERS = {
    "User-Agent": "Kodi BangTV/1.0.49",
    "Accept": "application/json,text/plain,*/*",
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
try:
    _adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
    SESSION.mount("http://", _adapter)
    SESSION.mount("https://", _adapter)
except Exception:
    pass

PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile")).rstrip("/\\")
if not xbmcvfs.exists(PROFILE_PATH):
    xbmcvfs.mkdirs(PROFILE_PATH)

ARTWORK_CACHE_DIR = os.path.join(PROFILE_PATH, "artwork_cache")
try:
    if not xbmcvfs.exists(ARTWORK_CACHE_DIR):
        xbmcvfs.mkdirs(ARTWORK_CACHE_DIR)
except Exception:
    pass

FAV_FILE = os.path.join(PROFILE_PATH, "favorites.json")
CACHE_FILE = os.path.join(PROFILE_PATH, "api_cache.json")
METADATA_DB_FILE = os.path.join(PROFILE_PATH, "metadata.db")
LIVE_DB_FILE = os.path.join(PROFILE_PATH, "live_cache.db")
LIBRARY_DB_FILE = os.path.join(PROFILE_PATH, "library_cache.db")
CACHE_TTL_SECONDS = 60 * 60
LIVE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
LIVE_CATEGORY_TTL_SECONDS = 7 * 24 * 60 * 60
EPG_TTL_SECONDS = 7 * 24 * 60 * 60
PAGE_SIZE = 20
FAST_PREVIEW_FETCH_LIMIT = PAGE_SIZE
_API_CACHE_MEMORY = None
_API_CACHE_DIRTY = False
METADATA_TTL_SECONDS = 30 * 24 * 60 * 60
BACKGROUND_QUEUE_FILE = os.path.join(PROFILE_PATH, "metadata_queue.json")
def addon_icon_path() -> str:
    candidates = []
    try:
        candidates.append(xbmcvfs.translatePath(ADDON.getAddonInfo("icon")))
    except Exception:
        pass
    candidates.extend([
        f"special://home/addons/{ADDON_ID}/icon.png",
        f"special://xbmc/addons/{ADDON_ID}/icon.png",
        os.path.join(xbmcvfs.translatePath(ADDON.getAddonInfo("path")), "icon.png"),
        "icon.png",
    ])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            if str(candidate).startswith("special://") or xbmcvfs.exists(candidate) or os.path.exists(candidate):
                return candidate
        except Exception:
            continue
    return f"special://home/addons/{ADDON_ID}/icon.png"


ADDON_ICON = addon_icon_path()
ADDON_VERSION = ADDON.getAddonInfo("version") or "1.0.13"

def cached_addon_icon_path() -> str:
    """Give Kodi skins a stable local file that changes filename each add-on version.

    Android TV can hold onto old texture records. A profile-cached icon named with
    the add-on version forces Kodi to treat it as fresh artwork without needing
    internet artwork or a full Kodi texture wipe.
    """
    try:
        safe_version = re.sub(r"[^A-Za-z0-9_.-]+", "_", ADDON_VERSION or "current")
        target = os.path.join(ARTWORK_CACHE_DIR, f"icon-{safe_version}.png")
        if os.path.exists(target) or xbmcvfs.exists(target):
            return target
        source = ADDON_ICON
        if source and (str(source).startswith("special://") or xbmcvfs.exists(source)):
            try:
                xbmcvfs.copy(source, target)
            except Exception:
                pass
        elif source and os.path.exists(source):
            try:
                import shutil
                shutil.copyfile(source, target)
            except Exception:
                pass
        if os.path.exists(target) or xbmcvfs.exists(target):
            return target
    except Exception:
        pass
    return ADDON_ICON

CACHED_ADDON_ICON = cached_addon_icon_path()
VERSION_MARKER_FILE = os.path.join(PROFILE_PATH, "installed_version.txt")
STARTUP_PRELOAD_FILE = os.path.join(PROFILE_PATH, "startup_preload.json")
PLAY_LINKS_FILE = os.path.join(PROFILE_PATH, "play_links.json")
LIVE_UPDATE_STATE_FILE = os.path.join(PROFILE_PATH, "live_update_state.json")
RECENT_LIVE_FILE = os.path.join(PROFILE_PATH, "recent_live.json")
HIDDEN_LIVE_CATEGORIES_FILE = os.path.join(PROFILE_PATH, "hidden_live_categories.json")
STREAM_HEALTH_FILE = os.path.join(PROFILE_PATH, "stream_health.json")
BACKUP_FILE = os.path.join(PROFILE_PATH, "bangtv_user_backup.json")
NOTIFICATIONS_FILE = os.path.join(PROFILE_PATH, "bangtv_notifications.json")
ACTIVITY_LOG_FILE = os.path.join(PROFILE_PATH, "bangtv_activity_log.json")
STATISTICS_FILE = os.path.join(PROFILE_PATH, "bangtv_statistics.json")
REMOVED_EXPORT_FILES = (
    os.path.join(PROFILE_PATH, "bangtv_pvr_channels.m3u8"),
    os.path.join(PROFILE_PATH, "bangtv_pvr_guide_setup.txt"),
)
MANUAL_EPG_FILE = os.path.join(PROFILE_PATH, "manual_epg_map.json")
LIVE_AUTO_CHECK_SECONDS = 30 * 60
LIVE_HIGH_ACTIVITY_SECONDS = 10 * 60
LIVE_HIGH_ACTIVITY_CHANGE_THRESHOLD = 20
LIVE_ACTIVE_CATEGORY_CHECK_SECONDS = 10 * 60
LIVE_RECENT_CATEGORY_CHECK_SECONDS = 30 * 60



def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def notify(message: str, title: str = ADDON_NAME, ms: int = 3000, icon: str = xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(title, message, icon, ms)


def progress_create(progress: Any, heading: str, line1: str = "", line2: str = "") -> None:
    message = "\n".join([x for x in [line1, line2] if x])
    try:
        progress.create(heading, message)
    except TypeError:
        try:
            progress.create(heading)
        except Exception:
            pass
    except Exception as exc:
        log(f"Progress dialog create failed: {exc}", xbmc.LOGWARNING)


def progress_update(progress: Any, percent: int, line1: str = "", line2: str = "") -> None:
    message = "\n".join([x for x in [line1, line2] if x])
    try:
        progress.update(int(percent), message)
    except TypeError:
        try:
            progress.update(int(percent))
        except Exception:
            pass
    except Exception as exc:
        log(f"Progress dialog update failed: {exc}", xbmc.LOGWARNING)


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


def live_startup_epg_boost_count() -> int:
    """Small blocking EPG boost for first open when the background cache is still empty."""
    try:
        return max(0, min(8, int(get_setting("live_startup_epg_boost", "4") or "4")))
    except Exception:
        return 4


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
    notify("Login saved. Downloading Live TV channels now. EPG will keep filling in the background.")
    xbmc.executebuiltin("Container.Refresh")


def xc_api_url(endpoint: str) -> str:
    user, pwd, _label = get_effective_creds()
    sep = "&" if "?" in endpoint else "?"
    return f"{SERVER}/{endpoint}{sep}username={quote(user)}&password={quote(pwd)}"


def load_cache() -> Dict[str, Any]:
    """Load the API cache once per Kodi plugin run.

    Android TV can feel laggy if the JSON cache file is read many times while
    building a menu. Keeping it in memory for the current run reduces disk I/O.
    """
    global _API_CACHE_MEMORY
    if isinstance(_API_CACHE_MEMORY, dict):
        return _API_CACHE_MEMORY
    try:
        if not os.path.exists(CACHE_FILE):
            _API_CACHE_MEMORY = {}
            return _API_CACHE_MEMORY
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            text = fh.read()
        try:
            data = json.loads(text)
        except Exception as exc:
            log(f"Cache read failed, attempting recovery: {exc}", xbmc.LOGWARNING)
            decoder = json.JSONDecoder()
            data, _idx = decoder.raw_decode(text.strip())
            try:
                save_cache(data if isinstance(data, dict) else {})
            except Exception:
                pass
        _API_CACHE_MEMORY = data if isinstance(data, dict) else {}
        return _API_CACHE_MEMORY
    except Exception as exc:
        log(f"Cache read failed: {exc}", xbmc.LOGWARNING)
        try:
            bad_file = CACHE_FILE + ".bad"
            if os.path.exists(CACHE_FILE):
                os.replace(CACHE_FILE, bad_file)
        except Exception:
            pass
        _API_CACHE_MEMORY = {}
        return _API_CACHE_MEMORY


def prune_cache(cache: Dict[str, Any], max_entries: int = 350) -> Dict[str, Any]:
    """Keep the on-disk cache small so Android TV storage stays quick."""
    try:
        if len(cache) <= max_entries:
            return cache
        items = sorted(cache.items(), key=lambda kv: int(kv[1].get("time", 0)) if isinstance(kv[1], dict) else 0, reverse=True)
        return dict(items[:max_entries])
    except Exception:
        return cache


def save_cache(cache: Dict[str, Any]) -> None:
    global _API_CACHE_MEMORY
    try:
        cache = prune_cache(cache if isinstance(cache, dict) else {})
        _API_CACHE_MEMORY = cache
        tmp_file = CACHE_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
        os.replace(tmp_file, CACHE_FILE)
    except Exception as exc:
        log(f"Cache save failed: {exc}", xbmc.LOGWARNING)


def metadata_db() -> sqlite3.Connection:
    conn = sqlite3.connect(METADATA_DB_FILE, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
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
        tmp_file = BACKGROUND_QUEUE_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as fh:
            json.dump(items[:2500], fh, ensure_ascii=False)
        os.replace(tmp_file, BACKGROUND_QUEUE_FILE)
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
        for path in (CACHE_FILE, BACKGROUND_QUEUE_FILE, LIVE_UPDATE_STATE_FILE):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
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
            # New installs and upgrades can otherwise keep stale category, EPG and artwork rows.
            # Clear all generated cache, but keep login, settings, favourites and manual mappings.
            for path in (CACHE_FILE, BACKGROUND_QUEUE_FILE, LIVE_UPDATE_STATE_FILE) + REMOVED_EXPORT_FILES:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            metadata_cache_delete_file()
            metadata_db().close()
            with open(VERSION_MARKER_FILE, "w", encoding="utf-8") as fh:
                fh.write(ADDON_VERSION)
            mark_startup_preload_pending("version_update")
            notify(f"Bang TV updated to v{ADDON_VERSION}. Fresh cache will rebuild now.")
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

def force_icon_refresh() -> None:
    try:
        # Remove old versioned icon files from the add-on profile, then recreate this version's copy.
        if os.path.isdir(ARTWORK_CACHE_DIR):
            for name in os.listdir(ARTWORK_CACHE_DIR):
                if name.startswith("icon-") and name.endswith(".png"):
                    try:
                        os.remove(os.path.join(ARTWORK_CACHE_DIR, name))
                    except Exception:
                        pass
        global CACHED_ADDON_ICON
        CACHED_ADDON_ICON = cached_addon_icon_path()
        notify("Bang TV icon cache refreshed")
        xbmc.executebuiltin("Container.Refresh")
    except Exception as exc:
        log(f"Icon refresh failed: {exc}", xbmc.LOGWARNING)
        notify("Could not refresh icon cache", icon=xbmcgui.NOTIFICATION_ERROR)


def cache_action(action: str) -> None:
    if action == "icons":
        force_icon_refresh()
        return
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


def api_cache_ttl_for_url(url: str, ttl: Optional[int] = None) -> int:
    if ttl is not None:
        return int(ttl)
    u = str(url or "")
    if "action=get_live_categories" in u:
        return LIVE_CATEGORY_TTL_SECONDS
    if "action=get_live_streams" in u:
        return LIVE_CACHE_TTL_SECONDS
    if "action=get_short_epg" in u or "xmltv.php" in u:
        return EPG_TTL_SECONDS
    return CACHE_TTL_SECONDS


def http_get_json(url: str, timeout: int = 25, use_cache: bool = True, silent: bool = False, ttl: Optional[int] = None) -> Optional[Any]:
    cache = load_cache() if use_cache else {}
    now = int(time.time())
    effective_ttl = api_cache_ttl_for_url(url, ttl)
    cached = cache.get(url)
    if use_cache and isinstance(cached, dict) and now - int(cached.get("time", 0)) < effective_ttl:
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
    # Android TV speed/safety: if the server is slow or offline, keep using the
    # saved local response instead of blocking or returning an empty folder.
    if use_cache and isinstance(cached, dict) and "data" in cached:
        return cached.get("data")
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


def cached_json_is_fresh(url: str, ttl: Optional[int] = None) -> bool:
    try:
        cache = load_cache()
        cached = cache.get(url)
        if not isinstance(cached, dict):
            return False
        return int(time.time()) - int(cached.get("time", 0)) < api_cache_ttl_for_url(url, ttl)
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
            # The caller decides which cache/database table should receive the response.
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


def live_db() -> sqlite3.Connection:
    """Small SQLite cache for Live TV categories and channels.

    This makes Bang TV database-first on Android TV. Folder opening can read
    from SQLite immediately, while the JSON API cache/background service updates
    the database only when channels change.
    """
    conn = sqlite3.connect(LIVE_DB_FILE, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
    except Exception:
        pass
    conn.execute("CREATE TABLE IF NOT EXISTS live_categories (category_id TEXT PRIMARY KEY, name TEXT, updated INTEGER, data TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS live_channels (stream_id TEXT PRIMARY KEY, category_id TEXT, name TEXT, signature TEXT, updated INTEGER, data TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_live_channels_category ON live_channels(category_id)")
    conn.execute("CREATE TABLE IF NOT EXISTS live_fingerprints (scope TEXT PRIMARY KEY, fingerprint TEXT, updated INTEGER, count INTEGER)")
    return conn


def live_fingerprint(items: Any, category: bool = False) -> str:
    try:
        sigs = live_signature_map(items, category)
        packed = json.dumps(sigs, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(packed.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def live_db_save_fingerprint(scope: str, items: Any, category: bool = False) -> None:
    try:
        fp = live_fingerprint(items, category)
        count = len(items) if isinstance(items, list) else 0
        with live_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO live_fingerprints(scope, fingerprint, updated, count) VALUES (?, ?, ?, ?)",
                (scope, fp, int(time.time()), int(count)),
            )
    except Exception as exc:
        log(f"Live fingerprint save failed: {exc}", xbmc.LOGWARNING)


def live_db_get_fingerprint(scope: str) -> Dict[str, Any]:
    try:
        with live_db() as conn:
            row = conn.execute("SELECT fingerprint, updated, count FROM live_fingerprints WHERE scope=?", (scope,)).fetchone()
        if not row:
            return {}
        return {"fingerprint": row[0] or "", "updated": int(row[1] or 0), "count": int(row[2] or 0)}
    except Exception:
        return {}


def live_db_upsert_categories(items: Any) -> None:
    if not isinstance(items, list):
        return
    now = int(time.time())
    try:
        with live_db() as conn:
            for item in items:
                if not isinstance(item, dict):
                    continue
                cid = str(item.get("category_id") or item.get("id") or "").strip()
                if not cid:
                    continue
                name = str(item.get("category_name") or item.get("name") or "Live TV")
                conn.execute(
                    "INSERT OR REPLACE INTO live_categories(category_id, name, updated, data) VALUES (?, ?, ?, ?)",
                    (cid, name, now, json.dumps(item, ensure_ascii=False)),
                )
        live_db_save_fingerprint("categories", items, True)
    except Exception as exc:
        log(f"Live category DB update failed: {exc}", xbmc.LOGWARNING)


def live_db_upsert_channels(items: Any, category_id: str = "") -> None:
    if not isinstance(items, list):
        return
    now = int(time.time())
    try:
        with live_db() as conn:
            if category_id:
                conn.execute("DELETE FROM live_channels WHERE category_id=?", (str(category_id),))
            for item in items:
                if not isinstance(item, dict):
                    continue
                sid = live_item_id(item, False)
                if not sid:
                    continue
                cid = str(item.get("category_id") or category_id or "")
                name = str(item.get("name") or "Unknown")
                sig = json.dumps(live_item_signature(item, False), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                conn.execute(
                    "INSERT OR REPLACE INTO live_channels(stream_id, category_id, name, signature, updated, data) VALUES (?, ?, ?, ?, ?, ?)",
                    (sid, cid, name, sig, now, json.dumps(item, ensure_ascii=False)),
                )
        live_db_save_fingerprint(f"category:{category_id}", items, False)
    except Exception as exc:
        log(f"Live channel DB update failed: {exc}", xbmc.LOGWARNING)


def live_db_load_categories() -> List[Dict[str, Any]]:
    try:
        with live_db() as conn:
            rows = conn.execute("SELECT data FROM live_categories ORDER BY lower(name)").fetchall()
        out = []
        for (raw,) in rows:
            try:
                item = json.loads(raw or "{}")
                if isinstance(item, dict):
                    out.append(item)
            except Exception:
                pass
        return out
    except Exception:
        return []


def live_db_load_channels(category_id: str = "") -> List[Dict[str, Any]]:
    try:
        with live_db() as conn:
            if category_id:
                rows = conn.execute("SELECT data FROM live_channels WHERE category_id=? ORDER BY lower(name)", (str(category_id),)).fetchall()
            else:
                rows = conn.execute("SELECT data FROM live_channels ORDER BY lower(name)").fetchall()
        out = []
        for (raw,) in rows:
            try:
                item = json.loads(raw or "{}")
                if isinstance(item, dict):
                    out.append(item)
            except Exception:
                pass
        return out
    except Exception:
        return []



def library_db() -> sqlite3.Connection:
    """SQLite cache for Movies and TV Shows lists.

    This keeps VOD and Series folders fast after the first open. The JSON API
    response is still respected, but Kodi can rebuild pages from local SQLite
    when Android TV storage/network is slow or the server is unavailable.
    """
    conn = sqlite3.connect(LIBRARY_DB_FILE, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
    except Exception:
        pass
    conn.execute("CREATE TABLE IF NOT EXISTS library_categories (content_type TEXT, category_id TEXT, name TEXT, updated INTEGER, data TEXT, PRIMARY KEY(content_type, category_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS library_items (content_type TEXT, item_id TEXT, category_id TEXT, name TEXT, added INTEGER, updated INTEGER, data TEXT, PRIMARY KEY(content_type, item_id))")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_library_items_type_category ON library_items(content_type, category_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_library_items_type_added ON library_items(content_type, added)")
    return conn


def library_db_upsert_categories(content_type: str, items: Any) -> None:
    if not isinstance(items, list):
        return
    now = int(time.time())
    ctype = content_type or "vod"
    try:
        with library_db() as conn:
            for item in items:
                if not isinstance(item, dict):
                    continue
                cid = str(item.get("category_id") or item.get("id") or "").strip()
                if not cid:
                    continue
                name = str(item.get("category_name") or item.get("name") or "Unknown")
                conn.execute(
                    "INSERT OR REPLACE INTO library_categories(content_type, category_id, name, updated, data) VALUES (?, ?, ?, ?, ?)",
                    (ctype, cid, name, now, json.dumps(item, ensure_ascii=False)),
                )
    except Exception as exc:
        log(f"Library category DB update failed: {exc}", xbmc.LOGWARNING)


def library_item_id(content_type: str, item: Dict[str, Any]) -> str:
    if content_type == "series":
        return str(item.get("series_id") or item.get("id") or "").strip()
    return str(item.get("stream_id") or item.get("id") or "").strip()


def library_db_upsert_items(content_type: str, items: Any, category_id: str = "") -> None:
    if not isinstance(items, list):
        return
    now = int(time.time())
    ctype = content_type or "vod"
    try:
        with library_db() as conn:
            if category_id:
                conn.execute("DELETE FROM library_items WHERE content_type=? AND category_id=?", (ctype, str(category_id)))
            for item in items:
                if not isinstance(item, dict):
                    continue
                iid = library_item_id(ctype, item)
                if not iid:
                    continue
                cid = str(item.get("category_id") or category_id or "")
                name = str(item.get("name") or item.get("title") or "Unknown")
                added = safe_int(item.get("added"))
                conn.execute(
                    "INSERT OR REPLACE INTO library_items(content_type, item_id, category_id, name, added, updated, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ctype, iid, cid, name, added, now, json.dumps(item, ensure_ascii=False)),
                )
    except Exception as exc:
        log(f"Library item DB update failed: {exc}", xbmc.LOGWARNING)


def library_db_load_categories(content_type: str) -> List[Dict[str, Any]]:
    try:
        with library_db() as conn:
            rows = conn.execute("SELECT data FROM library_categories WHERE content_type=? ORDER BY lower(name)", (content_type,)).fetchall()
        out: List[Dict[str, Any]] = []
        for (raw,) in rows:
            try:
                item = json.loads(raw or "{}")
                if isinstance(item, dict):
                    out.append(item)
            except Exception:
                pass
        return out
    except Exception:
        return []


def library_db_load_items(content_type: str, category_id: str = "") -> List[Dict[str, Any]]:
    try:
        with library_db() as conn:
            if category_id:
                rows = conn.execute("SELECT data FROM library_items WHERE content_type=? AND category_id=? ORDER BY lower(name)", (content_type, str(category_id))).fetchall()
            else:
                rows = conn.execute("SELECT data FROM library_items WHERE content_type=? ORDER BY lower(name)", (content_type,)).fetchall()
        out: List[Dict[str, Any]] = []
        for (raw,) in rows:
            try:
                item = json.loads(raw or "{}")
                if isinstance(item, dict):
                    out.append(item)
            except Exception:
                pass
        return out
    except Exception:
        return []


def library_db_recent_vod(limit: int = 300) -> List[Dict[str, Any]]:
    try:
        with library_db() as conn:
            rows = conn.execute("SELECT data FROM library_items WHERE content_type='vod' ORDER BY added DESC, lower(name) LIMIT ?", (int(limit),)).fetchall()
        out: List[Dict[str, Any]] = []
        for (raw,) in rows:
            try:
                item = json.loads(raw or "{}")
                if isinstance(item, dict):
                    out.append(item)
            except Exception:
                pass
        return out
    except Exception:
        return []


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
        # Include possible provider-side URL/source fields when present so stream changes
        # are detected even when the visible channel name and logo stay the same.
        "stream_url": str(item.get("stream_url") or item.get("url") or item.get("direct_source") or item.get("source") or ""),
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


def live_update_message(changes: Dict[str, Any], epg_updated: bool = False, prefix: str = "Bang TV updated") -> str:
    added = int(changes.get("added_count", 0) or 0) if isinstance(changes, dict) else 0
    removed = int(changes.get("removed_count", 0) or 0) if isinstance(changes, dict) else 0
    changed = int(changes.get("changed_count", 0) or 0) if isinstance(changes, dict) else 0
    parts = []
    if added:
        parts.append(f"New channels added: {added}")
    if changed:
        parts.append(f"Channels updated: {changed}")
    if removed:
        parts.append(f"Channels removed: {removed}")
    if epg_updated:
        parts.append("EPG updated")
    if not parts:
        return prefix + ": already up to date"
    return prefix + "\n" + "\n".join("• " + p for p in parts)


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
            live_db_upsert_categories(new_categories)
        else:
            new_categories = old_categories if isinstance(old_categories, list) else []

        if progress:
            progress.update(45, "Checking only opened Live TV folders...")
        # Super-fast mode: do not download the full all-channels playlist during normal
        # background checks. That call can be large and causes Android TV delays.
        # Manual Refresh Live TV / Force Full Rebuild still does the full check.
        all_streams_url = xc_api_url("player_api.php?action=get_live_streams")
        old_streams = cache.get(all_streams_url, {}).get("data") if isinstance(cache.get(all_streams_url), dict) else []
        new_streams = None
        if force or not isinstance(old_streams, list) or not old_streams:
            if progress:
                progress.update(55, "Downloading full playlist because refresh was forced...")
            new_streams = http_get_json(all_streams_url, timeout=35, use_cache=False, silent=True)
        if isinstance(new_streams, list):
            channel_changes = compare_live_maps(live_signature_map(old_streams, False), live_signature_map(new_streams, False))
            result["channel_changes"] = channel_changes
            cache[all_streams_url] = {"time": now, "data": new_streams}
            live_db_upsert_channels(new_streams, "")
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
            if progress:
                progress.update(70, "Updating changed categories...")
            for index, cid in enumerate(result["changed_category_ids"][:30]):
                _cu, streams_url = live_cache_keys_for_category(cid)
                items = [item for item in new_streams if isinstance(item, dict) and str(item.get("category_id") or "") == str(cid)]
                cache[streams_url] = {"time": now, "data": items}
                live_db_upsert_channels(items, cid)
                if progress and result["changed_category_ids"]:
                    progress.update(70 + min(20, int((index + 1) * 20 / max(1, len(result["changed_category_ids"])))), f"Updated category {index + 1} of {len(result['changed_category_ids'])}")
        else:
            result["channel_changes"] = {"added_count": 0, "removed_count": 0, "changed_count": 0}
        save_cache(cache)
    except Exception as exc:
        result["error"] = str(exc)
        log(f"Smart Live TV check failed: {exc}", xbmc.LOGWARNING)

    state["last_check"] = now
    state["last_result"] = result
    save_live_update_state(state)
    try:
        chn = result.get("channel_changes") if isinstance(result.get("channel_changes"), dict) else {}
        total = int(chn.get("added_count", 0) or 0) + int(chn.get("removed_count", 0) or 0) + int(chn.get("changed_count", 0) or 0)
        if total:
            add_bang_notification(live_update_message(chn), "Updates")
    except Exception:
        pass
    if show_notice:
        ch = result.get("channel_changes") if isinstance(result.get("channel_changes"), dict) else {}
        added = int(ch.get("added_count", 0) or 0)
        removed = int(ch.get("removed_count", 0) or 0)
        changed = int(ch.get("changed_count", 0) or 0)
        if added or removed or changed:
            notify(live_update_message(ch))
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
                live_db_upsert_channels(data, cat_id)
            if isinstance(data, list):
                state = load_live_update_state()
                state["last_check"] = int(time.time())
                state["last_result"] = {"checked": True, "time": int(time.time()), "category_update": str(cat_id), "channel_changes": changes, "changed_category_ids": [str(cat_id)]}
                save_live_update_state(state)
                total = int(changes.get("added_count", 0) or 0) + int(changes.get("removed_count", 0) or 0) + int(changes.get("changed_count", 0) or 0)
                if total:
                    notify(live_update_message(changes, prefix=f"{label} updated"))
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


def epg_alias_keys(value: Any) -> List[str]:
    """Return forgiving lookup keys for provider names vs XMLTV names.

    Some playlists add labels such as VIP, NZ, HD, FHD or pipe prefixes while
    the SkyGo XMLTV feed uses cleaner channel names. These aliases let a
    channel like 'VIP | Sky Sport NZ 1 FHD' match 'Sky Sport 1'.
    """
    raw = str(value or "").strip()
    if not raw:
        return []
    variants = {raw}
    no_brackets = re.sub(r"\[[^\]]+\]|\([^\)]+\)", " ", raw)
    variants.add(no_brackets)
    for part in re.split(r"[|/\\>-]", raw):
        part = part.strip()
        if part:
            variants.add(part)
    cleaned: set = set()
    for item in list(variants):
        text = re.sub(r"\b(VIP|NZ|NEW ZEALAND|FHD|HD|SD|UHD|4K|HEVC|H265|H264|1080P|720P|RAW|LIVE)\b", " ", item, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cleaned.add(text)
        # Sky Sport NZ 1 -> Sky Sport 1, Sky Sports 1 -> Sky Sport 1
        text2 = re.sub(r"\bSky\s+Sports\b", "Sky Sport", text, flags=re.I)
        text2 = re.sub(r"\bSky\s+Sport\s+NZ\b", "Sky Sport", text2, flags=re.I)
        text2 = re.sub(r"\s+", " ", text2).strip()
        if text2:
            cleaned.add(text2)
    keys: List[str] = []
    for item in list(variants) + list(cleaned):
        for key in (item, norm_epg_key(item)):
            if key and key not in keys:
                keys.append(key)
    return keys


def is_sky_sport_nz_live_item(item: Dict[str, Any], category_title: str = "", cat_id: str = "") -> bool:
    """True when this row/category should use Matt Huisman's SkyGo EPG.

    VIP | Sky Sport NZ is explicitly mapped to category 317.  Name matching is
    kept as a backup because some servers rename the category or channels.
    """
    cid = str(cat_id or item.get("category_id") or item.get("cat_id") or "").strip()
    if cid in SKYGO_EPG_CATEGORY_IDS:
        return True
    text = " ".join([
        str(category_title or ""),
        str(item.get("category_name") or ""),
        str(item.get("group-title") or ""),
        str(item.get("name") or ""),
        str(item.get("epg_channel_id") or ""),
        str(item.get("tvg_id") or ""),
    ]).lower()
    return "sky" in text and "sport" in text and ("nz" in text or "new zealand" in text or "vip" in text)


def combined_epg_map_for_live_items(items: List[Dict[str, Any]], category_title: str = "", cat_id: str = "") -> Dict[str, Dict[str, str]]:
    """Build the right Now/Next EPG map for the current Live TV list.

    Xtream XMLTV remains the default. If the current category/list contains
    VIP | Sky Sport NZ style channels, merge in Matt Huisman's SkyGo XMLTV feed
    so those channels can show reliable Sky Sport NZ guide data.
    """
    epg_map = xmltv_epg_map(xtream_xmltv_url(), "xtream_live")
    try:
        if str(cat_id or "") in SKYGO_EPG_CATEGORY_IDS or any(is_sky_sport_nz_live_item(i, category_title, cat_id) for i in items or []):
            sky_map = xmltv_epg_map(SKYGO_EPG_URL, "skygo_live")
            if sky_map:
                merged = dict(epg_map)
                merged.update(sky_map)
                add_notification("Sky Sport NZ EPG available", "Sky GO NZ EPG feed is being used for VIP | Sky Sport NZ, category 317.", "updates")
                add_activity("Sky Sport NZ EPG loaded from Sky GO NZ feed", "updates")
                return merged
    except Exception as exc:
        log(f"Sky Sport NZ EPG merge failed: {exc}", xbmc.LOGWARNING)
    return epg_map


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
                for alias in epg_alias_keys(key):
                    if alias:
                        result[alias] = value
                result[key] = value
                nkey = norm_epg_key(key)
                if nkey:
                    result[nkey] = value
    if result:
        metadata_cache_set("epg_xmltv", cache_key, result)
    return result




def cached_xmltv_epg_map(cache_key: str = "xtream_live") -> Dict[str, Dict[str, str]]:
    """Return XMLTV Now/Next from SQLite only.

    This keeps Android TV browsing instant. The background/startup preload or
    manual Refresh EPG fills this cache, but opening a channel folder should not
    download and parse a huge XMLTV file.
    """
    cached = metadata_cache_get("epg_xmltv", cache_key, ttl=EPG_TTL_SECONDS)
    return cached if isinstance(cached, dict) else {}


def live_epg_cached_only(stream_id: Any) -> Dict[str, str]:
    """Return short EPG only when it already exists locally."""
    if not stream_id or not setting_bool("show_epg", True):
        return {}
    cached = metadata_cache_get("epg", stream_id, ttl=EPG_TTL_SECONDS)
    return cached if isinstance(cached, dict) else {}

def live_item_epg_from_map(item: Dict[str, Any], epg_map: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    manual = manual_epg_now_next(item)
    if manual:
        return manual
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
    expanded: List[str] = []
    for key in candidates:
        if key in (None, ""):
            continue
        for alias in epg_alias_keys(key):
            if alias and alias not in expanded:
                expanded.append(alias)
    for key in expanded:
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
    thumb = safe_image_url(thumb) if thumb else ""
    fanart = safe_image_url(fanart) if fanart else ""
    fallback = CACHED_ADDON_ICON or ADDON_ICON
    image = thumb or fallback
    art = {
        "icon": image,
        "thumb": image,
        "poster": image,
        "banner": image,
        "landscape": fanart or image,
    }
    if fanart:
        art["fanart"] = fanart
    else:
        art["fanart"] = fallback
    li.setArt(art)
    # Some Android TV skins look at old ListItem properties instead of setArt only.
    try:
        li.setProperty("icon", image)
        li.setProperty("thumb", image)
        li.setProperty("poster", image)
        li.setProperty("banner", image)
        li.setProperty("clearlogo", fallback)
        li.setProperty("fanart_image", art.get("fanart") or fallback)
    except Exception:
        pass


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
        tmp_file = path + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_file, path)
    except Exception as exc:
        log(f"Could not write {path}: {exc}", xbmc.LOGERROR)







BUILTIN_EPG_SOURCES = {
    "skygo": {
        "label": "Sky GO NZ",
        "url": SKYGO_EPG_URL,
        "builtin": True,
        "enabled": True,
        "description": "Matt Huisman Sky GO NZ XMLTV feed for Sky Sport NZ and related channels.",
    },
}


def ensure_builtin_epg_sources(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {"sources": {}, "channels": {}}
    sources = data.setdefault("sources", {})
    if not isinstance(sources, dict):
        data["sources"] = sources = {}
    for sid, src in BUILTIN_EPG_SOURCES.items():
        saved = sources.get(sid) if isinstance(sources.get(sid), dict) else {}
        merged = dict(src)
        merged.update(saved or {})
        merged["label"] = src["label"]
        merged["url"] = src["url"]
        merged["builtin"] = True
        merged.setdefault("enabled", True)
        sources[sid] = merged
    return data


def manual_epg_load() -> Dict[str, Any]:
    data = read_json_file(MANUAL_EPG_FILE, {"sources": {}, "channels": {}})
    if not isinstance(data, dict):
        data = {"sources": {}, "channels": {}}
    if not isinstance(data.get("sources"), dict):
        data["sources"] = {}
    if not isinstance(data.get("channels"), dict):
        data["channels"] = {}
    return ensure_builtin_epg_sources(data)


def manual_epg_save(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        data = {"sources": {}, "channels": {}}
    data.setdefault("sources", {})
    data.setdefault("channels", {})
    write_json_file(MANUAL_EPG_FILE, data)


def manual_epg_channel_key(stream_id: Any = "", name: str = "") -> str:
    sid = str(stream_id or "").strip()
    if sid:
        return "stream:" + sid
    return "name:" + norm_epg_key(name)


def get_manual_epg_assignment(item: Dict[str, Any]) -> Dict[str, Any]:
    data = manual_epg_load()
    channels = data.get("channels") or {}
    keys = [manual_epg_channel_key(item.get("stream_id") or item.get("live_id") or "", item.get("name") or "")]
    name_key = manual_epg_channel_key("", item.get("name") or "")
    if name_key not in keys:
        keys.append(name_key)
    for key in keys:
        val = channels.get(key)
        if isinstance(val, dict):
            return val
    return {}


def manual_epg_source_url(source_id: str) -> str:
    if source_id == "xtream":
        return xtream_xmltv_url()
    if source_id == "skygo":
        return SKYGO_EPG_URL
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id)
    return str((src or {}).get("url") or "") if isinstance(src, dict) else ""


def manual_epg_guide_for_assignment(assign: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(assign.get("source_id") or "")
    url = str(assign.get("url") or "") or manual_epg_source_url(source_id)
    if not url:
        return {}
    cache_key = "manual_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id or str(abs(hash(url))))[:80]
    return xmltv_guide_data(url, cache_key)


def manual_epg_now_next(item: Dict[str, Any]) -> Dict[str, str]:
    assign = get_manual_epg_assignment(item)
    if not assign:
        return {}
    guide = manual_epg_guide_for_assignment(assign)
    programmes = guide.get("programmes") if isinstance(guide, dict) else {}
    channel_id = str(assign.get("channel_id") or "")
    if not isinstance(programmes, dict) or not channel_id:
        return {}
    return guide_now_next_text(programmes.get(channel_id, []) or {}) and {"plot": guide_now_next_text(programmes.get(channel_id, []) or [])} or {}


def _epg_source_candidate_urls(url: str) -> List[str]:
    urls = []
    u = str(url or '').strip()
    if u:
        urls.append(u)
    if 'githubusercontent.com/matthuisman/i.mjh.nz' in u and '/refs/heads/master/' in u:
        urls.append(u.replace('/refs/heads/master/', '/master/'))
    if 'SkyGo/epg.xml' in u or 'SkyGo/epg.xml.gz' in u:
        urls.append('https://i.mjh.nz/SkyGo/epg.xml.gz')
        urls.append('https://i.mjh.nz/SkyGo/epg.xml')
        urls.append('https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/SkyGo/epg.xml')
    # preserve order but remove duplicates
    out = []
    for item in urls:
        if item and item not in out:
            out.append(item)
    return out


def _download_epg_source_bytes(url: str, progress: Any = None, force_refresh: bool = False) -> Tuple[bytes, str, str]:
    """Download an XMLTV source for manual channel browsing.

    This uses a direct requests call rather than the generic cache helper so the
    EPG source picker can show visible progress and try known Sky GO mirrors.
    Returns: bytes, used_url, error_text.
    """
    last_error = ''
    for idx, candidate in enumerate(_epg_source_candidate_urls(url)):
        if progress:
            try:
                progress.update(min(15 + idx * 15, 55), 'Downloading EPG source...', candidate[:90])
            except Exception:
                pass
        try:
            headers = {'User-Agent': 'Kodi BangTV EPG Manager/1.0'}
            response = SESSION.get(candidate, timeout=75, headers=headers)
            response.raise_for_status()
            data = response.content or b''
            if data:
                return data, candidate, ''
            last_error = 'Downloaded file was empty'
        except requests.exceptions.Timeout:
            last_error = 'Timed out downloading EPG source'
            log(f'Manual EPG source timeout: {redact_url(candidate)}', xbmc.LOGWARNING)
        except Exception as exc:
            last_error = str(exc)
            log(f'Manual EPG source download failed: {redact_url(candidate)} - {exc}', xbmc.LOGWARNING)
    return b'', '', last_error or 'Could not download EPG source'


def _parse_xmltv_channels_fast(raw: bytes, progress: Any = None) -> List[Tuple[str, str]]:
    """Parse XMLTV <channel> blocks only.

    XMLTV files can be very large because of programmes. For the manual picker
    we only need the <channel> list, so this avoids loading the full guide.
    """
    if not raw:
        return []
    try:
        if raw[:2] == b'\x1f\x8b':
            if progress:
                progress.update(62, 'Decompressing EPG source...')
            raw = gzip.decompress(raw)
    except Exception as exc:
        log(f'Manual EPG gzip decompress failed: {exc}', xbmc.LOGWARNING)
    if progress:
        progress.update(70, 'Reading EPG channel list...')
    text = raw.decode('utf-8', 'ignore')
    # Only scan the channel header area where possible. This is much faster on
    # big 7-day feeds.
    first_programme = text.find('<programme')
    scan = text[:first_programme] if first_programme > 0 else text
    choices = []
    seen = set()
    # Handles <channel id="..."><display-name>...</display-name></channel>
    pattern = re.compile(r'<channel\b([^>]*)>(.*?)</channel\s*>', re.I | re.S)
    for i, m in enumerate(pattern.finditer(scan)):
        attrs = m.group(1) or ''
        body = m.group(2) or ''
        id_match = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if not id_match:
            continue
        ch_id = id_match.group(1).strip()
        if not ch_id or ch_id in seen:
            continue
        names = []
        for dn in re.finditer(r'<display-name\b[^>]*>(.*?)</display-name\s*>', body, re.I | re.S):
            name = re.sub(r'<[^>]+>', '', dn.group(1) or '')
            name = html_unescape(name).strip()
            if name and name not in names:
                names.append(name)
        label = names[0] if names else ch_id
        seen.add(ch_id)
        choices.append((ch_id, label))
        if progress and i and i % 50 == 0:
            try:
                progress.update(min(70 + int(len(choices) / 10), 92), f'Found {len(choices)} EPG channels...', label[:80])
            except Exception:
                pass
    if choices:
        choices.sort(key=lambda x: x[1].lower())
        return choices
    # Fallback to ElementTree if the regex missed namespaced or unusual XML.
    try:
        if progress:
            progress.update(82, 'Using fallback XML parser...')
        root = ET.fromstring(raw)
        for channel in root.iter():
            tag = str(channel.tag or '').split('}')[-1].lower()
            if tag != 'channel':
                continue
            ch_id = str(channel.get('id') or '').strip()
            if not ch_id or ch_id in seen:
                continue
            label = ch_id
            for child in list(channel):
                ctag = str(child.tag or '').split('}')[-1].lower()
                if ctag == 'display-name' and (child.text or '').strip():
                    label = (child.text or '').strip()
                    break
            seen.add(ch_id)
            choices.append((ch_id, label))
    except Exception as exc:
        log(f'Manual EPG fallback XML parse failed: {exc}', xbmc.LOGWARNING)
    choices.sort(key=lambda x: x[1].lower())
    return choices


def xmltv_channel_choices(url: str, cache_key: str, force_refresh: bool = False, progress: Any = None) -> List[Tuple[str, str]]:
    """Return every XMLTV <channel> from an EPG source.

    This ignores the normal EPG on/off setting. When you click Sky GO NZ under
    EPG Sources, this function downloads/parses that XMLTV and returns every
    channel in the EPG so you can pick one and assign it manually.
    """
    if not url:
        return []
    cache_id = 'xmltv_channels_' + re.sub(r'[^A-Za-z0-9_]+', '_', cache_key or str(abs(hash(url))))[:80]
    if not force_refresh:
        try:
            cache = load_cache()
            cached = cache.get('manual_epg_channels:' + cache_id)
            if isinstance(cached, dict) and int(time.time()) - int(cached.get('time', 0)) < EPG_TTL_SECONDS:
                data = cached.get('data')
                if isinstance(data, list) and data:
                    return [(str(a), str(b)) for a, b in data if a]
        except Exception:
            pass
    raw, used_url, error = _download_epg_source_bytes(url, progress=progress, force_refresh=force_refresh)
    if not raw:
        log(f'Manual EPG channel list returned no data: {redact_url(url)} error={error}', xbmc.LOGWARNING)
        return []
    choices = _parse_xmltv_channels_fast(raw, progress=progress)
    if choices:
        metadata_cache_set('epg_source_channels', cache_id, {'items': choices, 'used_url': used_url})
        # metadata_cache_set only stores dicts, so also keep old list cache via
        # normal cache file for compatibility with previous versions.
        try:
            cache = load_cache()
            cache['manual_epg_channels:' + cache_id] = {'time': int(time.time()), 'data': choices, 'used_url': used_url}
            save_cache(cache)
        except Exception:
            pass
    return choices

def manual_epg_manager_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "EPG Manager")
    data = manual_epg_load()
    count = len(data.get("channels") or {})
    source_count = len([s for s in (data.get("sources") or {}).values() if isinstance(s, dict) and s.get("url")])
    add_folder(f"EPG Sources ({source_count})", "manual_epg_sources", plot="View built-in and custom XMLTV sources. Sky GO NZ is included by default.")
    add_action("Refresh EPG Sources", "manual_epg_refresh_sources", plot="Download and cache enabled EPG sources now.")
    add_folder("Assign EPG by Live TV Category", "manual_epg_live_categories", plot="Choose a Live TV category, choose a Bang TV channel, then choose the matching EPG channel from Sky GO NZ or another XMLTV source.")
    add_action("Assign EPG by channel ID", "manual_epg_assign_prompt", plot="Enter a Live TV stream ID, choose an XMLTV source, then choose the matching EPG channel.")
    add_folder(f"Channel Assignments ({count})", "manual_epg_assignments", plot="View and clear manually assigned EPG channel mappings.")
    add_folder("Unassigned Channels", "manual_epg_unassigned", plot="Show cached Live TV channels that do not have a manual EPG assignment.")
    add_folder("Missing EPG", "manual_epg_missing", plot="Show channels where no current EPG programme could be found.")
    add_folder("Recently Assigned Channels", "manual_epg_recent", plot="Show recently mapped EPG channels.")
    add_action("Add Custom XMLTV Source URL", "manual_epg_add_source", plot="Add any XMLTV URL, including .xml or .xml.gz feeds, then use it for manual channel mapping.")
    add_action("Export EPG Mappings", "manual_epg_export", plot="Choose where to save your EPG mapping JSON file.")
    add_action("Import EPG Mappings", "manual_epg_import", plot="Choose a saved EPG mapping JSON file to restore.")
    add_action("Clear all manual EPG assignments", "manual_epg_clear_all", plot="Removes all manual EPG channel links. Does not delete normal EPG cache.")
    xbmcplugin.endOfDirectory(HANDLE)


def cached_live_channel_choices(limit: int = 1000) -> List[Dict[str, Any]]:
    """Return cached Live TV channels for EPG assignment pickers."""
    seen: Dict[str, Dict[str, Any]] = {}
    try:
        for item in recent_live_load():
            sid = str(item.get("stream_id") or item.get("live_id") or "")
            if sid:
                seen[sid] = {"stream_id": sid, "name": item.get("name") or sid, "thumb": item.get("thumb") or item.get("stream_icon") or ""}
    except Exception:
        pass
    try:
        cache = load_cache()
        for val in cache.values() if isinstance(cache, dict) else []:
            if isinstance(val, list):
                for item in val:
                    if not isinstance(item, dict):
                        continue
                    sid = str(item.get("stream_id") or item.get("live_id") or "")
                    if sid:
                        seen.setdefault(sid, item)
    except Exception as exc:
        log(f"Could not build cached Live TV channel picker: {exc}", xbmc.LOGWARNING)
    items = sorted(seen.values(), key=lambda x: str(x.get("name") or x.get("stream_id") or "").lower())
    return items[:limit]


def _load_live_categories_for_epg_manager() -> List[Dict[str, Any]]:
    url = xc_api_url("player_api.php?action=get_live_categories")
    data = get_cached_json_any_age(url)
    if data is None:
        data = http_get_json_with_progress(url, "Loading Live TV categories...", timeout=25, force_refresh=False)
    return data if isinstance(data, list) else []


def _load_live_channels_for_epg_manager(cat_id: str, title: str = "") -> List[Dict[str, Any]]:
    endpoint = f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}" if cat_id else "player_api.php?action=get_live_streams"
    url = xc_api_url(endpoint)
    data = get_cached_json_any_age(url)
    if data is None:
        data = http_get_json_with_progress(url, f"Loading channels for {title or 'category'}...", timeout=30, force_refresh=False)
    return data if isinstance(data, list) else []


def manual_epg_live_categories_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Assign EPG by Category")
    xbmcplugin.setContent(HANDLE, "videos")
    cats = _load_live_categories_for_epg_manager()
    if not cats:
        add_action("No Live TV categories found. Open Live TV first, then try again.", "manual_epg_manager")
    else:
        add_folder("All Live TV Channels", "manual_epg_live_channels", {"cat_id": "", "title": "All Live TV Channels"}, plot="Show all cached/live channels, then choose one to map to an EPG channel.")
        for cat in sorted_items(cats, "category_name"):
            cid = str(cat.get("category_id") or "")
            name = str(cat.get("category_name") or "Unknown")
            if cid and not hidden_live_is_hidden(cid):
                add_folder(name, "manual_epg_live_channels", {"cat_id": cid, "title": name}, plot="Open this category, choose a Bang TV channel, then select the EPG channel to assign.")
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_live_channels_menu(cat_id: str, title: str = "") -> None:
    title = title or "Live TV Channels"
    xbmcplugin.setPluginCategory(HANDLE, f"Assign EPG: {title}")
    xbmcplugin.setContent(HANDLE, "videos")
    channels = _load_live_channels_for_epg_manager(cat_id, title)
    if not channels:
        add_action("No channels found in this category", "manual_epg_live_categories", plot="Open Live TV first or refresh this category, then try again.")
    else:
        for item in sorted_items(channels, "name")[:3000]:
            sid = str(item.get("stream_id") or item.get("live_id") or "")
            name = str(item.get("name") or sid or "Live TV Channel")
            icon = str(item.get("stream_icon") or item.get("thumbnail") or "")
            if not sid:
                continue
            current = get_manual_epg_assignment({"stream_id": sid, "name": name})
            suffix = ""
            plot = "Choose this Bang TV channel, then choose the EPG source and EPG channel to link to it."
            if current:
                suffix = "  [EPG linked]"
                plot += f"\n\nCurrent EPG: {current.get('source_label') or current.get('source_id')} → {current.get('channel_label') or current.get('channel_id')}"
            add_folder(name + suffix, "manual_epg_sources_for_channel", {"stream_id": sid, "name": name, "cat_id": cat_id, "title": title}, thumb=icon, plot=plot)
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_sources_for_channel_menu(stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    xbmcplugin.setPluginCategory(HANDLE, f"EPG Source for {name}")
    xbmcplugin.setContent(HANDLE, "videos")
    data = manual_epg_load()
    sources = data.get("sources") or {}
    add_action("Automatic EPG", "manual_epg_clear_channel", {"stream_id": stream_id, "name": name}, plot="Remove manual override and use automatic EPG matching.")
    for sid, src in sorted(sources.items(), key=lambda kv: str((kv[1] or {}).get("label") or kv[0]).lower()):
        if not isinstance(src, dict):
            continue
        label = str(src.get("label") or sid)
        url = str(src.get("url") or "")
        if not url:
            continue
        plot = f"Open {label}, load its XMLTV channels with a progress dialog, then choose the EPG channel to assign to {name}.\n\nURL: {url}"
        add_folder(f"{'⭐ ' if sid == 'skygo' else ''}{label}", "manual_epg_source_channels_for_channel", {"source_id": sid, "stream_id": stream_id, "name": name, "cat_id": cat_id, "title": title}, plot=plot)
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_source_channels_for_channel_menu(source_id: str, stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id)
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    xbmcplugin.setPluginCategory(HANDLE, f"{label} EPG Channels")
    xbmcplugin.setContent(HANDLE, "videos")
    if not url:
        add_action("EPG source has no URL", "manual_epg_sources_for_channel", {"stream_id": stream_id, "name": name})
        xbmcplugin.endOfDirectory(HANDLE)
        return
    progress = xbmcgui.DialogProgress()
    progress_create(progress, ADDON_NAME, f"Loading {label} EPG channels...", "Downloading XMLTV data")
    try:
        choices = xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=True, progress=progress)
        try:
            progress_update(progress, 100, "EPG channels loaded", f"Found {len(choices)} channels")
        except Exception:
            pass
    finally:
        try:
            progress.close()
        except Exception:
            pass
    add_action(f"Loaded EPG channels: {len(choices)}", "manual_epg_source_info", {"source_id": source_id}, plot=f"Source: {label}\nURL: {url}")
    if not choices:
        add_action("No EPG channels found. Check the EPG URL or try Refresh EPG Sources.", "manual_epg_manager")
    else:
        target = norm_epg_key(name)
        def score(pair):
            cid, lbl = pair
            key = norm_epg_key(lbl)
            if target and key == target:
                return (0, lbl.lower())
            if target and (target in key or key in target):
                return (1, lbl.lower())
            return (2, lbl.lower())
        for ch_id, ch_label in sorted(choices, key=score)[:3000]:
            plot = f"Assign EPG channel:\n{ch_label}\n\nEPG ID: {ch_id}\n\nTo Bang TV channel:\n{name}"
            add_action(str(ch_label), "manual_epg_assign_to_stream", {"source_id": source_id, "channel_id": ch_id, "channel_label": ch_label, "stream_id": stream_id, "name": name, "cat_id": cat_id, "title": title}, plot=plot)
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_assign_to_stream(source_id: str, channel_id: str, channel_label: str, stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    source_id = str(source_id or "")
    channel_id = str(channel_id or "")
    channel_label = str(channel_label or channel_id)
    stream_id = str(stream_id or "")
    name = str(name or stream_id or "Live TV Channel")
    if not stream_id or not channel_id:
        notify("Missing channel or EPG ID", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    source_label = str(src.get("label") or source_id)
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    key = manual_epg_channel_key(stream_id, name)
    data.setdefault("channels", {})[key] = {
        "stream_id": stream_id,
        "name": name,
        "source_id": source_id,
        "source_label": source_label,
        "url": url,
        "channel_id": channel_id,
        "channel_label": channel_label,
        "updated": int(time.time()),
    }
    manual_epg_save(data)
    add_bang_notification(f"Manual EPG assigned: {name} → {channel_label}", "Updates")
    add_activity(f"Manual EPG assigned for {name}", "updates")
    xbmcgui.Dialog().ok(ADDON_NAME, f"EPG assigned\n\n{name}\n→ {channel_label}")
    xbmc.executebuiltin("Container.Refresh")


def manual_epg_clear_channel(stream_id: str, name: str = "") -> None:
    data = manual_epg_load()
    key = manual_epg_channel_key(stream_id, name)
    removed = False
    if key in (data.get("channels") or {}):
        data["channels"].pop(key, None)
        removed = True
    name_key = manual_epg_channel_key("", name)
    if name_key in (data.get("channels") or {}):
        data["channels"].pop(name_key, None)
        removed = True
    manual_epg_save(data)
    notify("Manual EPG cleared" if removed else "No manual EPG override found")
    xbmc.executebuiltin("Container.Refresh")


def manual_epg_sources_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "EPG Sources")
    data = manual_epg_load()
    sources = data.get("sources") or {}
    for sid, src in sorted(sources.items(), key=lambda kv: str((kv[1] or {}).get("label") or kv[0]).lower()):
        if not isinstance(src, dict):
            continue
        label = str(src.get("label") or sid)
        url = str(src.get("url") or "")
        if not url:
            continue
        enabled = bool(src.get("enabled", True))
        built = "Built-in" if src.get("builtin") else "Custom"
        status = "Enabled" if enabled else "Disabled"
        plot = f"{built} EPG source\nStatus: {status}\nURL: {url}\n\nOpen this source to load its XMLTV channels, then pick one and assign it to a Bang TV channel."
        add_folder(f"{'⭐ ' if sid == 'skygo' else ''}{label} [{status}]", "manual_epg_source_channels", {"source_id": sid}, plot=plot)
    add_action("Add Custom XMLTV Source URL", "manual_epg_add_source")
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_source_info(source_id: str) -> None:
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id)
    url = str(src.get("url") or "")
    guide = xmltv_guide_data(url, "source_info_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80]) if url else {}
    channels = guide.get("channels") if isinstance(guide, dict) else {}
    text = f"{label}\n\nURL:\n{url}\n\nStatus: {'Enabled' if src.get('enabled', True) else 'Disabled'}\nType: {'Built-in' if src.get('builtin') else 'Custom'}\nChannel count: {len(channels) if isinstance(channels, dict) else 0}\n\nOpen this source to view all EPG channels and assign one to a Bang TV Live TV channel."
    xbmcgui.Dialog().textviewer("EPG Source", text)


def manual_epg_source_channels_menu(source_id: str) -> None:
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id)
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    xbmcplugin.setPluginCategory(HANDLE, f"{label} EPG Channels")
    if not url:
        add_action("EPG source has no URL", "manual_epg_sources")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    progress = xbmcgui.DialogProgress()
    progress_create(progress, ADDON_NAME, "Loading EPG channels...", label)
    try:
        choices = xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=True, progress=progress)
    finally:
        try:
            progress.close()
        except Exception:
            pass
    add_action("Source info", "manual_epg_source_info", {"source_id": source_id}, plot=f"View URL and channel count for {label}.")
    add_action("Refresh this EPG source", "manual_epg_refresh_one_source", {"source_id": source_id}, plot="Force refresh this XMLTV feed now.")
    if choices:
        add_action(f"EPG channels loaded: {len(choices)}", "manual_epg_source_info", {"source_id": source_id}, plot="This source loaded successfully. Choose any EPG channel below to assign it to a Bang TV channel.")
    if not choices:
        add_action("No EPG channels found. Press Refresh this EPG source, or check the URL.", "manual_epg_sources")
    else:
        for ch_id, ch_label in choices[:2000]:
            add_action(str(ch_label), "manual_epg_assign_from_source_channel", {"source_id": source_id, "channel_id": ch_id, "channel_label": ch_label}, plot=f"EPG channel ID: {ch_id}\nSelect this, then choose the Bang TV channel to link it to.")
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_refresh_one_source(source_id: str) -> None:
    url = manual_epg_source_url(source_id)
    if not url:
        notify("No EPG source URL", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    progress = xbmcgui.DialogProgress()
    progress_create(progress, ADDON_NAME, "Refreshing EPG source...", source_id)
    try:
        xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=True, progress=progress)
    finally:
        try:
            progress.close()
        except Exception:
            pass
    notify("EPG source refreshed")
    add_bang_notification(f"EPG source refreshed: {source_id}", "Updates")


def manual_epg_assign_from_source_channel(source_id: str, channel_id: str, channel_label: str) -> None:
    source_id = str(source_id or "")
    channel_id = str(channel_id or "")
    channel_label = str(channel_label or channel_id)
    url = manual_epg_source_url(source_id)
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    source_label = str(src.get("label") or ("Provider XMLTV" if source_id == "xtream" else source_id))
    live_items = cached_live_channel_choices()
    if not live_items:
        notify("No cached Live TV channels yet", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcgui.Dialog().ok(ADDON_NAME, "Open Live TV first so Bang TV can cache your channels, then come back and assign the EPG channel.")
        return
    names = []
    default_idx = 0
    target = norm_epg_key(channel_label)
    for i, item in enumerate(live_items):
        nm = str(item.get("name") or item.get("stream_id") or "Live TV Channel")
        names.append(nm)
        nkey = norm_epg_key(nm)
        if target and (target in nkey or nkey in target) and default_idx == 0:
            default_idx = i
    idx = xbmcgui.Dialog().select(f"Assign '{channel_label}' to Bang TV channel", names, preselect=default_idx)
    if idx < 0:
        notify("EPG assignment cancelled")
        return
    item = live_items[idx]
    sid = str(item.get("stream_id") or item.get("live_id") or "")
    channel_name = str(item.get("name") or sid)
    if not sid:
        notify("Selected Bang TV channel has no stream ID", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    key = manual_epg_channel_key(sid, channel_name)
    data.setdefault("channels", {})[key] = {
        "stream_id": sid,
        "name": channel_name,
        "source_id": source_id,
        "source_label": source_label,
        "url": url,
        "channel_id": channel_id,
        "channel_label": channel_label,
        "updated": int(time.time()),
    }
    manual_epg_save(data)
    add_bang_notification(f"Manual EPG assigned: {channel_name} → {channel_label}", "Updates")
    add_activity(f"Manual EPG assigned for {channel_name}", "updates")
    notify(f"EPG linked to {channel_name}")
    xbmc.executebuiltin("Container.Refresh")


def manual_epg_refresh_sources() -> None:
    data = manual_epg_load()
    sources = [(sid, src) for sid, src in (data.get("sources") or {}).items() if isinstance(src, dict) and src.get("url") and src.get("enabled", True)]
    if not sources:
        notify("No enabled EPG sources")
        return
    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, "Refreshing EPG sources...")
    refreshed = 0
    try:
        for i, (sid, src) in enumerate(sources):
            if progress.iscanceled():
                break
            label = str(src.get("label") or sid)
            progress.update(int((i / max(1, len(sources))) * 100), "Refreshing EPG", label)
            xmltv_guide_data(str(src.get("url") or ""), "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", str(sid))[:80])
            refreshed += 1
    finally:
        try:
            progress.close()
        except Exception:
            pass
    add_bang_notification(f"EPG sources refreshed: {refreshed}", "Updates")
    add_activity(f"EPG sources refreshed: {refreshed}", "updates")
    notify(f"EPG sources refreshed: {refreshed}")


def manual_epg_export() -> None:
    data = manual_epg_load()
    folder = xbmcgui.Dialog().browse(0, "Choose folder to save EPG mappings", "files")
    if not folder:
        notify("Export cancelled")
        return
    filename = f"BangTV_EPG_Mappings_{time.strftime('%Y-%m-%d_%H%M')}.json"
    path = os.path.join(folder, filename)
    write_json_file(path, data)
    notify("EPG mappings exported")


def manual_epg_import() -> None:
    path = xbmcgui.Dialog().browse(1, "Choose EPG mappings JSON", "files", mask=".json")
    if not path:
        notify("Import cancelled")
        return
    data = read_json_file(path, {})
    if not isinstance(data, dict):
        notify("Invalid EPG mapping file", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    current = manual_epg_load()
    current["sources"].update(data.get("sources") or {})
    current["channels"].update(data.get("channels") or {})
    manual_epg_save(ensure_builtin_epg_sources(current))
    notify("EPG mappings imported")
    xbmc.executebuiltin("Container.Refresh")


def manual_epg_recent_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Recently Assigned EPG")
    data = manual_epg_load()
    rows = []
    for key, val in (data.get("channels") or {}).items():
        if isinstance(val, dict):
            rows.append((int(val.get("updated", 0) or 0), key, val))
    rows.sort(reverse=True)
    for _ts, key, val in rows[:50]:
        plot = f"Source: {val.get('source_label') or val.get('source_id')}\nEPG channel: {val.get('channel_label') or val.get('channel_id')}\nUpdated: {nice_time(int(val.get('updated', 0) or 0))}"
        add_action(str(val.get("name") or key), "manual_epg_clear_one", {"key": key}, plot=plot)
    if not rows:
        add_action("No recently assigned EPG channels", "manual_epg_manager")
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_unassigned_menu(missing_only: bool = False) -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Missing EPG" if missing_only else "Unassigned Channels")
    # Use recently watched and cached category channels as a lightweight source list.
    seen = {}
    for item in recent_live_load():
        sid = str(item.get("stream_id") or "")
        if sid:
            seen[sid] = {"stream_id": sid, "name": item.get("name") or sid, "thumb": item.get("thumb") or ""}
    cache = load_cache()
    for val in cache.values() if isinstance(cache, dict) else []:
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    sid = str(item.get("stream_id") or item.get("live_id") or "")
                    if sid:
                        seen.setdefault(sid, item)
    added = 0
    for sid, item in sorted(seen.items(), key=lambda kv: str(kv[1].get("name") or kv[0]).lower()):
        if get_manual_epg_assignment(item):
            continue
        if missing_only and live_item_epg_from_map(item, combined_epg_map_for_live_items([item])).get("plot"):
            continue
        add_action(f"Assign: {item.get('name') or sid}", "manual_epg_assign", {"stream_id": sid, "name": item.get("name") or sid}, plot="No manual EPG assignment saved for this channel.")
        added += 1
        if added >= 200:
            break
    if not added:
        add_action("No channels found here yet", "manual_epg_manager")
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_assignments_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Manual EPG Assignments")
    data = manual_epg_load()
    channels = data.get("channels") or {}
    if not channels:
        add_action("No manual EPG assignments yet", "manual_epg_manager")
    for key, val in sorted(channels.items()):
        if not isinstance(val, dict):
            continue
        label = val.get("name") or key
        plot = f"Stream: {val.get('stream_id') or key}\nEPG source: {val.get('source_label') or val.get('source_id')}\nEPG channel: {val.get('channel_label') or val.get('channel_id')}"
        add_action(f"Clear: {label}", "manual_epg_clear_one", {"key": key}, plot=plot)
    xbmcplugin.endOfDirectory(HANDLE)


def manual_epg_add_source() -> None:
    url = xbmcgui.Dialog().input("Custom XMLTV URL", type=xbmcgui.INPUT_ALPHANUM).strip()
    if not url:
        notify("No EPG URL added")
        return
    label = xbmcgui.Dialog().input("Source name", defaultt="Custom EPG", type=xbmcgui.INPUT_ALPHANUM).strip() or "Custom EPG"
    data = manual_epg_load()
    source_id = "custom_" + str(int(time.time()))
    data.setdefault("sources", {})[source_id] = {"label": label, "url": url, "added": int(time.time())}
    manual_epg_save(data)
    notify("Custom EPG source added")
    add_bang_notification(f"Custom EPG source added: {label}", "Updates")


def manual_epg_source_select() -> Tuple[str, str, str]:
    data = manual_epg_load()
    options: List[Tuple[str, str, str]] = []
    provider_url = xtream_xmltv_url()
    if provider_url:
        options.append(("xtream", "Provider XMLTV", provider_url))
    seen = set(["xtream"])
    for sid, src in (data.get("sources") or {}).items():
        if not isinstance(src, dict):
            continue
        url = str(src.get("url") or "")
        if not url or sid in seen:
            continue
        seen.add(str(sid))
        options.append((str(sid), str(src.get("label") or sid), url))
    filtered = [o for o in options if o[2]]
    if not filtered:
        return "", "", ""
    labels = [o[1] for o in filtered]
    idx = xbmcgui.Dialog().select("Choose EPG source", labels)
    if idx < 0:
        return "", "", ""
    return filtered[idx]


def manual_epg_assign(stream_id: str = "", name: str = "") -> None:
    sid = str(stream_id or "").strip()
    if not sid:
        sid = xbmcgui.Dialog().input("Live TV stream ID", type=xbmcgui.INPUT_NUMERIC).strip()
    if not sid:
        notify("No stream ID entered")
        return
    channel_name = name or xbmcgui.Dialog().input("Channel name", defaultt="Live TV Channel", type=xbmcgui.INPUT_ALPHANUM).strip() or sid
    source_id, source_label, url = manual_epg_source_select()
    if not url:
        notify("EPG assignment cancelled")
        return
    progress = xbmcgui.DialogProgress()
    progress_create(progress, ADDON_NAME, "Loading EPG channels...", source_label)
    try:
        choices = xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80])
    finally:
        try:
            progress.close()
        except Exception:
            pass
    if not choices:
        notify("No XMLTV channels found", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    names = [f"{label}  [{ch_id}]" for ch_id, label in choices]
    # Try to jump close to likely match.
    default_idx = 0
    target = norm_epg_key(channel_name)
    for i, (_cid, label) in enumerate(choices):
        if target and (target in norm_epg_key(label) or norm_epg_key(label) in target):
            default_idx = i
            break
    idx = xbmcgui.Dialog().select("Choose matching EPG channel", names, preselect=default_idx)
    if idx < 0:
        notify("EPG assignment cancelled")
        return
    ch_id, ch_label = choices[idx]
    data = manual_epg_load()
    key = manual_epg_channel_key(sid, channel_name)
    data.setdefault("channels", {})[key] = {
        "stream_id": sid,
        "name": channel_name,
        "source_id": source_id,
        "source_label": source_label,
        "url": url,
        "channel_id": ch_id,
        "channel_label": ch_label,
        "updated": int(time.time()),
    }
    manual_epg_save(data)
    add_bang_notification(f"Manual EPG assigned: {channel_name} → {ch_label}", "Updates")
    add_activity(f"Manual EPG assigned for {channel_name}", "updates")
    notify("Manual EPG assigned")
    xbmc.executebuiltin("Container.Refresh")


def manual_epg_clear_one(key: str) -> None:
    data = manual_epg_load()
    if key in (data.get("channels") or {}):
        data["channels"].pop(key, None)
        manual_epg_save(data)
        notify("Manual EPG assignment cleared")
    xbmc.executebuiltin("Container.Refresh")


def manual_epg_clear_all() -> None:
    if not xbmcgui.Dialog().yesno(ADDON_NAME, "Clear all manual EPG assignments?"):
        return
    data = manual_epg_load()
    data["channels"] = {}
    manual_epg_save(data)
    notify("Manual EPG assignments cleared")
    xbmc.executebuiltin("Container.Refresh")


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
        "notifications": read_json_file(NOTIFICATIONS_FILE, []),
        "activity_log": read_json_file(ACTIVITY_LOG_FILE, []),
        "statistics": read_json_file(STATISTICS_FILE, {}),
        "manual_epg": manual_epg_load(),
        "manual_epg_sources": (manual_epg_load().get("sources") or {}),
        "manual_epg_channels": (manual_epg_load().get("channels") or {}),
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
    if isinstance(data.get("notifications"), list):
        write_json_file(NOTIFICATIONS_FILE, data.get("notifications"))
    if isinstance(data.get("activity_log"), list):
        write_json_file(ACTIVITY_LOG_FILE, data.get("activity_log"))
    if isinstance(data.get("statistics"), dict):
        write_json_file(STATISTICS_FILE, data.get("statistics"))
    add_bang_notification("Quick backup restored", "Maintenance")
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
    # v1.0.52: prefetch the whole visible page before Kodi displays Movies/TV Shows.
    # This keeps Android TV fast because only the current page is prepared, while
    # the rest of the library stays queued for the background metadata worker.
    fetch_limit = min(limit, FAST_PREVIEW_FETCH_LIMIT)
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
    if len(missing) > fetch_limit:
        enqueue_background_metadata(content_type, missing[fetch_limit:], priority=False)
        missing = missing[:fetch_limit]

    label = "movies" if content_type == "vod" else "TV shows" if content_type == "series" else "episodes"
    progress = xbmcgui.DialogProgress()
    try:
        try:
            progress.create(ADDON_NAME, f"Preparing {label} page...", "Getting metadata for visible items")
        except TypeError:
            progress.create(ADDON_NAME, f"Preparing {label} page...")
        total = len(missing)
        for index, item_id in enumerate(missing, start=1):
            if progress and progress.iscanceled():
                enqueue_background_metadata(content_type, missing[index-1:], priority=True)
                break
            if progress:
                percent = int((index - 1) * 100 / max(total, 1))
                try:
                    progress.update(percent, f"Getting {label} metadata", f"Item {index} of {total}")
                except TypeError:
                    progress.update(percent, f"Getting {label} metadata, item {index} of {total}")
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
        if progress:
            try:
                progress.update(100, "Metadata ready", f"Prepared {len(results)} {label} items")
            except TypeError:
                progress.update(100, f"Metadata ready for {label}")
    finally:
        try:
            if progress:
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
    data = http_get_json(xc_api_url(f"player_api.php?action=get_short_epg&stream_id={quote(stream_id)}&limit=2"), timeout=3, use_cache=True, silent=True, ttl=EPG_TTL_SECONDS)
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
    if not xbmcgui.Dialog().yesno(ADDON_NAME, "Log out and clear the saved Bang TV username and password?"):
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
        context_items.append(("Assign EPG to this channel", f'RunPlugin({build_url({"mode": "manual_epg_assign", "stream_id": str(live_stream_id), "name": name, "cat_id": live_category_id or ""})})'))
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
    manual = get_manual_epg_assignment(item)
    if manual.get("channel_id"):
        return [str(manual.get("channel_id"))]
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
    manual = get_manual_epg_assignment(item)
    if manual:
        manual_guide = manual_epg_guide_for_assignment(manual)
        if manual_guide:
            guide = manual_guide
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



def remove_disabled_export_files(show_notice: bool = False) -> bool:
    """Remove old external guide export files. Bang TV now keeps TV Guide inside the add-on only."""
    removed = 0
    for path in REMOVED_EXPORT_FILES:
        try:
            if os.path.exists(path):
                os.remove(path)
                removed += 1
        except Exception as exc:
            log(f"Could not remove old export file {path}: {exc}", xbmc.LOGWARNING)
    if show_notice:
        notify("Old PVR/IPTV export files removed" if removed else "No PVR/IPTV export files found")
    return True


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
    """A TiviMate-style visual guide rendered inside the add-on.

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
    """Skin-safe TV Guide landing page.

    This must use folder items, not action items, because the guide screens are
    directories. Some Kodi skins will not open a directory properly if the item
    was added as non-folder/playable.
    """
    xbmcplugin.setPluginCategory(HANDLE, "TV Guide")
    xbmcplugin.setContent(HANDLE, "videos")
    add_folder("[B]All Channels Guide[/B]", "tv_guide_category", {"cat_id": "", "title": "All Channels"}, ADDON_ICON, "Open the Bang TV guide using normal Kodi folder controls. Works on all skins.")
    add_folder("Visual Grid Guide (experimental)", "tv_guide_visual", {"cat_id": "", "title": "All Channels"}, ADDON_ICON, "Optional experimental visual guide. Use the normal guide if your skin does not show it properly.")

    data = get_cached_json_any_age(xc_api_url("player_api.php?action=get_live_categories"))
    if data is None:
        data = http_get_json_with_progress(xc_api_url("player_api.php?action=get_live_categories"), "Loading TV Guide categories...", timeout=25, force_refresh=False)

    if isinstance(data, list) and data:
        for cat in sorted_items(data, "category_name"):
            name = cat.get("category_name") or "Unknown"
            cat_id = str(cat.get("category_id") or "")
            if cat_id and not hidden_live_is_hidden(cat_id):
                add_folder(name, "tv_guide_category", {"cat_id": cat_id, "title": name}, cat.get("stream_icon") or ADDON_ICON, "Open this category in the Bang TV guide.")
    else:
        add_action("No guide categories found. Open Live TV or Refresh Live TV first.", "tv_guide")
    xbmcplugin.endOfDirectory(HANDLE)


def tv_guide_grid_label(channel_name: str, rows: List[Dict[str, Any]]) -> str:
    """Build a TiviMate-inspired row label that stays inside Kodi plugin lists."""
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
    # Do not force-download or parse the full XMLTV guide just to open this list.
    # That made the guide look broken or very slow on some skins. Use cached EPG
    # if available, otherwise show the channels immediately and fill EPG later.
    guide = get_cached_metadata_any_age("epg_guide", "xtream_7day_guide") or {"channels": {}, "programmes": {}}
    try:
        if str(cat_id or "") in SKYGO_EPG_CATEGORY_IDS or any(is_sky_sport_nz_live_item(i, title or "", cat_id) for i in data):
            sky_guide = get_cached_metadata_any_age("epg_guide", "skygo_7day_guide") or xmltv_guide_data(SKYGO_EPG_URL, "skygo_7day_guide")
            if isinstance(sky_guide, dict) and sky_guide.get("programmes"):
                merged_channels = dict(guide.get("channels") or {})
                merged_channels.update(sky_guide.get("channels") or {})
                merged_programmes = dict(guide.get("programmes") or {})
                merged_programmes.update(sky_guide.get("programmes") or {})
                guide = {"channels": merged_channels, "programmes": merged_programmes}
    except Exception as exc:
        log(f"SkyGo guide merge failed: {exc}", xbmc.LOGWARNING)
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
    if is_sky_sport_nz_live_item(item, title or "", cat_id):
        try:
            sky_guide = xmltv_guide_data(SKYGO_EPG_URL, "skygo_7day_guide")
            if isinstance(sky_guide, dict) and sky_guide.get("programmes"):
                merged_channels = dict(guide.get("channels") or {})
                merged_channels.update(sky_guide.get("channels") or {})
                merged_programmes = dict(guide.get("programmes") or {})
                merged_programmes.update(sky_guide.get("programmes") or {})
                guide = {"channels": merged_channels, "programmes": merged_programmes}
        except Exception as exc:
            log(f"SkyGo 7 day channel guide failed: {exc}", xbmc.LOGWARNING)
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
        # SQLite-first: open saved categories instantly when available. The
        # background checker keeps them fresh and only calls the API when due.
        data = get_cached_json_any_age(url) or live_db_load_categories()
        if not isinstance(data, list) or not data:
            data = http_get_json_with_progress(url, "Loading Live TV categories...", timeout=25)
        if isinstance(data, list):
            live_db_upsert_categories(data)
    elif action == "get_vod_categories":
        data = get_cached_json_any_age(url) or library_db_load_categories("vod")
        if not isinstance(data, list) or not data:
            data = http_get_json_with_progress(url, "Loading Movie categories...", timeout=25)
        if isinstance(data, list):
            library_db_upsert_categories("vod", data)
    elif action == "get_series_categories":
        data = get_cached_json_any_age(url) or library_db_load_categories("series")
        if not isinstance(data, list) or not data:
            data = http_get_json_with_progress(url, "Loading TV Show categories...", timeout=25)
        if isinstance(data, list):
            library_db_upsert_categories("series", data)
    elif content_type in ("vod", "series"):
        data = get_cached_json_any_age(url) or library_db_load_items(content_type, cat_id)
        if not isinstance(data, list) or not data:
            label = "Loading Movies..." if content_type == "vod" else "Loading TV Shows..."
            data = http_get_json_with_progress(url, label, timeout=30)
        if isinstance(data, list) and data:
            library_db_upsert_items(content_type, data, cat_id)
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
        data = get_cached_json_any_age(url) or live_db_load_channels(cat_id)
        if data is None or not isinstance(data, list) or not data:
            data = http_get_json_with_progress(url, "Loading Live TV channels...", timeout=25, force_refresh=True)
        if isinstance(data, list) and data:
            live_db_upsert_channels(data, cat_id)
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
        # Use cached 7-day XMLTV only. Do not download/parse XMLTV while opening folders.
        live_xmltv_epg = cached_xmltv_epg_map("xtream_live")
        if not live_xmltv_epg and page == 1:
            notify("EPG is still downloading in the background")

    user, pwd, _label = get_effective_creds()
    live_boost_remaining = live_startup_epg_boost_count() if content_type == "live" and page == 1 and not live_xmltv_epg else 0
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
            epg = live_item_epg_from_map(item, live_xmltv_epg) or live_epg_cached_only(stream_id)
            # First-login safety net: if the background EPG cache is empty, fetch only a few
            # visible channel rows so EPG starts appearing without making Android TV sluggish.
            if not epg and live_boost_remaining > 0:
                epg = live_epg(stream_id)
                live_boost_remaining -= 1
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
    recent_url = xc_api_url("player_api.php?action=get_vod_streams")
    data = get_cached_json_any_age(recent_url) or library_db_recent_vod(300)
    if not isinstance(data, list) or not data:
        data = http_get_json_with_progress(recent_url, "Loading Recently Added Movies...", timeout=30)
    if isinstance(data, list) and data:
        library_db_upsert_items("vod", data, "")
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



def add_activity(message: str, kind: str = "info") -> None:
    """Append a small local activity record for the Bang TV Control Centre."""
    try:
        items = read_json_file(ACTIVITY_LOG_FILE, [])
        if not isinstance(items, list):
            items = []
        items.insert(0, {"time": int(time.time()), "kind": kind, "message": str(message or "")})
        write_json_file(ACTIVITY_LOG_FILE, items[:300])
    except Exception as exc:
        log(f"Activity log write failed: {exc}", xbmc.LOGWARNING)


def add_bang_notification(message: str, kind: str = "Updates", level: str = "info") -> None:
    """Store an in-add-on notification so updates are not missed."""
    try:
        items = read_json_file(NOTIFICATIONS_FILE, [])
        if not isinstance(items, list):
            items = []
        items.insert(0, {"time": int(time.time()), "kind": kind, "level": level, "message": str(message or ""), "read": False})
        write_json_file(NOTIFICATIONS_FILE, items[:200])
        add_activity(message, kind)
    except Exception as exc:
        log(f"Notification write failed: {exc}", xbmc.LOGWARNING)


def notifications_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Bang TV Notifications")
    items = read_json_file(NOTIFICATIONS_FILE, [])
    if not isinstance(items, list):
        items = []
    unread = sum(1 for i in items if isinstance(i, dict) and not i.get("read"))
    add_action(f"Mark all read ({unread} unread)", "notifications_mark_read", plot="Marks all Bang TV notifications as read.")
    add_action("Clear notifications", "notifications_clear", plot="Deletes the saved Bang TV notification inbox.")
    add_action("Export notifications", "notifications_export", plot="Lets you choose a folder and export notifications as a text file.")
    if not items:
        add_action("No notifications yet", "tools")
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        prefix = "● " if not item.get("read") else "  "
        kind = item.get("kind") or "Info"
        label = f"{prefix}{nice_time(int(item.get('time', 0) or 0))} | {kind} | {item.get('message', '')}"
        add_action(label, "notification_view", {"idx": str(items.index(item))}, plot=item.get("message") or "Bang TV notification")
    xbmcplugin.endOfDirectory(HANDLE)


def notification_view(idx: str) -> None:
    items = read_json_file(NOTIFICATIONS_FILE, [])
    try:
        i = int(idx)
        item = items[i]
        if isinstance(item, dict):
            item["read"] = True
            write_json_file(NOTIFICATIONS_FILE, items)
            xbmcgui.Dialog().textviewer("Bang TV Notification", f"{nice_time(int(item.get('time', 0) or 0))}\n{item.get('kind', 'Info')}\n\n{item.get('message', '')}")
    except Exception:
        notify("Notification not found", icon=xbmcgui.NOTIFICATION_WARNING)


def notifications_mark_read() -> None:
    items = read_json_file(NOTIFICATIONS_FILE, [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                item["read"] = True
        write_json_file(NOTIFICATIONS_FILE, items)
    notify("Notifications marked read")


def notifications_clear() -> None:
    if xbmcgui.Dialog().yesno(ADDON_NAME, "Clear all Bang TV notifications?"):
        write_json_file(NOTIFICATIONS_FILE, [])
        add_activity("Notifications cleared", "Maintenance")
        notify("Notifications cleared")


def notifications_export() -> None:
    folder = xbmcgui.Dialog().browse(3, "Choose export folder", "files")
    if not folder:
        return
    folder = xbmcvfs.translatePath(folder)
    path = os.path.join(folder, "BangTV_Notifications.txt")
    items = read_json_file(NOTIFICATIONS_FILE, [])
    lines = ["Bang TV Notifications", ""]
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            lines.append(f"{nice_time(int(item.get('time', 0) or 0))} | {item.get('kind', 'Info')} | {item.get('message', '')}")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        notify("Notifications exported")
    except Exception as exc:
        notify("Export failed", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"Notification export failed: {exc}", xbmc.LOGWARNING)


def activity_log_menu() -> None:
    items = read_json_file(ACTIVITY_LOG_FILE, [])
    if not isinstance(items, list):
        items = []
    text = "Bang TV Activity Log\n\n"
    if not items:
        text += "No activity recorded yet."
    for item in items[:200]:
        if isinstance(item, dict):
            text += f"{nice_time(int(item.get('time', 0) or 0))}\n{item.get('kind', 'Info')}: {item.get('message', '')}\n\n"
    xbmcgui.Dialog().textviewer("Bang TV Activity Log", text)


def bang_control_centre() -> None:
    stats = live_stats_summary()
    state = load_live_update_state()
    health = stream_health_load()
    notifications = read_json_file(NOTIFICATIONS_FILE, [])
    unread = sum(1 for i in notifications if isinstance(i, dict) and not i.get("read")) if isinstance(notifications, list) else 0
    ch = (state.get("last_result") or {}).get("channel_changes") if isinstance(state.get("last_result"), dict) else {}
    failing = 0
    slow = 0
    for item in health.values() if isinstance(health, dict) else []:
        if isinstance(item, dict):
            fails = int(item.get("fails", 0) or 0)
            if fails >= 3:
                failing += 1
            elif fails:
                slow += 1
    text = "Bang TV Control Centre\n\n"
    text += f"Server: {SERVER}\n"
    text += f"Last update: {nice_time(int(stats.get('newest_update', 0) or 0))}\n"
    text += f"Next update: {nice_time(int(stats.get('next_check', 0) or 0)) if stats.get('next_check') else 'When Live TV is opened'}\n"
    text += f"Categories: {stats.get('total_categories', 0)}\n"
    text += f"Cached categories: {stats.get('cached_categories', 0)}\n"
    text += f"Cached channels: {stats.get('total_channels', 0)}\n"
    text += f"Cache health: {stats.get('status', 'Unknown')}\n"
    text += f"Background updates: {'Enabled' if stats.get('background_enabled') else 'Disabled'}\n"
    text += f"High Activity Mode: {'On' if stats.get('high_activity') else 'Off'}\n"
    text += f"New channels last check: {int((ch or {}).get('added_count', 0) or 0)}\n"
    text += f"Removed channels last check: {int((ch or {}).get('removed_count', 0) or 0)}\n"
    text += f"Changed channels last check: {int((ch or {}).get('changed_count', 0) or 0)}\n"
    text += f"Stream health records: {len(health) if isinstance(health, dict) else 0}\n"
    text += f"Slow streams: {slow}\n"
    text += f"Failing streams: {failing}\n"
    text += f"Unread notifications: {unread}\n"
    text += f"Recently watched: {len(recent_live_load())}\n"
    text += f"Hidden categories: {len(hidden_live_load())}\n"
    xbmcgui.Dialog().textviewer("Bang TV Control Centre", text)


def live_tv_manager_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Live TV Manager")
    add_action("Live TV Stats", "live_stats")
    add_action("Refresh Live TV", "live_refresh")
    add_action("Force Full Rebuild", "force_full_rebuild", plot="Clears Live TV cache then downloads a fresh playlist.")
    add_action("Refresh EPG", "refresh_epg", plot="Clears EPG cache so guide info reloads fresh.")
    add_folder("Manual EPG Manager", "manual_epg_manager", plot="Manually link any Live TV channel to an XMLTV EPG source and channel ID.")
    add_action("Refresh Logos", "refresh_logos", plot="Clears old artwork and logo cache where possible.")
    add_folder("Recently Updated Categories", "recently_changed", {"view": "categories"})
    add_folder("Recently Added Channels", "recently_changed", {"view": "added"})
    add_folder("Recently Removed Channels", "recently_changed", {"view": "removed"})
    add_folder("Changed Channels", "recently_changed", {"view": "changed"})
    xbmcplugin.endOfDirectory(HANDLE)


def force_full_rebuild() -> None:
    if not xbmcgui.Dialog().yesno(ADDON_NAME, "Force a full Live TV rebuild now? This may take a moment."):
        return
    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, "Rebuilding Live TV cache...")
    try:
        cache = load_cache()
        for key in list(cache.keys()):
            if "get_live" in str(key) or "action=get_live" in str(key):
                cache.pop(key, None)
        save_cache(cache)
        smart_live_check(force=True, show_notice=True, progress=progress)
        add_bang_notification("Live TV full rebuild completed", "Maintenance")
    finally:
        try:
            progress.close()
        except Exception:
            pass


def refresh_epg() -> None:
    try:
        cache = load_cache()
        for key in list(cache.keys()):
            if "epg" in str(key).lower() or "xmltv" in str(key).lower():
                cache.pop(key, None)
        save_cache(cache)
        add_bang_notification("EPG cache refreshed", "Maintenance")
        notify("EPG refresh complete")
    except Exception as exc:
        log(f"EPG refresh failed: {exc}", xbmc.LOGWARNING)
        notify("EPG refresh failed", icon=xbmcgui.NOTIFICATION_ERROR)


def refresh_logos() -> None:
    try:
        # Plugin cannot reliably clear Kodi's global texture cache, so we clear Bang TV artwork metadata/cache only.
        cache = load_cache()
        for key in list(cache.keys()):
            if "logo" in str(key).lower() or "art" in str(key).lower() or "image" in str(key).lower():
                cache.pop(key, None)
        save_cache(cache)
        add_bang_notification("Logo and artwork cache refresh requested", "Maintenance")
        notify("Logo refresh complete")
    except Exception as exc:
        log(f"Logo refresh failed: {exc}", xbmc.LOGWARNING)
        notify("Logo refresh failed", icon=xbmcgui.NOTIFICATION_ERROR)


def recently_changed_menu(view: str = "categories") -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Recently Changed")
    state = load_live_update_state()
    result = state.get("last_result") if isinstance(state.get("last_result"), dict) else {}
    changes = result.get("channel_changes") if isinstance(result.get("channel_changes"), dict) else {}
    cat_ids = result.get("changed_category_ids") if isinstance(result.get("changed_category_ids"), list) else []
    if view == "categories":
        if not cat_ids:
            add_action("No recently changed categories", "live_tv_manager")
        for cid in cat_ids[:100]:
            add_folder(f"Category ID {cid}", "live_streams", {"cat_id": str(cid), "page": "1"})
    else:
        ids = changes.get(view if view in {"added", "removed", "changed"} else "changed", [])
        if not ids:
            add_action("No items recorded from last check", "live_tv_manager")
        for sid in ids[:200]:
            add_action(f"Stream ID {sid}", "live_tv_manager")
    xbmcplugin.endOfDirectory(HANDLE)


def maintenance_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Maintenance")
    add_action("Clean Cache", "auto_cleanup")
    add_action("Clean Logos", "refresh_logos")
    add_action("Clean Artwork", "refresh_logos")
    add_action("Vacuum Databases", "vacuum_databases")
    add_action("Remove Dead Cache", "auto_cleanup")
    add_action("Weekly Auto Maintenance", "weekly_maintenance")
    add_action("Reset Everything", "reset_everything", plot="Danger: clears user data, cache, stats, notifications and history.")
    xbmcplugin.endOfDirectory(HANDLE)


def vacuum_databases() -> None:
    ok = 0
    for path in [METADATA_DB_FILE]:
        try:
            if os.path.exists(path):
                con = sqlite3.connect(path)
                con.execute("VACUUM")
                con.close()
                ok += 1
        except Exception as exc:
            log(f"Vacuum failed for {path}: {exc}", xbmc.LOGWARNING)
    add_bang_notification(f"Database maintenance completed ({ok} database checked)", "Maintenance")
    notify("Database maintenance complete")


def weekly_maintenance() -> None:
    live_auto_cleanup(False)
    vacuum_databases()
    add_bang_notification("Weekly auto maintenance completed", "Maintenance")
    notify("Weekly maintenance complete")


def reset_everything() -> None:
    if not xbmcgui.Dialog().yesno(ADDON_NAME, "Reset Bang TV user data and cache? Login settings stay in Kodi settings, but favourites/history/cache/stats will be cleared."):
        return
    for path in [FAV_FILE, CACHE_FILE, BACKGROUND_QUEUE_FILE, STARTUP_PRELOAD_FILE, PLAY_LINKS_FILE, LIVE_UPDATE_STATE_FILE, RECENT_LIVE_FILE, HIDDEN_LIVE_CATEGORIES_FILE, STREAM_HEALTH_FILE, NOTIFICATIONS_FILE, ACTIVITY_LOG_FILE, STATISTICS_FILE]:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as exc:
            log(f"Reset could not remove {path}: {exc}", xbmc.LOGWARNING)
    notify("Bang TV reset complete")


def statistics_menu() -> None:
    stats = live_stats_summary()
    recent = recent_live_load()
    cats = {}
    for item in recent:
        cid = str(item.get("category_id") or "Unknown") if isinstance(item, dict) else "Unknown"
        cats[cid] = cats.get(cid, 0) + 1
    text = "Bang TV Statistics\n\n"
    text += f"Recently watched channels saved: {len(recent)}\n"
    text += f"Total cached channels: {stats.get('total_channels', 0)}\n"
    text += f"Total categories: {stats.get('total_categories', 0)}\n"
    text += f"Cached categories: {stats.get('cached_categories', 0)}\n"
    text += f"Most active saved category ID: {max(cats, key=cats.get) if cats else 'None'}\n"
    text += f"Stream health records: {len(stream_health_load())}\n"
    text += "\nMost recent channels:\n"
    for item in recent[:20]:
        if isinstance(item, dict):
            text += f"{nice_time(int(item.get('time', 0) or 0))}: {item.get('name', 'Unknown')}\n"
    xbmcgui.Dialog().textviewer("Bang TV Statistics", text)


def stream_health_centre() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Stream Health Centre")
    data = stream_health_load()
    add_action("Reset Health Data", "reset_stream_health")
    if not data:
        add_action("No stream health data yet", "tools")
    for sid, item in list(data.items())[:200]:
        if not isinstance(item, dict):
            continue
        fails = int(item.get("fails", 0) or 0)
        status = "🔴 Failing" if fails >= 3 else ("🟡 Slow" if fails else "🟢 Healthy")
        label = f"{status} | Stream {sid} | fails {fails}"
        plot = f"Last success: {nice_time(int(item.get('last_ok', 0) or 0))}\nLast failure: {nice_time(int(item.get('last_fail', 0) or 0))}\nReliability is based on local playback results."
        add_action(label, "tools", plot=plot)
    xbmcplugin.endOfDirectory(HANDLE)


def reset_stream_health() -> None:
    if xbmcgui.Dialog().yesno(ADDON_NAME, "Reset all stream health data?"):
        write_json_file(STREAM_HEALTH_FILE, {})
        add_bang_notification("Stream health data reset", "Maintenance")
        notify("Stream health reset")


def upcoming_sports_menu() -> None:
    # Lightweight EPG keyword view using whatever guide metadata is already cached.
    xbmcplugin.setPluginCategory(HANDLE, "Upcoming Sports")
    keywords = ["rugby", "league", "cricket", "football", "soccer", "sport", "tennis", "basketball", "race", "ufc", "fight"]
    found = 0
    cache = load_cache()
    for key, entry in cache.items():
        if found >= 100:
            break
        if not isinstance(entry, dict):
            continue
        data = entry.get("data")
        text = json.dumps(data, ensure_ascii=False).lower()[:20000]
        if any(k in text for k in keywords):
            add_action(f"Possible sport in cached guide: {str(key)[-60:]}", "tv_guide", plot="Open TV Guide to view cached programme information.")
            found += 1
    if not found:
        add_action("No upcoming sports found in cached EPG yet", "tv_guide", plot="Open channels once EPG is loaded, then this page can find sports from cached guide data.")
    xbmcplugin.endOfDirectory(HANDLE)


def backup_restore_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Backup & Restore")
    add_action("Create Backup, choose save folder", "backup_choose")
    add_action("Restore Backup, choose ZIP file", "restore_choose")
    add_action("Create Quick Backup in Kodi profile", "backup_settings")
    add_action("Restore Quick Backup from Kodi profile", "restore_settings")
    xbmcplugin.endOfDirectory(HANDLE)


def collect_backup_data() -> Dict[str, Any]:
    return {
        "created": int(time.time()),
        "addon_version": ADDON_VERSION,
        "favourites": fav_load(),
        "recent_live": recent_live_load(),
        "hidden_live_categories": hidden_live_load(),
        "stream_health": stream_health_load(),
        "live_update_state": load_live_update_state(),
        "notifications": read_json_file(NOTIFICATIONS_FILE, []),
        "activity_log": read_json_file(ACTIVITY_LOG_FILE, []),
        "statistics": read_json_file(STATISTICS_FILE, {}),
    }


def backup_choose() -> None:
    import zipfile
    folder = xbmcgui.Dialog().browse(3, "Choose where to save Bang TV backup", "files")
    if not folder:
        return
    folder = xbmcvfs.translatePath(folder)
    name = datetime.now().strftime("BangTV_Backup_%Y-%m-%d_%H%M.zip")
    path = os.path.join(folder, name)
    tmp_json = os.path.join(PROFILE_PATH, "backup_payload.json")
    try:
        write_json_file(tmp_json, collect_backup_data())
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_json, "bangtv_backup.json")
        try:
            os.remove(tmp_json)
        except Exception:
            pass
        add_bang_notification(f"Backup created: {path}", "Maintenance")
        xbmcgui.Dialog().ok(ADDON_NAME, f"Backup saved to:\n{path}")
    except Exception as exc:
        log(f"Backup failed: {exc}", xbmc.LOGWARNING)
        notify("Backup failed", icon=xbmcgui.NOTIFICATION_ERROR)


def restore_choose() -> None:
    import zipfile
    file_path = xbmcgui.Dialog().browse(1, "Choose Bang TV backup ZIP", "files", ".zip")
    if not file_path:
        return
    file_path = xbmcvfs.translatePath(file_path)
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            data = json.loads(zf.read("bangtv_backup.json").decode("utf-8"))
        choices = ["Settings/state", "Favourites", "Recently watched", "Hidden categories", "Stream health", "Notifications", "Activity log", "Statistics", "Custom EPG sources and mappings"]
        selected = xbmcgui.Dialog().multiselect("Choose what to restore", choices)
        if selected is None:
            return
        if 1 in selected and isinstance(data.get("favourites"), list): fav_save(data.get("favourites"))
        if 2 in selected and isinstance(data.get("recent_live"), list): write_json_file(RECENT_LIVE_FILE, data.get("recent_live"))
        if 3 in selected and isinstance(data.get("hidden_live_categories"), dict): write_json_file(HIDDEN_LIVE_CATEGORIES_FILE, data.get("hidden_live_categories"))
        if 4 in selected and isinstance(data.get("stream_health"), dict): write_json_file(STREAM_HEALTH_FILE, data.get("stream_health"))
        if 5 in selected and isinstance(data.get("notifications"), list): write_json_file(NOTIFICATIONS_FILE, data.get("notifications"))
        if 6 in selected and isinstance(data.get("activity_log"), list): write_json_file(ACTIVITY_LOG_FILE, data.get("activity_log"))
        if 7 in selected and isinstance(data.get("statistics"), dict): write_json_file(STATISTICS_FILE, data.get("statistics"))
        if 8 in selected:
            epg_data = data.get("manual_epg") if isinstance(data.get("manual_epg"), dict) else {}
            if not epg_data:
                epg_data = {"sources": data.get("manual_epg_sources") or {}, "channels": data.get("manual_epg_channels") or {}}
            if isinstance(epg_data, dict):
                current = manual_epg_load()
                current.setdefault("sources", {}).update(epg_data.get("sources") or {})
                current.setdefault("channels", {}).update(epg_data.get("channels") or {})
                manual_epg_save(ensure_builtin_epg_sources(current))
        if 0 in selected and isinstance(data.get("live_update_state"), dict): save_live_update_state(data.get("live_update_state"))
        add_bang_notification("Backup restored from selected ZIP", "Maintenance")
        notify("Backup restored")
    except Exception as exc:
        log(f"Restore failed: {exc}", xbmc.LOGWARNING)
        notify("Restore failed", icon=xbmcgui.NOTIFICATION_ERROR)


def advanced_settings_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Advanced Settings")
    add_action("Open Kodi Add-on Settings", "open_settings")
    add_action("Smart Live TV Updates Help", "live_help")
    add_action("High Activity Mode Help", "live_help")
    add_action("EPG / TV Guide Help", "live_help")
    xbmcplugin.endOfDirectory(HANDLE)


def help_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Help")
    add_action("First Time Setup", "help_topic", {"topic": "setup"})
    add_action("Live TV Updates", "live_help")
    add_action("High Activity Mode", "live_help")
    add_action("Stream Health", "help_topic", {"topic": "health"})
    add_action("TV Guide / EPG", "help_topic", {"topic": "guide"})
    add_action("Movies and TV Shows Cache", "help_topic", {"topic": "faq"})
    add_action("FAQ", "help_topic", {"topic": "faq"})
    xbmcplugin.endOfDirectory(HANDLE)


def help_topic(topic: str) -> None:
    texts = {
        "setup": "First Time Setup\n\nOpen Settings, enter your username and password, then use Test Connection. On first login Bang TV downloads Live TV channels first, then starts EPG and artwork work in the background so browsing stays usable. Open Movies and TV Shows once to build their local SQLite list cache. After that, folders should open much faster.",
        "health": "Stream Health\n\nBang TV records when streams play successfully or fail. This helps mark channels as healthy, slow, or failing. Health data stays local and is used to help you spot problem streams.",
        "guide": "TV Guide / EPG\n\nBang TV keeps EPG data local where possible. Live TV opens from cache first, then EPG fills in from local XMLTV or short EPG cache. If guide rows are missing at first login, leave Kodi open briefly or open the category again so the background EPG worker can finish.",
        "faq": "FAQ\n\nLive TV, Movies and TV Shows are cache-first. Movies and TV Shows now save their category and item lists into SQLite, while metadata is cached separately. The first open may show a metadata progress bar, but the next open should be faster. Use Refresh Live TV or Update Category only when you want to force fresh Live TV data.",
    }
    xbmcgui.Dialog().textviewer("Bang TV Help", texts.get(topic, "Help not found."))

def tools_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Tools")
    add_action("Bang TV Control Centre", "control_centre", plot="One screen showing server, cache, updates, health, notifications and activity status.")
    add_folder("Bang TV Notifications", "notifications", plot="Inbox for Bang TV updates, warnings, maintenance and stream health messages.")
    add_action("Activity Log", "activity_log", plot="Shows recent Bang TV background updates, cache changes and maintenance actions.")
    add_folder("Live TV Manager", "live_tv_manager", plot="Live TV stats, refresh, EPG, logos and recently changed channel tools.")
    add_folder("Manual EPG Manager", "manual_epg_manager", plot="Manually assign EPG data to channels when automatic matching does not work.")
    add_folder("Maintenance", "maintenance", plot="Clean cache, logos, artwork, databases, dead cache and reset tools.")
    add_action("Statistics", "statistics", plot="Viewing and cache statistics for Bang TV.")
    add_folder("Stream Health Centre", "stream_health_centre", plot="Shows healthy, slow and failing streams based on local playback results.")
    add_folder("Recently Changed", "recently_changed", {"view": "categories"}, plot="Recently updated categories from the last smart playlist check.")
    add_folder("Upcoming Sports", "upcoming_sports", plot="Finds possible upcoming sport from cached EPG data.")
    add_folder("Backup & Restore", "backup_restore", plot="Create or restore backups from a folder, USB, NAS or selected ZIP file.")
    add_folder("Advanced Settings", "advanced_settings", plot="Smart update, cache, metadata and EPG settings/help.")
    add_folder("Help", "help_menu", plot="First time setup, Live TV cache, Movies/TV Shows metadata cache, EPG, Android TV performance and FAQ.")
    add_action("Account status", "account_status", plot="Shows your IPTV account status, expiry date and connection limits.")
    add_action("Test connection", "connection_test", plot="Checks that Bang TV can connect to the Xtream Codes server with your saved login.")
    add_folder("Cache", "cache_menu", plot="View cache size, clear cached metadata, clear EPG data, and rebuild Bang TV databases.")
    add_action("Settings", "open_settings", plot="Open Bang TV settings for login, metadata, preview and add-on options.")
    add_action("Logout", "logout", plot="Logs out of Bang TV and removes your saved Bang TV username and password.")
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

Movies and TV Shows

Movies and TV Shows now save their category and item lists into a local SQLite database. The first open may show a progress bar while Bang TV prepares metadata for the visible page. After that, posters, fanart, plots and list data are read from the local cache first, then refreshed only when needed. This keeps Android TV browsing faster and reduces repeated API calls.
"""
    xbmcgui.Dialog().textviewer("Live TV Help", text)

def cache_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Tools / Cache")
    add_action("Cache statistics", "cache_action", {"action": "stats"}, plot="Shows the current size of the Bang TV API and SQLite metadata cache.")
    add_action("Force Icons / Refresh Logos", "cache_action", {"action": "icons"}, plot="Rebuilds the versioned local artwork fallback used by Android TV skins.")
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
        add_action("Login", "login", plot="Enter your Bang TV username and password to unlock Live TV, Movies and Series.")
        add_action("Settings", "open_settings", plot="Open Bang TV settings for login, metadata, EPG and background service options.")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    if setting_bool("show_account_status", True):
        _user, _pwd, label = get_effective_creds()
        add_action(f"Account: {label}", "account_status", plot="Shows your IPTV account status, expiry date and connection limits.")
    add_folder("Live TV", "live_categories", plot="Browse live channels with channel logos and Xtream EPG information.")
    add_folder("TV Guide", "tv_guide", plot="Open the skin-safe Bang TV guide that works across Kodi skins. Uses normal Kodi folder controls with Channel | Now | Next | Later rows.")
    add_folder("Recently Watched", "recent_live", plot="Quickly reopen your recent Live TV channels.")
    add_folder("Movies", "vod_categories", plot="Browse movie categories, recently added movies, posters, descriptions, ratings and trailers.")
    add_folder("Series", "series_categories", plot="Browse TV show categories, seasons and episodes with cached metadata and episode descriptions.")
    add_folder("Search", "search", plot="Search across Bang TV Movies, TV Shows and Live TV channels.")
    add_folder("Favourites", "favourites", plot="Open your saved Bang TV favourite movies, shows and channels.")
    add_folder("Tools", "tools", plot="Account tools, cache controls, connection test, settings and maintenance options.")
    add_action("Logout", "logout", plot="Logs out of Bang TV and removes your saved Bang TV username and password.")
    xbmcplugin.endOfDirectory(HANDLE)




# ---- v1.0.32 robust EPG source browser overrides ----
def _btv_decompress_xmltv_bytes(raw: bytes, progress: Any = None) -> bytes:
    """Return plain XML bytes from XMLTV or XMLTV.GZ without throwing."""
    try:
        if not raw:
            return b""
        # Requests may already decompress some responses. Only decompress true gzip bytes.
        if raw[:2] == b"\x1f\x8b":
            if progress:
                try:
                    progress.update(45, "Decompressing Sky GO NZ EPG...")
                except Exception:
                    pass
            try:
                return gzip.decompress(raw)
            except Exception:
                import io
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
                    return gz.read()
        return raw
    except Exception as exc:
        log(f"EPG gzip/XML decompress failed: {exc}", xbmc.LOGWARNING)
        return raw or b""


def _btv_download_xmltv_source(url: str, progress: Any = None) -> Tuple[bytes, str, str]:
    """Download XMLTV source with visible progress and no hard crash."""
    last_error = ""
    for idx, candidate in enumerate(_epg_source_candidate_urls(url)):
        try:
            if progress:
                try:
                    progress.update(min(10 + idx * 15, 40), "Downloading EPG source...", candidate[:100])
                except Exception:
                    pass
            headers = {
                "User-Agent": "Kodi BangTV/1.0.49",
                "Accept": "application/xml,text/xml,*/*",
            }
            response = SESSION.get(candidate, timeout=90, headers=headers)
            response.raise_for_status()
            raw = response.content or b""
            if raw:
                return _btv_decompress_xmltv_bytes(raw, progress), candidate, ""
            last_error = "Downloaded EPG file was empty"
        except Exception as exc:
            last_error = str(exc)
            log(f"EPG source download failed: {redact_url(candidate)} - {exc}", xbmc.LOGWARNING)
    return b"", "", last_error or "Could not download EPG source"


def _btv_parse_xmltv_channel_rows(raw: bytes, progress: Any = None) -> List[Tuple[str, str]]:
    """Extract all XMLTV <channel> ids and display names without loading programmes."""
    try:
        if not raw:
            return []
        if progress:
            try:
                progress.update(65, "Reading EPG channels...")
            except Exception:
                pass
        text = raw.decode("utf-8", "ignore")
        # Channel definitions normally live before the first programme. This keeps it quick.
        first_programme = text.find("<programme")
        scan = text[:first_programme] if first_programme > 0 else text
        choices: List[Tuple[str, str]] = []
        seen = set()
        for idx, m in enumerate(re.finditer(r"<channel\b([^>]*)>(.*?)</channel\s*>", scan, re.I | re.S)):
            attrs = m.group(1) or ""
            body = m.group(2) or ""
            id_match = re.search(r"\bid\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
            if not id_match:
                continue
            ch_id = html_unescape(id_match.group(1)).strip()
            if not ch_id or ch_id in seen:
                continue
            names = []
            for dn in re.finditer(r"<display-name\b[^>]*>(.*?)</display-name\s*>", body, re.I | re.S):
                name = re.sub(r"<[^>]+>", "", dn.group(1) or "")
                name = html_unescape(name).strip()
                if name and name not in names:
                    names.append(name)
            label = names[0] if names else ch_id
            seen.add(ch_id)
            choices.append((ch_id, label))
            if progress and idx and idx % 25 == 0:
                try:
                    progress.update(min(70 + int(len(choices) / 3), 94), f"Found {len(choices)} EPG channels...", label[:90])
                except Exception:
                    pass
        if choices:
            choices.sort(key=lambda row: row[1].lower())
            return choices
        # Fallback parser for unusual XML formatting.
        try:
            import io
            if progress:
                try:
                    progress.update(80, "Using fallback XML parser...")
                except Exception:
                    pass
            root = ET.fromstring(raw)
            for channel in root.iter():
                tag = str(channel.tag or "").split("}")[-1].lower()
                if tag != "channel":
                    continue
                ch_id = str(channel.get("id") or "").strip()
                if not ch_id or ch_id in seen:
                    continue
                label = ch_id
                for child in list(channel):
                    ctag = str(child.tag or "").split("}")[-1].lower()
                    if ctag == "display-name" and (child.text or "").strip():
                        label = (child.text or "").strip()
                        break
                seen.add(ch_id)
                choices.append((ch_id, label))
        except Exception as exc:
            log(f"Fallback XMLTV channel parse failed: {exc}", xbmc.LOGWARNING)
        choices.sort(key=lambda row: row[1].lower())
        return choices
    except Exception as exc:
        log(f"XMLTV channel list parse crashed: {exc}", xbmc.LOGERROR)
        return []


def xmltv_channel_choices(url: str, cache_key: str, force_refresh: bool = False, progress: Any = None) -> List[Tuple[str, str]]:
    """Robust channel list loader for EPG Sources. Ignores global EPG on/off."""
    try:
        if not url:
            return []
        cache_id = "xmltv_channels_" + re.sub(r"[^A-Za-z0-9_]+", "_", cache_key or str(abs(hash(url))))[:80]
        if not force_refresh:
            cached = metadata_cache_get("epg_source_channels", cache_id, ttl=EPG_TTL_SECONDS)
            if isinstance(cached, dict):
                items = cached.get("items")
                if isinstance(items, list) and items:
                    return [(str(a), str(b)) for a, b in items if a]
        raw, used_url, error = _btv_download_xmltv_source(url, progress)
        if not raw:
            log(f"No XMLTV data returned for {redact_url(url)} error={error}", xbmc.LOGWARNING)
            return []
        choices = _btv_parse_xmltv_channel_rows(raw, progress)
        if choices:
            metadata_cache_set("epg_source_channels", cache_id, {"items": choices, "used_url": used_url, "updated": int(time.time())})
        else:
            log(f"XMLTV source loaded but no <channel> rows found: {redact_url(used_url or url)}", xbmc.LOGWARNING)
        return choices
    except Exception as exc:
        log(f"xmltv_channel_choices crashed: {exc}", xbmc.LOGERROR)
        return []


def manual_epg_source_channels_menu(source_id: str) -> None:
    """Open an EPG source, show visible loading, then list every EPG channel."""
    xbmcplugin.setPluginCategory(HANDLE, "Sky GO NZ EPG Channels" if source_id == "skygo" else "EPG Channels")
    xbmcplugin.setContent(HANDLE, "videos")
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id or "EPG Source")
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    if not url:
        add_action("EPG source has no URL", "manual_epg_sources")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
        return
    choices: List[Tuple[str, str]] = []
    progress = xbmcgui.DialogProgress()
    try:
        progress_create(progress, ADDON_NAME, f"Loading {label} EPG", "Downloading guide...")
        choices = xmltv_channel_choices(url, "manual_source_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id or label)[:80], force_refresh=True, progress=progress)
        try:
            progress_update(progress, 100, "EPG loaded", f"Found {len(choices)} channels")
        except Exception:
            pass
    except Exception as exc:
        log(f"EPG source channel menu crashed: {exc}", xbmc.LOGERROR)
        try:
            progress_update(progress, 100, "EPG load failed", str(exc)[:90])
            xbmc.sleep(700)
        except Exception:
            pass
    finally:
        try:
            progress.close()
        except Exception:
            pass
    add_action(f"Source info: {label}", "manual_epg_source_info", {"source_id": source_id}, plot=f"URL: {url}\nChannels found: {len(choices)}")
    add_action("Refresh this EPG source", "manual_epg_refresh_one_source", {"source_id": source_id}, plot="Force download and parse this XMLTV source again.")
    if not choices:
        add_action("No EPG channels found", "manual_epg_sources", plot=f"Bang TV downloaded the EPG source but could not read channel rows.\n\nSource: {label}\nURL: {url}")
    else:
        add_action(f"EPG channels loaded: {len(choices)}", "manual_epg_source_info", {"source_id": source_id}, plot="Choose an EPG channel below, then choose the Bang TV channel to assign it to.")
        for ch_id, ch_label in choices[:3000]:
            add_action(str(ch_label), "manual_epg_assign_from_source_channel", {"source_id": source_id, "channel_id": ch_id, "channel_label": ch_label}, plot=f"EPG channel: {ch_label}\nEPG ID: {ch_id}\n\nSelect this, then choose the Bang TV Live TV channel to link it to.")
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)


def manual_epg_source_channels_for_channel_menu(source_id: str, stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    """Choose the EPG channel for one already selected Bang TV channel."""
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id)
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    xbmcplugin.setPluginCategory(HANDLE, f"{label} EPG Channels")
    xbmcplugin.setContent(HANDLE, "videos")
    choices: List[Tuple[str, str]] = []
    progress = xbmcgui.DialogProgress()
    try:
        progress_create(progress, ADDON_NAME, f"Loading {label} EPG", "Reading channel list...")
        choices = xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=True, progress=progress)
        try:
            progress_update(progress, 100, "EPG loaded", f"Found {len(choices)} channels")
        except Exception:
            pass
    except Exception as exc:
        log(f"EPG source channel-for-channel menu crashed: {exc}", xbmc.LOGERROR)
    finally:
        try:
            progress.close()
        except Exception:
            pass
    add_action(f"Loaded EPG channels: {len(choices)}", "manual_epg_source_info", {"source_id": source_id}, plot=f"Assigning to Bang TV channel:\n{name}")
    if not choices:
        add_action("No EPG channels found", "manual_epg_sources_for_channel", {"stream_id": stream_id, "name": name})
    else:
        target = norm_epg_key(name)
        def score(pair: Tuple[str, str]) -> Tuple[int, str]:
            cid, lbl = pair
            key = norm_epg_key(lbl)
            if target and key == target:
                return (0, lbl.lower())
            if target and (target in key or key in target):
                return (1, lbl.lower())
            return (2, lbl.lower())
        for ch_id, ch_label in sorted(choices, key=score)[:3000]:
            add_action(str(ch_label), "manual_epg_assign_to_stream", {"source_id": source_id, "channel_id": ch_id, "channel_label": ch_label, "stream_id": stream_id, "name": name, "cat_id": cat_id, "title": title}, plot=f"Assign EPG channel:\n{ch_label}\n\nEPG ID: {ch_id}\n\nTo Bang TV channel:\n{name}")
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
# ---- end v1.0.32 overrides ----


# ---- v1.0.34 EPG source loading final robust fix ----
def _btv_http_get_bytes_multi(url: str, progress: Any = None) -> Tuple[bytes, str, str]:
    """Try several download methods so XMLTV.GZ sources work inside Kodi."""
    last_error = ""
    candidates = _epg_source_candidate_urls(url)
    for idx, candidate in enumerate(candidates):
        pct = min(8 + idx * 18, 48)
        if progress:
            try:
                progress_update(progress, pct, "Downloading EPG source...", candidate[:110])
            except Exception:
                pass
        # Method 1: addon session
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 Kodi BangTV EPG Manager/1.0.35",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, identity",
                "Cache-Control": "no-cache",
            }
            r = SESSION.get(candidate, timeout=90, headers=headers, allow_redirects=True)
            r.raise_for_status()
            raw = r.content or b""
            if raw:
                return raw, candidate, ""
            last_error = "Downloaded empty file"
        except Exception as exc:
            last_error = str(exc)
            log(f"EPG requests download failed: {redact_url(candidate)} - {exc}", xbmc.LOGWARNING)
        # Method 2: urllib, useful on some Kodi Python builds
        try:
            import urllib.request
            req = urllib.request.Request(candidate, headers={
                "User-Agent": "Mozilla/5.0 Kodi BangTV EPG Manager/1.0.35",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-cache",
            })
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read() or b""
            if raw:
                return raw, candidate, ""
            last_error = "Downloaded empty file with urllib"
        except Exception as exc:
            last_error = str(exc)
            log(f"EPG urllib download failed: {redact_url(candidate)} - {exc}", xbmc.LOGWARNING)
    return b"", "", last_error or "Could not download EPG source"


def _btv_to_plain_xml(raw: bytes, progress: Any = None) -> Tuple[bytes, str]:
    """Convert gzip/deflate/plain XML bytes into plain XML bytes and a status."""
    if not raw:
        return b"", "empty"
    data = raw
    # Some servers/clients return already decompressed XML.
    if data.lstrip()[:1] == b"<":
        return data, "plain xml"
    # True gzip file magic.
    if data[:2] == b"\x1f\x8b":
        if progress:
            try: progress.update(55, "Decompressing epg.xml.gz...")
            except Exception: pass
        try:
            return gzip.decompress(data), "gzip decompressed"
        except Exception:
            try:
                import io
                with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                    return gz.read(), "gzipfile decompressed"
            except Exception as exc:
                log(f"gzip decompress failed: {exc}", xbmc.LOGWARNING)
    # Try zlib wrappers just in case.
    try:
        import zlib
        out = zlib.decompress(data, 16 + zlib.MAX_WBITS)
        if out:
            return out, "zlib gzip decompressed"
    except Exception:
        pass
    try:
        import zlib
        out = zlib.decompress(data)
        if out:
            return out, "zlib decompressed"
    except Exception:
        pass
    return data, "unknown/raw"


def _btv_extract_xmltv_channels_stream(xml_bytes: bytes, progress: Any = None) -> Tuple[List[Tuple[str, str]], str]:
    """Extract XMLTV channel rows using streaming parse plus regex fallback."""
    if not xml_bytes:
        return [], "no xml bytes"
    stripped = xml_bytes.lstrip()
    if not stripped.startswith(b"<"):
        preview = stripped[:180].decode("utf-8", "ignore").replace("\n", " ")
        return [], "not xml: " + preview
    choices: List[Tuple[str, str]] = []
    seen = set()
    # Streaming parse is safer than fromstring for large 7 day guides.
    try:
        import io
        if progress:
            try: progress.update(68, "Reading EPG channel list...")
            except Exception: pass
        for idx, (event, elem) in enumerate(ET.iterparse(io.BytesIO(xml_bytes), events=("end",))):
            tag = str(elem.tag or "").split("}")[-1].lower()
            if tag == "channel":
                ch_id = str(elem.get("id") or "").strip()
                if ch_id and ch_id not in seen:
                    label = ch_id
                    names = []
                    for child in list(elem):
                        ctag = str(child.tag or "").split("}")[-1].lower()
                        if ctag == "display-name":
                            txt = "".join(child.itertext()).strip()
                            if txt and txt not in names:
                                names.append(txt)
                    if names:
                        label = names[0]
                    seen.add(ch_id)
                    choices.append((ch_id, label))
                    if progress and len(choices) % 20 == 0:
                        try: progress.update(min(70 + len(choices)//2, 94), f"Found {len(choices)} EPG channels...", label[:90])
                        except Exception: pass
                try: elem.clear()
                except Exception: pass
            elif tag == "programme" and choices:
                # Channels normally come before programmes. Stop early once programme data starts.
                break
        if choices:
            choices.sort(key=lambda row: row[1].lower())
            return choices, f"stream parser found {len(choices)}"
    except Exception as exc:
        log(f"Streaming XMLTV channel parse failed: {exc}", xbmc.LOGWARNING)
    # Regex fallback, including self closing channels.
    try:
        if progress:
            try: progress.update(82, "Using fallback channel scanner...")
            except Exception: pass
        text = xml_bytes.decode("utf-8", "ignore")
        first_programme = text.find("<programme")
        scan = text[:first_programme] if first_programme > 0 else text
        for m in re.finditer(r"<channel\b([^>]*?)(?:>(.*?)</channel\s*>|/>)", scan, re.I | re.S):
            attrs = m.group(1) or ""
            body = m.group(2) or ""
            id_match = re.search(r"\bid\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
            if not id_match:
                continue
            ch_id = html_unescape(id_match.group(1)).strip()
            if not ch_id or ch_id in seen:
                continue
            label = ch_id
            dn = re.search(r"<display-name\b[^>]*>(.*?)</display-name\s*>", body, re.I | re.S)
            if dn:
                label = html_unescape(re.sub(r"<[^>]+>", "", dn.group(1) or "")).strip() or ch_id
            seen.add(ch_id)
            choices.append((ch_id, label))
        choices.sort(key=lambda row: row[1].lower())
        return choices, f"regex found {len(choices)}"
    except Exception as exc:
        log(f"Regex XMLTV channel parse failed: {exc}", xbmc.LOGWARNING)
    return [], "no <channel> elements found"


def xmltv_channel_choices(url: str, cache_key: str, force_refresh: bool = False, progress: Any = None) -> List[Tuple[str, str]]:
    """v1.0.34 final override: load .xml.gz, parse channels, never silently return stale empty data."""
    try:
        if not url:
            return []
        cache_id = "xmltv_channels_" + re.sub(r"[^A-Za-z0-9_]+", "_", cache_key or str(abs(hash(url))))[:80]
        if not force_refresh:
            cached = metadata_cache_get("epg_source_channels", cache_id, ttl=EPG_TTL_SECONDS)
            if isinstance(cached, dict):
                items = cached.get("items")
                if isinstance(items, list) and items:
                    return [(str(a), str(b)) for a, b in items if a]
        raw, used_url, err = _btv_http_get_bytes_multi(url, progress)
        if not raw:
            log(f"EPG source download returned no data: {redact_url(url)} error={err}", xbmc.LOGWARNING)
            return []
        xml_bytes, decode_status = _btv_to_plain_xml(raw, progress)
        choices, parse_status = _btv_extract_xmltv_channels_stream(xml_bytes, progress)
        try:
            metadata_cache_set("epg_source_debug", cache_id, {"url": used_url or url, "bytes": len(raw), "xml_bytes": len(xml_bytes or b""), "decode": decode_status, "parse": parse_status, "count": len(choices), "updated": int(time.time())})
        except Exception:
            pass
        if choices:
            metadata_cache_set("epg_source_channels", cache_id, {"items": choices, "used_url": used_url, "updated": int(time.time()), "count": len(choices)})
        else:
            log(f"EPG source parsed 0 channels. decode={decode_status} parse={parse_status} bytes={len(raw)} xml_bytes={len(xml_bytes or b'')}", xbmc.LOGWARNING)
        return choices
    except Exception as exc:
        log(f"xmltv_channel_choices v1.0.34 crashed: {exc}", xbmc.LOGERROR)
        return []


def manual_epg_source_channels_menu(source_id: str) -> None:
    """Open EPG source and list all channels with visible loading and debug on failure."""
    xbmcplugin.setPluginCategory(HANDLE, "Sky GO NZ EPG Channels" if source_id == "skygo" else "EPG Channels")
    xbmcplugin.setContent(HANDLE, "videos")
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id or "EPG Source")
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    # Force Sky GO NZ to the correct current URL even if old settings/cache stored another one.
    if source_id == "skygo":
        label = "Sky GO NZ"
        url = "https://i.mjh.nz/SkyGo/epg.xml.gz"
    choices: List[Tuple[str, str]] = []
    progress = xbmcgui.DialogProgress()
    try:
        progress_create(progress, ADDON_NAME, f"Loading {label} EPG", "Downloading guide...")
        choices = xmltv_channel_choices(url, "manual_source_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id or label)[:80], force_refresh=True, progress=progress)
        try: progress_update(progress, 100, "EPG loaded", f"Found {len(choices)} channels")
        except Exception: pass
        xbmc.sleep(350)
    except Exception as exc:
        log(f"manual_epg_source_channels_menu v1.0.34 crashed: {exc}", xbmc.LOGERROR)
    finally:
        try: progress.close()
        except Exception: pass
    add_action(f"Source: {label}", "manual_epg_source_info", {"source_id": source_id}, plot=f"URL: {url}\nChannels found: {len(choices)}")
    add_action("Refresh this EPG source", "manual_epg_refresh_one_source", {"source_id": source_id}, plot="Force download and parse this XMLTV source again.")
    if not choices:
        cache_id = "xmltv_channels_" + re.sub(r"[^A-Za-z0-9_]+", "_", ("manual_source_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id or label)[:80]))[:80]
        debug = metadata_cache_get("epg_source_debug", cache_id, ttl=86400) or {}
        dbg = "\n".join([f"{k}: {v}" for k, v in debug.items()]) if isinstance(debug, dict) else ""
        add_action("No EPG channels found", "manual_epg_sources", plot=f"Could not read channels from this EPG.\n\nURL: {url}\n\n{dbg}")
    else:
        add_action(f"EPG channels loaded: {len(choices)}", "manual_epg_source_info", {"source_id": source_id}, plot="Choose an EPG channel below, then choose the Bang TV channel to assign it to.")
        for ch_id, ch_label in choices[:5000]:
            add_action(str(ch_label), "manual_epg_assign_from_source_channel", {"source_id": source_id, "channel_id": ch_id, "channel_label": ch_label}, plot=f"EPG channel: {ch_label}\nEPG ID: {ch_id}\n\nSelect this, then choose the Bang TV Live TV channel to link it to.")
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)


def manual_epg_source_channels_for_channel_menu(source_id: str, stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    """Choose the EPG channel for one selected Bang TV channel."""
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id or "EPG Source")
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    if source_id == "skygo":
        label = "Sky GO NZ"
        url = "https://i.mjh.nz/SkyGo/epg.xml.gz"
    xbmcplugin.setPluginCategory(HANDLE, f"{label} EPG Channels")
    xbmcplugin.setContent(HANDLE, "videos")
    progress = xbmcgui.DialogProgress()
    choices: List[Tuple[str, str]] = []
    try:
        progress_create(progress, ADDON_NAME, f"Loading {label} EPG", "Downloading guide...")
        choices = xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=True, progress=progress)
        try: progress_update(progress, 100, "EPG loaded", f"Found {len(choices)} channels")
        except Exception: pass
        xbmc.sleep(350)
    except Exception as exc:
        log(f"manual_epg_source_channels_for_channel v1.0.34 crashed: {exc}", xbmc.LOGERROR)
    finally:
        try: progress.close()
        except Exception: pass
    add_action(f"Loaded EPG channels: {len(choices)}", "manual_epg_source_info", {"source_id": source_id}, plot=f"Assigning to Bang TV channel:\n{name}")
    if not choices:
        add_action("No EPG channels found", "manual_epg_sources_for_channel", {"stream_id": stream_id, "name": name}, plot=f"Could not read EPG channels from {label}. Try Refresh this EPG source.")
    else:
        target = norm_epg_key(name)
        def score(pair: Tuple[str, str]) -> Tuple[int, str]:
            cid, lbl = pair
            key = norm_epg_key(lbl)
            if target and key == target: return (0, lbl.lower())
            if target and (target in key or key in target): return (1, lbl.lower())
            return (2, lbl.lower())
        for ch_id, ch_label in sorted(choices, key=score)[:5000]:
            add_action(str(ch_label), "manual_epg_assign_to_stream", {"source_id": source_id, "channel_id": ch_id, "channel_label": ch_label, "stream_id": stream_id, "name": name, "cat_id": cat_id, "title": title}, plot=f"Assign EPG channel:\n{ch_label}\n\nEPG ID: {ch_id}\n\nTo Bang TV channel:\n{name}")
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
# ---- end v1.0.34 EPG source loading final robust fix ----


# ---- v1.0.35 EPG source loader, force real channel extraction ----
def _btv_parse_xmltv_channels_v35(xml_bytes: bytes, progress: Any = None) -> Tuple[List[Tuple[str, str]], str]:
    """Very tolerant XMLTV channel extractor.

    Some feeds can have channel rows, some can have a doctype, and some Kodi
    builds are fussy with huge XML. This first scans raw text for <channel>
    display names, then falls back to programme channel ids so the user always
    gets something selectable from the EPG source.
    """
    if not xml_bytes:
        return [], "empty xml"
    text = xml_bytes.decode('utf-8', 'ignore')
    if not text.lstrip().startswith('<'):
        return [], 'not xml: ' + text[:180].replace('\n', ' ')
    choices = []
    seen = set()
    if progress:
        try: progress_update(progress, 65, 'Reading EPG channels...', 'Scanning XMLTV channel list')
        except Exception: pass
    # Fast raw scan for channels before programmes, but do not require them to be before programme.
    channel_pat = re.compile(r'<\s*channel\b([^>]*)>(.*?)<\s*/\s*channel\s*>', re.I | re.S)
    for m in channel_pat.finditer(text):
        attrs = m.group(1) or ''
        body = m.group(2) or ''
        im = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if not im:
            continue
        ch_id = html_unescape(im.group(1)).strip()
        if not ch_id or ch_id in seen:
            continue
        names = []
        for dm in re.finditer(r'<\s*display-name\b[^>]*>(.*?)<\s*/\s*display-name\s*>', body, re.I | re.S):
            nm = html_unescape(re.sub(r'<[^>]+>', '', dm.group(1) or '')).strip()
            if nm and nm not in names:
                names.append(nm)
        label = names[0] if names else ch_id
        seen.add(ch_id)
        choices.append((ch_id, label))
        if progress and len(choices) % 25 == 0:
            try: progress_update(progress, min(66 + len(choices)//2, 88), f'Found {len(choices)} EPG channels...', label[:90])
            except Exception: pass
    # Self-closing channel rows, uncommon but harmless to support.
    for m in re.finditer(r'<\s*channel\b([^>]*)/\s*>', text, re.I | re.S):
        attrs = m.group(1) or ''
        im = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if not im:
            continue
        ch_id = html_unescape(im.group(1)).strip()
        if ch_id and ch_id not in seen:
            seen.add(ch_id); choices.append((ch_id, ch_id))
    if choices:
        choices.sort(key=lambda row: row[1].lower())
        return choices, f'channel elements found {len(choices)}'
    # Fallback: if this EPG has programme rows but no channel list, show each programme channel id.
    if progress:
        try: progress_update(progress, 82, 'No channel rows found...', 'Scanning programme channel IDs')
        except Exception: pass
    prog_seen = set()
    for m in re.finditer(r'<\s*programme\b([^>]*)>', text, re.I | re.S):
        attrs = m.group(1) or ''
        cm = re.search(r'\bchannel\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if not cm:
            continue
        cid = html_unescape(cm.group(1)).strip()
        if cid and cid not in prog_seen:
            prog_seen.add(cid)
            label = cid
            # Turn common ids into nicer labels while keeping id exact for assignment.
            label = re.sub(r'[-_.]+', ' ', label).strip()
            label = re.sub(r'\s+', ' ', label)
            choices.append((cid, label or cid))
            if progress and len(choices) % 25 == 0:
                try: progress_update(progress, min(84 + len(choices)//4, 94), f'Found {len(choices)} EPG channel IDs...', cid[:90])
                except Exception: pass
    choices.sort(key=lambda row: row[1].lower())
    return choices, f'programme channel ids found {len(choices)}'


def xmltv_channel_choices(url: str, cache_key: str, force_refresh: bool = False, progress: Any = None) -> List[Tuple[str, str]]:
    """v1.0.35: always load Sky GO NZ channel list, including .xml.gz and programme-id fallback."""
    try:
        if not url:
            return []
        # Force current Sky GO NZ URL when this is the built-in source.
        if 'SkyGo' in url or 'skygo' in str(cache_key).lower():
            url = 'https://i.mjh.nz/SkyGo/epg.xml.gz'
        cache_id = 'xmltv_channels_' + re.sub(r'[^A-Za-z0-9_]+', '_', cache_key or str(abs(hash(url))))[:80]
        if not force_refresh:
            cached = metadata_cache_get('epg_source_channels', cache_id, ttl=EPG_TTL_SECONDS)
            if isinstance(cached, dict):
                items = cached.get('items')
                if isinstance(items, list) and items:
                    return [(str(a), str(b)) for a, b in items if a]
        if progress:
            try: progress_update(progress, 5, 'Loading EPG source...', 'Preparing download')
            except Exception: pass
        raw, used_url, err = _btv_http_get_bytes_multi(url, progress)
        if not raw:
            metadata_cache_set('epg_source_debug', cache_id, {'url': url, 'error': err, 'count': 0, 'updated': int(time.time())})
            log(f'EPG source download returned no data: {redact_url(url)} error={err}', xbmc.LOGWARNING)
            return []
        xml_bytes, decode_status = _btv_to_plain_xml(raw, progress)
        choices, parse_status = _btv_parse_xmltv_channels_v35(xml_bytes, progress)
        try:
            metadata_cache_set('epg_source_debug', cache_id, {
                'url': used_url or url,
                'raw_bytes': len(raw),
                'xml_bytes': len(xml_bytes or b''),
                'decode': decode_status,
                'parse': parse_status,
                'count': len(choices),
                'preview': (xml_bytes or b'')[:220].decode('utf-8', 'ignore').replace('\n',' '),
                'updated': int(time.time())
            })
        except Exception:
            pass
        if choices:
            metadata_cache_set('epg_source_channels', cache_id, {'items': choices, 'used_url': used_url or url, 'updated': int(time.time()), 'count': len(choices)})
        else:
            log(f'EPG source parsed 0 channels. decode={decode_status} parse={parse_status} bytes={len(raw)} xml_bytes={len(xml_bytes or b"")}', xbmc.LOGWARNING)
        return choices
    except Exception as exc:
        log(f'xmltv_channel_choices v1.0.35 crashed: {exc}', xbmc.LOGERROR)
        return []


def manual_epg_source_channels_menu(source_id: str) -> None:
    """Open EPG source and list all channels, with visible loading and debug info."""
    data = manual_epg_load()
    src = (data.get('sources') or {}).get(source_id) or {}
    label = str(src.get('label') or source_id or 'EPG Source')
    url = str(src.get('url') or '') or manual_epg_source_url(source_id)
    if source_id == 'skygo':
        label = 'Sky GO NZ'
        url = 'https://i.mjh.nz/SkyGo/epg.xml.gz'
    xbmcplugin.setPluginCategory(HANDLE, f'{label} EPG Channels')
    xbmcplugin.setContent(HANDLE, 'videos')
    choices: List[Tuple[str, str]] = []
    progress = xbmcgui.DialogProgress()
    try:
        progress_create(progress, ADDON_NAME, f'Loading {label} EPG', 'Downloading and reading channel list')
        choices = xmltv_channel_choices(url, 'manual_source_' + re.sub(r'[^A-Za-z0-9_]+', '_', source_id or label)[:80], force_refresh=True, progress=progress)
        try: progress_update(progress, 100, 'EPG channels loaded', f'Found {len(choices)} channels')
        except Exception: pass
        xbmc.sleep(500)
    except Exception as exc:
        log(f'manual_epg_source_channels_menu v1.0.35 crashed: {exc}', xbmc.LOGERROR)
    finally:
        try: progress.close()
        except Exception: pass
    add_action(f'EPG channels loaded: {len(choices)}', 'manual_epg_source_info', {'source_id': source_id}, plot=f'Source: {label}\nURL: {url}\nChannels found: {len(choices)}')
    add_action('Refresh this EPG source', 'manual_epg_refresh_one_source', {'source_id': source_id}, plot='Force download and parse this XMLTV source again.')
    if not choices:
        cache_id = 'xmltv_channels_' + re.sub(r'[^A-Za-z0-9_]+', '_', ('manual_source_' + re.sub(r'[^A-Za-z0-9_]+', '_', source_id or label)[:80]))[:80]
        debug = metadata_cache_get('epg_source_debug', cache_id, ttl=86400) or {}
        dbg = '\n'.join([f'{k}: {v}' for k, v in debug.items()]) if isinstance(debug, dict) else ''
        add_action('Still no EPG channels found, open this for debug info', 'manual_epg_source_info', {'source_id': source_id}, plot=f'Bang TV downloaded/read attempted this source but found 0 channels.\n\nURL: {url}\n\n{dbg}')
    else:
        add_action('Select an EPG channel below, then choose Bang TV channel', 'manual_epg_source_info', {'source_id': source_id}, plot='Pick one of the EPG channels below. After that, choose the Bang TV live channel to assign it to.')
        for ch_id, ch_label in choices[:5000]:
            add_action(str(ch_label), 'manual_epg_assign_from_source_channel', {'source_id': source_id, 'channel_id': ch_id, 'channel_label': ch_label}, plot=f'EPG channel: {ch_label}\nEPG ID: {ch_id}\n\nSelect this, then choose the Bang TV Live TV channel to link it to.')
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)


def manual_epg_source_channels_for_channel_menu(source_id: str, stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    data = manual_epg_load()
    src = (data.get('sources') or {}).get(source_id) or {}
    label = str(src.get('label') or source_id or 'EPG Source')
    url = str(src.get('url') or '') or manual_epg_source_url(source_id)
    if source_id == 'skygo':
        label = 'Sky GO NZ'
        url = 'https://i.mjh.nz/SkyGo/epg.xml.gz'
    xbmcplugin.setPluginCategory(HANDLE, f'{label} EPG Channels')
    xbmcplugin.setContent(HANDLE, 'videos')
    choices: List[Tuple[str, str]] = []
    progress = xbmcgui.DialogProgress()
    try:
        progress_create(progress, ADDON_NAME, f'Loading {label} EPG', f'Assigning to {name}')
        choices = xmltv_channel_choices(url, 'manual_select_' + re.sub(r'[^A-Za-z0-9_]+', '_', source_id or label)[:80], force_refresh=True, progress=progress)
        try: progress_update(progress, 100, 'EPG channels loaded', f'Found {len(choices)} channels')
        except Exception: pass
        xbmc.sleep(500)
    except Exception as exc:
        log(f'manual_epg_source_channels_for_channel v1.0.35 crashed: {exc}', xbmc.LOGERROR)
    finally:
        try: progress.close()
        except Exception: pass
    add_action(f'Loaded EPG channels: {len(choices)}', 'manual_epg_source_info', {'source_id': source_id}, plot=f'Assigning to Bang TV channel:\n{name}')
    if not choices:
        add_action('No EPG channels found, open EPG source debug info', 'manual_epg_source_info', {'source_id': source_id}, plot=f'Could not read EPG channels from {label}.')
    else:
        target = norm_epg_key(name)
        def score(pair: Tuple[str, str]) -> Tuple[int, str]:
            cid, lbl = pair
            key = norm_epg_key(lbl)
            if target and key == target: return (0, lbl.lower())
            if target and (target in key or key in target): return (1, lbl.lower())
            return (2, lbl.lower())
        for ch_id, ch_label in sorted(choices, key=score)[:5000]:
            add_action(str(ch_label), 'manual_epg_assign_to_stream', {'source_id': source_id, 'channel_id': ch_id, 'channel_label': ch_label, 'stream_id': stream_id, 'name': name}, plot=f'Assign EPG channel:\n{ch_label}\n\nEPG ID: {ch_id}\n\nTo Bang TV channel:\n{name}')
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
# ---- end v1.0.35 EPG source loader ----


# ---- v1.0.37 manual EPG right-click assignment flow ----
def _btv_refresh_after_epg_assign(cat_id: str = "") -> None:
    """Refresh the screen the user assigned from so the new EPG appears straight away."""
    try:
        xbmc.executebuiltin("Container.Refresh")
        xbmc.sleep(250)
    except Exception:
        pass
    if cat_id:
        try:
            # When assignment is launched from a live category context menu, jump back to that
            # category and replace the EPG picker folder, so the user immediately sees the data.
            xbmc.executebuiltin('Container.Update(%s,replace)' % build_url({"mode": "live_streams", "cat_id": str(cat_id)}))
        except Exception as exc:
            log(f"EPG assign category refresh failed: {exc}", xbmc.LOGWARNING)


def manual_epg_assign(stream_id: str = "", name: str = "", cat_id: str = "") -> None:
    """Context-menu Assign EPG flow.

    Right-click channel -> Assign EPG to this channel:
    - lets user choose Sky GO NZ or another source
    - downloads/parses the source on demand if it has not been loaded before
    - lets user choose EPG channel
    - saves the mapping
    - shows success
    - refreshes the current Live TV directory straight away
    """
    sid = str(stream_id or "").strip()
    if not sid:
        sid = xbmcgui.Dialog().input("Live TV stream ID", type=xbmcgui.INPUT_NUMERIC).strip()
    if not sid:
        notify("No stream ID entered")
        return

    channel_name = str(name or "").strip()
    if not channel_name:
        channel_name = xbmcgui.Dialog().input("Channel name", defaultt="Live TV Channel", type=xbmcgui.INPUT_ALPHANUM).strip() or sid

    source_id, source_label, url = manual_epg_source_select()
    if not url:
        notify("EPG assignment cancelled")
        return
    if source_id == "skygo":
        source_label = "Sky GO NZ"
        url = "https://i.mjh.nz/SkyGo/epg.xml.gz"

    progress = xbmcgui.DialogProgress()
    choices: List[Tuple[str, str]] = []
    try:
        progress_create(progress, ADDON_NAME, f"Loading {source_label} EPG", "Downloading guide if needed...")
        choices = xmltv_channel_choices(
            url,
            "manual_assign_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id or source_label)[:80],
            force_refresh=False,
            progress=progress,
        )
        try:
            progress_update(progress, 100, "EPG channels ready", f"Found {len(choices)} channels")
            xbmc.sleep(300)
        except Exception:
            pass
    except Exception as exc:
        log(f"manual_epg_assign v1.0.37 EPG load crashed: {exc}", xbmc.LOGERROR)
    finally:
        try:
            progress.close()
        except Exception:
            pass

    if not choices:
        xbmcgui.Dialog().ok(ADDON_NAME, f"No EPG channels found in {source_label}.\n\nTry Tools > EPG Manager > Refresh EPG Sources, then try again.")
        return

    target = norm_epg_key(channel_name)
    ordered = sorted(
        choices,
        key=lambda pair: (
            0 if target and norm_epg_key(pair[1]) == target else
            1 if target and (target in norm_epg_key(pair[1]) or norm_epg_key(pair[1]) in target) else
            2,
            str(pair[1]).lower()
        )
    )
    labels = [f"{lbl}  [{cid}]" for cid, lbl in ordered]
    idx = xbmcgui.Dialog().select(f"Assign EPG to {channel_name}", labels)
    if idx < 0:
        notify("EPG assignment cancelled")
        return

    ch_id, ch_label = ordered[idx]
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    source_label = str(src.get("label") or source_label or source_id)
    key = manual_epg_channel_key(sid, channel_name)
    data.setdefault("channels", {})[key] = {
        "stream_id": sid,
        "name": channel_name,
        "source_id": source_id,
        "source_label": source_label,
        "url": url,
        "channel_id": ch_id,
        "channel_label": ch_label,
        "updated": int(time.time()),
    }
    manual_epg_save(data)

    # Clear related live metadata cache so the current folder rebuild pulls the manual EPG now/next.
    try:
        metadata_cache_delete("live_streams", str(cat_id or ""))
    except Exception:
        pass

    add_bang_notification(f"Manual EPG assigned: {channel_name} → {ch_label}", "Updates")
    add_activity(f"Manual EPG assigned for {channel_name}", "updates")
    notify(f"EPG assigned: {channel_name} → {ch_label}")
    try:
        xbmcgui.Dialog().notification(ADDON_NAME, f"EPG assigned to {channel_name}", xbmcgui.NOTIFICATION_INFO, 3500)
    except Exception:
        pass
    _btv_refresh_after_epg_assign(cat_id)


def manual_epg_assign_to_stream(source_id: str, channel_id: str, channel_label: str, stream_id: str, name: str, cat_id: str = "") -> None:
    source_id = str(source_id or "")
    channel_id = str(channel_id or "")
    channel_label = str(channel_label or channel_id)
    stream_id = str(stream_id or "")
    name = str(name or stream_id or "Live TV Channel")
    if not stream_id or not channel_id:
        notify("Missing channel or EPG ID", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    source_label = str(src.get("label") or source_id)
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    if source_id == "skygo":
        source_label = "Sky GO NZ"
        url = "https://i.mjh.nz/SkyGo/epg.xml.gz"
    key = manual_epg_channel_key(stream_id, name)
    data.setdefault("channels", {})[key] = {
        "stream_id": stream_id,
        "name": name,
        "source_id": source_id,
        "source_label": source_label,
        "url": url,
        "channel_id": channel_id,
        "channel_label": channel_label,
        "updated": int(time.time()),
    }
    manual_epg_save(data)
    add_bang_notification(f"Manual EPG assigned: {name} → {channel_label}", "Updates")
    add_activity(f"Manual EPG assigned for {name}", "updates")
    notify(f"EPG assigned: {name} → {channel_label}")
    try:
        xbmcgui.Dialog().notification(ADDON_NAME, f"EPG assigned to {name}", xbmcgui.NOTIFICATION_INFO, 3500)
    except Exception:
        pass
    _btv_refresh_after_epg_assign(cat_id)
# ---- end v1.0.37 manual EPG right-click assignment flow ----


# ---- v1.0.38 final manual EPG assign flow fix ----
def _btv_epg_source_items() -> List[Tuple[str, str, str]]:
    data = manual_epg_load()
    sources = ensure_builtin_epg_sources(data).get("sources") or {}
    rows = []
    for sid, src in sources.items():
        if not src.get("enabled", True):
            continue
        label = str(src.get("label") or sid)
        url = str(src.get("url") or "") or manual_epg_source_url(sid)
        if sid == "skygo":
            label = "Sky GO NZ"
            url = SKYGO_EPG_URL
        rows.append((str(sid), label, url))
    rows.sort(key=lambda r: (0 if r[0] == "skygo" else 1, r[1].lower()))
    return rows


def _btv_save_epg_assignment(source_id: str, channel_id: str, channel_label: str, stream_id: str, name: str) -> None:
    data = manual_epg_load()
    data = ensure_builtin_epg_sources(data)
    src = (data.get("sources") or {}).get(source_id) or {}
    source_label = str(src.get("label") or source_id)
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    if source_id == "skygo":
        source_label = "Sky GO NZ"
        url = SKYGO_EPG_URL
    key = manual_epg_channel_key(stream_id, name)
    data.setdefault("channels", {})[key] = {
        "stream_id": str(stream_id),
        "name": str(name),
        "source_id": str(source_id),
        "source_label": source_label,
        "url": url,
        "channel_id": str(channel_id),
        "channel_label": str(channel_label or channel_id),
        "updated": int(time.time()),
    }
    manual_epg_save(data)


def _btv_finish_epg_assignment(name: str, channel_label: str, cat_id: str = "") -> None:
    add_bang_notification(f"Manual EPG assigned: {name} → {channel_label}", "Updates")
    add_activity(f"Manual EPG assigned for {name}", "updates")
    try:
        xbmcgui.Dialog().notification(ADDON_NAME, f"EPG assigned to {name}", xbmcgui.NOTIFICATION_INFO, 4000)
    except Exception:
        pass
    try:
        xbmc.executebuiltin(f'Notification({ADDON_NAME},EPG assigned and refreshing folder,3000)')
    except Exception:
        pass
    try:
        xbmc.executebuiltin("Container.Refresh")
        xbmc.sleep(300)
    except Exception:
        pass
    if cat_id:
        try:
            xbmc.executebuiltin('Container.Update(%s,replace)' % build_url({"mode": "live_streams", "cat_id": str(cat_id)}))
        except Exception as exc:
            log(f"EPG assign Container.Update failed: {exc}", xbmc.LOGWARNING)


def manual_epg_assign(stream_id: str = "", name: str = "", cat_id: str = "") -> None:
    """Right click channel -> Assign EPG to this channel.

    This is now a direct popup flow, not a hidden folder flow:
    choose source, download on demand with visible progress, choose EPG channel,
    save, notify, then refresh/reopen the current Live TV category.
    """
    sid = str(stream_id or "").strip()
    channel_name = str(name or sid or "Live TV Channel").strip()
    if not sid:
        sid = xbmcgui.Dialog().input("Live TV stream ID", type=xbmcgui.INPUT_ALPHANUM).strip()
    if not sid:
        notify("No channel selected", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    if not channel_name or channel_name == sid:
        channel_name = xbmcgui.Dialog().input("Channel name", defaultt=channel_name or sid, type=xbmcgui.INPUT_ALPHANUM).strip() or sid

    sources = _btv_epg_source_items()
    if not sources:
        notify("No EPG sources enabled", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    labels = [("⭐ " if source_id == "skygo" else "") + label for source_id, label, url in sources]
    src_idx = xbmcgui.Dialog().select("Choose EPG source", labels)
    if src_idx < 0:
        notify("EPG assignment cancelled")
        return
    source_id, source_label, url = sources[src_idx]

    progress = xbmcgui.DialogProgress()
    choices: List[Tuple[str, str]] = []
    try:
        progress_create(progress, ADDON_NAME, f"Loading {source_label} EPG", "Downloading and reading channels...")
        choices = xmltv_channel_choices(url, "manual_assign_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=False, progress=progress)
        if not choices:
            # Force a fresh download if cached list was empty/stale.
            choices = xmltv_channel_choices(url, "manual_assign_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=True, progress=progress)
        try:
            progress_update(progress, 100, "EPG loaded", f"Found {len(choices)} channels")
            xbmc.sleep(350)
        except Exception:
            pass
    except Exception as exc:
        log(f"Manual EPG context assign load failed: {exc}", xbmc.LOGERROR)
    finally:
        try:
            progress.close()
        except Exception:
            pass

    if not choices:
        xbmcgui.Dialog().ok(ADDON_NAME, f"No EPG channels found for {source_label}.\n\nTry Tools → EPG Manager → Refresh EPG Sources.")
        return

    target = norm_epg_key(channel_name)
    def score(pair: Tuple[str, str]) -> Tuple[int, str]:
        ch_id, lbl = pair
        key = norm_epg_key(lbl)
        if target and key == target:
            return (0, lbl.lower())
        if target and (target in key or key in target):
            return (1, lbl.lower())
        return (2, lbl.lower())
    sorted_choices = sorted(choices, key=score)[:5000]
    epg_labels = [label for _cid, label in sorted_choices]
    epg_idx = xbmcgui.Dialog().select(f"Assign EPG to {channel_name}", epg_labels)
    if epg_idx < 0:
        notify("EPG assignment cancelled")
        return
    epg_id, epg_label = sorted_choices[epg_idx]
    _btv_save_epg_assignment(source_id, epg_id, epg_label, sid, channel_name)
    _btv_finish_epg_assignment(channel_name, epg_label, cat_id)


def manual_epg_assign_to_stream(source_id: str, channel_id: str, channel_label: str, stream_id: str, name: str, cat_id: str = "") -> None:
    source_id = str(source_id or "")
    channel_id = str(channel_id or "")
    channel_label = str(channel_label or channel_id)
    stream_id = str(stream_id or "")
    name = str(name or stream_id or "Live TV Channel")
    if not stream_id or not channel_id:
        notify("Missing channel or EPG ID", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    _btv_save_epg_assignment(source_id, channel_id, channel_label, stream_id, name)
    _btv_finish_epg_assignment(name, channel_label, cat_id)


def manual_epg_source_channels_for_channel_menu(source_id: str, stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    data = manual_epg_load()
    src = (data.get("sources") or {}).get(source_id) or {}
    label = str(src.get("label") or source_id or "EPG Source")
    url = str(src.get("url") or "") or manual_epg_source_url(source_id)
    if source_id == "skygo":
        label = "Sky GO NZ"
        url = SKYGO_EPG_URL
    xbmcplugin.setPluginCategory(HANDLE, f"{label} EPG Channels")
    xbmcplugin.setContent(HANDLE, "videos")
    progress = xbmcgui.DialogProgress()
    choices: List[Tuple[str, str]] = []
    try:
        progress_create(progress, ADDON_NAME, f"Loading {label} EPG", f"Assigning to {name}")
        choices = xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id or label)[:80], force_refresh=False, progress=progress)
        if not choices:
            choices = xmltv_channel_choices(url, "manual_select_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id or label)[:80], force_refresh=True, progress=progress)
        try:
            progress_update(progress, 100, "EPG loaded", f"Found {len(choices)} channels")
            xbmc.sleep(300)
        except Exception:
            pass
    except Exception as exc:
        log(f"manual_epg_source_channels_for_channel v1.0.38 crashed: {exc}", xbmc.LOGERROR)
    finally:
        try:
            progress.close()
        except Exception:
            pass
    if not choices:
        add_action("No EPG channels found", "manual_epg_sources_for_channel", {"stream_id": stream_id, "name": name, "cat_id": cat_id, "title": title}, plot=f"Could not read channels from {label}.")
    else:
        add_action(f"EPG channels loaded: {len(choices)}", "manual_epg_source_info", {"source_id": source_id}, plot=f"Assigning to Bang TV channel:\n{name}")
        target = norm_epg_key(name)
        def score(pair: Tuple[str, str]) -> Tuple[int, str]:
            cid, lbl = pair
            key = norm_epg_key(lbl)
            if target and key == target:
                return (0, lbl.lower())
            if target and (target in key or key in target):
                return (1, lbl.lower())
            return (2, lbl.lower())
        for ch_id, ch_label in sorted(choices, key=score)[:5000]:
            add_action(str(ch_label), "manual_epg_assign_to_stream", {"source_id": source_id, "channel_id": ch_id, "channel_label": ch_label, "stream_id": stream_id, "name": name, "cat_id": cat_id}, plot=f"Assign EPG channel:\n{ch_label}\n\nEPG ID: {ch_id}\n\nTo Bang TV channel:\n{name}")
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
# ---- end v1.0.38 final manual EPG assign flow fix ----


# ---- v1.0.40 EPG assignment refresh + Kodi args fix ----
def _btv_finish_epg_assignment(name: str, channel_label: str, cat_id: str = "", title: str = "") -> None:
    """Finish manual EPG assignment and refresh the correct folder.

    Context-menu assignments launched from Live TV return to the Live TV category.
    EPG Manager assignments launched from Assign by Category return to that EPG
    Manager category channel list so the new mapping is visible immediately.
    """
    add_bang_notification(f"Manual EPG assigned: {name} → {channel_label}", "Updates")
    add_activity(f"Manual EPG assigned for {name}", "updates")
    try:
        xbmcgui.Dialog().notification(ADDON_NAME, f"EPG assigned to {name}", xbmcgui.NOTIFICATION_INFO, 4000)
    except Exception:
        pass
    try:
        xbmc.executebuiltin(f'Notification({ADDON_NAME},EPG assigned, refreshing,3000)')
    except Exception:
        pass
    try:
        xbmc.executebuiltin("Container.Refresh")
        xbmc.sleep(250)
    except Exception:
        pass
    try:
        if cat_id and title:
            xbmc.executebuiltin('Container.Update(%s,replace)' % build_url({"mode": "manual_epg_live_channels", "cat_id": str(cat_id), "title": str(title)}))
        elif cat_id:
            xbmc.executebuiltin('Container.Update(%s,replace)' % build_url({"mode": "live_streams", "cat_id": str(cat_id)}))
    except Exception as exc:
        log(f"EPG assign folder refresh failed: {exc}", xbmc.LOGWARNING)


def manual_epg_assign_to_stream(source_id: str, channel_id: str, channel_label: str, stream_id: str, name: str, cat_id: str = "", title: str = "") -> None:
    """Save EPG mapping from either EPG Manager or channel context menu.

    Kodi router passes title as the seventh arg for Assign by Category. Earlier
    builds did not accept it, causing 'Could not load folder' after selecting an
    EPG channel. Keep this signature broad and safe.
    """
    try:
        source_id = str(source_id or "")
        channel_id = str(channel_id or "")
        channel_label = str(channel_label or channel_id)
        stream_id = str(stream_id or "")
        name = str(name or stream_id or "Live TV Channel")
        if not stream_id or not channel_id:
            notify("Missing channel or EPG ID", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        _btv_save_epg_assignment(source_id, channel_id, channel_label, stream_id, name)
        # Clear cached live/category items so now/next and plot rebuild from the new manual EPG.
        try:
            metadata_cache_delete("live_streams", str(cat_id or ""))
        except Exception:
            pass
        _btv_finish_epg_assignment(name, channel_label, cat_id, title)
    except Exception as exc:
        log(f"manual_epg_assign_to_stream v1.0.40 crashed: {exc}", xbmc.LOGERROR)
        try:
            xbmcgui.Dialog().ok(ADDON_NAME, f"EPG assignment failed:\n{exc}")
        except Exception:
            pass


def manual_epg_assign(stream_id: str = "", name: str = "", cat_id: str = "") -> None:
    """Right click channel -> Assign EPG to this channel, with immediate refresh."""
    try:
        sid = str(stream_id or "").strip()
        channel_name = str(name or sid or "Live TV Channel").strip()
        if not sid:
            sid = xbmcgui.Dialog().input("Live TV stream ID", type=xbmcgui.INPUT_ALPHANUM).strip()
        if not sid:
            notify("No channel selected", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        if not channel_name or channel_name == sid:
            channel_name = xbmcgui.Dialog().input("Channel name", defaultt=channel_name or sid, type=xbmcgui.INPUT_ALPHANUM).strip() or sid
        sources = _btv_epg_source_items()
        if not sources:
            notify("No EPG sources enabled", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        labels = [("⭐ " if source_id == "skygo" else "") + label for source_id, label, url in sources]
        src_idx = xbmcgui.Dialog().select("Choose EPG source", labels)
        if src_idx < 0:
            notify("EPG assignment cancelled")
            return
        source_id, source_label, url = sources[src_idx]
        progress = xbmcgui.DialogProgress()
        choices: List[Tuple[str, str]] = []
        try:
            progress_create(progress, ADDON_NAME, f"Loading {source_label} EPG", "Downloading and reading channels...")
            choices = xmltv_channel_choices(url, "manual_assign_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=False, progress=progress)
            if not choices:
                choices = xmltv_channel_choices(url, "manual_assign_" + re.sub(r"[^A-Za-z0-9_]+", "_", source_id)[:80], force_refresh=True, progress=progress)
            try:
                progress_update(progress, 100, "EPG loaded", f"Found {len(choices)} channels")
                xbmc.sleep(350)
            except Exception:
                pass
        finally:
            try:
                progress.close()
            except Exception:
                pass
        if not choices:
            xbmcgui.Dialog().ok(ADDON_NAME, f"No EPG channels found for {source_label}.\n\nTry Tools → EPG Manager → Refresh EPG Sources.")
            return
        target = norm_epg_key(channel_name)
        def score(pair: Tuple[str, str]) -> Tuple[int, str]:
            ch_id, lbl = pair
            key = norm_epg_key(lbl)
            if target and key == target:
                return (0, lbl.lower())
            if target and (target in key or key in target):
                return (1, lbl.lower())
            return (2, lbl.lower())
        sorted_choices = sorted(choices, key=score)[:5000]
        epg_labels = [label for _cid, label in sorted_choices]
        epg_idx = xbmcgui.Dialog().select(f"Assign EPG to {channel_name}", epg_labels)
        if epg_idx < 0:
            notify("EPG assignment cancelled")
            return
        epg_id, epg_label = sorted_choices[epg_idx]
        _btv_save_epg_assignment(source_id, epg_id, epg_label, sid, channel_name)
        try:
            metadata_cache_delete("live_streams", str(cat_id or ""))
        except Exception:
            pass
        _btv_finish_epg_assignment(channel_name, epg_label, cat_id, "")
    except Exception as exc:
        log(f"manual_epg_assign v1.0.40 crashed: {exc}", xbmc.LOGERROR)
        try:
            xbmcgui.Dialog().ok(ADDON_NAME, f"EPG assignment failed:\n{exc}")
        except Exception:
            pass
# ---- end v1.0.40 EPG assignment refresh + Kodi args fix ----

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
    elif mode == "control_centre":
        bang_control_centre()
    elif mode == "notifications":
        notifications_menu()
    elif mode == "notification_view":
        notification_view(params.get("idx") or "0")
    elif mode == "notifications_mark_read":
        notifications_mark_read(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "notifications_clear":
        notifications_clear(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "notifications_export":
        notifications_export()
    elif mode == "activity_log":
        activity_log_menu()
    elif mode == "live_tv_manager":
        live_tv_manager_menu()
    elif mode == "manual_epg_manager":
        manual_epg_manager_menu()
    elif mode == "manual_epg_sources":
        manual_epg_sources_menu()
    elif mode == "manual_epg_live_categories":
        manual_epg_live_categories_menu()
    elif mode == "manual_epg_live_channels":
        manual_epg_live_channels_menu(params.get("cat_id") or "", params.get("title") or "Live TV")
    elif mode == "manual_epg_sources_for_channel":
        manual_epg_sources_for_channel_menu(params.get("stream_id") or "", params.get("name") or "", params.get("cat_id") or "", params.get("title") or "")
    elif mode == "manual_epg_source_channels_for_channel":
        manual_epg_source_channels_for_channel_menu(params.get("source_id") or "", params.get("stream_id") or "", params.get("name") or "", params.get("cat_id") or "", params.get("title") or "")
    elif mode == "manual_epg_assign_to_stream":
        manual_epg_assign_to_stream(params.get("source_id") or "", params.get("channel_id") or "", params.get("channel_label") or "", params.get("stream_id") or "", params.get("name") or "", params.get("cat_id") or "", params.get("title") or "")
    elif mode == "manual_epg_clear_channel":
        manual_epg_clear_channel(params.get("stream_id") or "", params.get("name") or "")
    elif mode == "manual_epg_source_info":
        manual_epg_source_info(params.get("source_id") or "")
    elif mode == "manual_epg_source_channels":
        manual_epg_source_channels_menu(params.get("source_id") or "")
    elif mode == "manual_epg_refresh_one_source":
        manual_epg_refresh_one_source(params.get("source_id") or ""); xbmc.executebuiltin("Container.Refresh")
    elif mode == "manual_epg_assign_from_source_channel":
        manual_epg_assign_from_source_channel(params.get("source_id") or "", params.get("channel_id") or "", params.get("channel_label") or "")
    elif mode == "manual_epg_refresh_sources":
        manual_epg_refresh_sources(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "manual_epg_export":
        manual_epg_export()
    elif mode == "manual_epg_import":
        manual_epg_import()
    elif mode == "manual_epg_recent":
        manual_epg_recent_menu()
    elif mode == "manual_epg_unassigned":
        manual_epg_unassigned_menu(False)
    elif mode == "manual_epg_missing":
        manual_epg_unassigned_menu(True)
    elif mode == "manual_epg_assignments":
        manual_epg_assignments_menu()
    elif mode == "manual_epg_add_source":
        manual_epg_add_source(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "manual_epg_assign":
        manual_epg_assign(params.get("stream_id") or "", params.get("name") or "", params.get("cat_id") or "")
    elif mode == "manual_epg_assign_prompt":
        manual_epg_assign("", "")
    elif mode == "manual_epg_clear_one":
        manual_epg_clear_one(params.get("key") or "")
    elif mode == "manual_epg_clear_all":
        manual_epg_clear_all()

    elif mode == "force_full_rebuild":
        force_full_rebuild(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "refresh_epg":
        refresh_epg(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "refresh_logos":
        refresh_logos(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "recently_changed":
        recently_changed_menu(params.get("view") or "categories")
    elif mode == "maintenance":
        maintenance_menu()
    elif mode == "vacuum_databases":
        vacuum_databases()
    elif mode == "weekly_maintenance":
        weekly_maintenance()
    elif mode == "reset_everything":
        reset_everything(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "statistics":
        statistics_menu()
    elif mode == "stream_health_centre":
        stream_health_centre()
    elif mode == "reset_stream_health":
        reset_stream_health(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "upcoming_sports":
        upcoming_sports_menu()
    elif mode == "backup_restore":
        backup_restore_menu()
    elif mode == "backup_choose":
        backup_choose()
    elif mode == "restore_choose":
        restore_choose(); xbmc.executebuiltin("Container.Refresh")
    elif mode == "advanced_settings":
        advanced_settings_menu()
    elif mode == "help_menu":
        help_menu()
    elif mode == "help_topic":
        help_topic(params.get("topic") or "faq")
    elif mode == "cache_menu":
        cache_menu()
    elif mode == "live_help":
        live_update_help()
    elif mode == "live_dashboard":
        live_dashboard()
    elif mode == "setup_native_pvr_guide":
        remove_disabled_export_files(show_notice=True)
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
    elif mode == "tv_guide_fallback":
        list_tv_guide_categories()
    elif mode == "tv_guide_category":
        list_tv_guide_channels(params.get("cat_id") or "", params.get("title") or "TV Guide", int(params.get("page") or 1))
    elif mode == "tv_guide_visual":
        open_visual_tv_guide(params.get("cat_id") or "", params.get("title") or "TV Guide")
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
