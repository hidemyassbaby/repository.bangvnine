# -*- coding: utf-8 -*-
"""Bang TV background metadata service.

Keeps Kodi folder browsing fast by filling metadata.db after a page has loaded.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.parse
from typing import Any, Dict, List, Tuple

import xbmc
import xbmcaddon
import xbmcvfs
import requests

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name") or "Bang TV"
SERVER = "http://freqdns.com"
PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile")).rstrip("/\\")
if not xbmcvfs.exists(PROFILE_PATH):
    xbmcvfs.mkdirs(PROFILE_PATH)

METADATA_DB_FILE = os.path.join(PROFILE_PATH, "metadata.db")
BACKGROUND_QUEUE_FILE = os.path.join(PROFILE_PATH, "metadata_queue.json")
METADATA_TTL_SECONDS = 30 * 24 * 60 * 60
REQUEST_TIMEOUT = 6
IDLE_SLEEP = 2
RATE_SLEEP = 0.35
MAX_PER_CYCLE = 30
STARTUP_PRELOAD_FILE = os.path.join(PROFILE_PATH, "startup_preload.json")
CACHE_FILE = os.path.join(PROFILE_PATH, "api_cache.json")
CACHE_TTL_SECONDS = 10 * 60
LIVE_UPDATE_STATE_FILE = os.path.join(PROFILE_PATH, "live_update_state.json")
LIVE_AUTO_CHECK_SECONDS = 30 * 60
LIVE_HIGH_ACTIVITY_SECONDS = 10 * 60
LIVE_HIGH_ACTIVITY_CHANGE_THRESHOLD = 20

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Kodi BangTV/1.0.7 background-service",
    "Accept": "application/json,text/plain,*/*",
    "Connection": "keep-alive",
})


def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID} service] {message}", level)


def setting_bool(key: str, default: bool = False) -> bool:
    value = (ADDON.getSetting(key) or "").strip().lower()
    if not value:
        return default
    return value in {"true", "1", "yes", "on"}


def quote(value: Any) -> str:
    return urllib.parse.quote_plus(str(value or ""))


def get_creds() -> Tuple[str, str]:
    return (ADDON.getSetting("username") or "").strip(), (ADDON.getSetting("password") or "").strip()


def xc_api_url(endpoint: str) -> str:
    user, pwd = get_creds()
    sep = "&" if "?" in endpoint else "?"
    return f"{SERVER}/{endpoint}{sep}username={quote(user)}&password={quote(pwd)}"


def redact_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        safe_query = [(k, "***" if k.lower() in {"username", "password"} else v) for k, v in query]
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(safe_query), parsed.fragment))
    except Exception:
        return str(url)


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


def metadata_key(content_type: str, item_id: Any) -> str:
    return f"{content_type}:{item_id}"


def metadata_get(content_type: str, item_id: Any, ttl: int = METADATA_TTL_SECONDS) -> Dict[str, Any]:
    if item_id in (None, ""):
        return {}
    try:
        now = int(time.time())
        with metadata_db() as conn:
            row = conn.execute("SELECT updated, data FROM metadata_cache WHERE cache_key=?", (metadata_key(content_type, item_id),)).fetchone()
        if not row:
            return {}
        updated, raw = row
        if ttl > 0 and now - int(updated or 0) > ttl:
            return {}
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"metadata_get failed: {exc}", xbmc.LOGWARNING)
        return {}


def metadata_set(content_type: str, item_id: Any, data: Dict[str, Any]) -> None:
    if item_id in (None, "") or not isinstance(data, dict) or not data:
        return
    try:
        with metadata_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata_cache(cache_key, content_type, item_id, updated, data) VALUES (?, ?, ?, ?, ?)",
                (metadata_key(content_type, item_id), content_type, str(item_id), int(time.time()), json.dumps(data, ensure_ascii=False)),
            )
    except Exception as exc:
        log(f"metadata_set failed: {exc}", xbmc.LOGWARNING)


def read_queue() -> List[Dict[str, Any]]:
    try:
        if not os.path.exists(BACKGROUND_QUEUE_FILE):
            return []
        with open(BACKGROUND_QUEUE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception as exc:
        log(f"queue read failed: {exc}", xbmc.LOGWARNING)
        return []


def write_queue(items: List[Dict[str, Any]]) -> None:
    try:
        with open(BACKGROUND_QUEUE_FILE, "w", encoding="utf-8") as fh:
            json.dump(items[:5000], fh, ensure_ascii=False)
    except Exception as exc:
        log(f"queue save failed: {exc}", xbmc.LOGWARNING)


def http_json(url: str) -> Any:
    try:
        response = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        log(f"Timeout: {redact_url(url)}", xbmc.LOGWARNING)
    except requests.exceptions.RequestException as exc:
        log(f"HTTP error: {redact_url(str(exc))}", xbmc.LOGWARNING)
    except ValueError as exc:
        log(f"JSON error: {exc}", xbmc.LOGWARNING)
    return None


def load_api_cache() -> Dict[str, Any]:
    try:
        if not os.path.exists(CACHE_FILE):
            return {}
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_api_cache(cache: Dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
    except Exception as exc:
        log(f"api cache save failed: {exc}", xbmc.LOGWARNING)


def load_live_state() -> Dict[str, Any]:
    try:
        if not os.path.exists(LIVE_UPDATE_STATE_FILE):
            return {}
        with open(LIVE_UPDATE_STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_live_state(state: Dict[str, Any]) -> None:
    try:
        with open(LIVE_UPDATE_STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception as exc:
        log(f"live state save failed: {exc}", xbmc.LOGWARNING)


def live_cache_keys_for_category(cat_id: str) -> Tuple[str, str]:
    cat_url = xc_api_url("player_api.php?action=get_live_categories")
    streams_url = xc_api_url(f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}")
    return cat_url, streams_url


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
        return {"name": str(item.get("category_name") or item.get("name") or ""), "parent_id": str(item.get("parent_id") or "")}
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


def smart_live_background_check(force: bool = False) -> Dict[str, Any]:
    user, pwd = get_creds()
    if not user or not pwd:
        return {"checked": False, "reason": "Not logged in"}
    now = int(time.time())
    state = load_live_state()
    high_until = int(state.get("high_activity_until", 0) or 0)
    interval = LIVE_HIGH_ACTIVITY_SECONDS if high_until > now else LIVE_AUTO_CHECK_SECONDS
    live_opened_at = int(state.get("live_opened_at", 0) or 0)
    recently_opened = now - live_opened_at < 90 * 60
    # Check often only when Live TV was recently used, otherwise back off to every 6 hours.
    if not recently_opened:
        interval = 6 * 60 * 60
    if not force and now - int(state.get("last_check", 0) or 0) < interval:
        return {"checked": False, "reason": "Not due yet"}

    result: Dict[str, Any] = {"checked": True, "time": now, "category_changes": {}, "channel_changes": {}, "changed_category_ids": []}
    try:
        cache = load_api_cache()
        cat_url, _unused = live_cache_keys_for_category("")
        old_categories = cache.get(cat_url, {}).get("data") if isinstance(cache.get(cat_url), dict) else []
        new_categories = http_json(cat_url)
        if isinstance(new_categories, list):
            result["category_changes"] = compare_live_maps(live_signature_map(old_categories, True), live_signature_map(new_categories, True))
            cache[cat_url] = {"time": now, "data": new_categories}
        all_streams_url = xc_api_url("player_api.php?action=get_live_streams")
        old_streams = cache.get(all_streams_url, {}).get("data") if isinstance(cache.get(all_streams_url), dict) else []
        new_streams = http_json(all_streams_url)
        if isinstance(new_streams, list):
            changes = compare_live_maps(live_signature_map(old_streams, False), live_signature_map(new_streams, False))
            result["channel_changes"] = changes
            cache[all_streams_url] = {"time": now, "data": new_streams}
            old_map = live_signature_map(old_streams, False)
            new_map = live_signature_map(new_streams, False)
            changed_cat_ids = set()
            for sid in changes.get("added", []) + changes.get("changed", []):
                cid = (new_map.get(sid) or {}).get("category_id")
                if cid:
                    changed_cat_ids.add(str(cid))
            for sid in changes.get("removed", []):
                cid = (old_map.get(sid) or {}).get("category_id")
                if cid:
                    changed_cat_ids.add(str(cid))
            result["changed_category_ids"] = sorted(changed_cat_ids)
            total_changes = int(changes.get("added_count", 0)) + int(changes.get("removed_count", 0)) + int(changes.get("changed_count", 0))
            if total_changes >= LIVE_HIGH_ACTIVITY_CHANGE_THRESHOLD:
                state["high_activity_until"] = now + (3 * 60 * 60)
            for cid in result["changed_category_ids"][:30]:
                _cu, streams_url = live_cache_keys_for_category(cid)
                cache[streams_url] = {"time": now, "data": [item for item in new_streams if isinstance(item, dict) and str(item.get("category_id") or "") == str(cid)]}
        else:
            result["error"] = "Could not read latest channel list"
        save_api_cache(cache)
    except Exception as exc:
        result["error"] = str(exc)
        log(f"smart live background check failed: {exc}", xbmc.LOGWARNING)
    state["last_check"] = now
    state["last_result"] = result
    save_live_state(state)
    ch = result.get("channel_changes") if isinstance(result.get("channel_changes"), dict) else {}
    total = int(ch.get("added_count", 0) or 0) + int(ch.get("removed_count", 0) or 0) + int(ch.get("changed_count", 0) or 0)
    if total:
        log(f"Live TV playlist updated in background: {total} channel changes")
    return result


def cache_http_json(url: str, timeout: int = REQUEST_TIMEOUT) -> Any:
    cache = load_api_cache()
    now = int(time.time())
    cached = cache.get(url)
    if isinstance(cached, dict) and now - int(cached.get("time", 0)) < CACHE_TTL_SECONDS:
        return cached.get("data")
    try:
        response = SESSION.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        cache[url] = {"time": now, "data": data}
        save_api_cache(cache)
        return data
    except requests.exceptions.RequestException as exc:
        log(f"preload HTTP error: {redact_url(str(exc))}", xbmc.LOGWARNING)
    except ValueError as exc:
        log(f"preload JSON error: {exc}", xbmc.LOGWARNING)
    return None


def decode_epg_text(v: Any) -> str:
    text = str(v or "")
    try:
        import base64
        raw = base64.b64decode(text + "===")
        decoded = raw.decode("utf-8", "ignore").strip()
        return decoded or text
    except Exception:
        return text


def fetch_and_cache_epg(stream_id: Any) -> None:
    if stream_id in (None, ""):
        return
    if metadata_get("epg", stream_id, ttl=6 * 60 * 60):
        return
    data = http_json(xc_api_url(f"player_api.php?action=get_short_epg&stream_id={quote(stream_id)}&limit=2"))
    if not isinstance(data, dict):
        return
    listings = data.get("epg_listings") or []
    if not isinstance(listings, list) or not listings:
        return
    now = listings[0] if isinstance(listings[0], dict) else {}
    nxt = listings[1] if len(listings) > 1 and isinstance(listings[1], dict) else {}
    plot = ""
    if now:
        plot = "Now: " + decode_epg_text(now.get("title"))
        start = now.get("start") or now.get("start_timestamp") or ""
        end = now.get("end") or now.get("stop") or now.get("end_timestamp") or ""
        if start or end:
            plot += f" ({start} - {end})"
        desc = decode_epg_text(now.get("description"))
        if desc:
            plot += "\n" + desc
    if nxt:
        title = decode_epg_text(nxt.get("title"))
        if title:
            plot += "\n\nNext: " + title
    if plot:
        metadata_set("epg", stream_id, {"plot": plot})


def startup_preload_pending() -> bool:
    return os.path.exists(STARTUP_PRELOAD_FILE)


def clear_startup_preload() -> None:
    try:
        if os.path.exists(STARTUP_PRELOAD_FILE):
            os.remove(STARTUP_PRELOAD_FILE)
    except Exception:
        pass


def preload_startup_data() -> None:
    if not startup_preload_pending():
        return
    user, pwd = get_creds()
    if not user or not pwd:
        return
    log("Startup preload started")
    # Core menus, channels and category lists are loaded into the API cache first.
    endpoints = [
        "player_api.php",
        "player_api.php?action=get_live_categories",
        "player_api.php?action=get_live_streams",
        "player_api.php?action=get_vod_categories",
        "player_api.php?action=get_series_categories",
        "player_api.php?action=get_vod_streams",
        "player_api.php?action=get_series",
    ]
    live_streams = []
    for endpoint in endpoints:
        data = cache_http_json(xc_api_url(endpoint), timeout=20)
        if endpoint.endswith("get_live_streams") and isinstance(data, list):
            live_streams = data
    # Prime a small amount of EPG in the background so it does not block metadata filling.
    count = 0
    for channel in live_streams[:25]:
        if not isinstance(channel, dict):
            continue
        stream_id = channel.get("stream_id")
        fetch_and_cache_epg(stream_id)
        count += 1
        time.sleep(0.15)
    clear_startup_preload()
    log(f"Startup preload finished, EPG primed for {count} channels")


def fetch_vod(stream_id: str) -> Dict[str, Any]:
    data = http_json(xc_api_url(f"player_api.php?action=get_vod_info&vod_id={quote(stream_id)}"))
    if not isinstance(data, dict):
        return {}
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    movie_data = data.get("movie_data") if isinstance(data.get("movie_data"), dict) else {}
    merged = dict(movie_data)
    merged.update(info)
    if merged:
        merged["mediatype"] = "movie"
    return merged


def fetch_series(series_id: str) -> Dict[str, Any]:
    data = http_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={quote(series_id)}"))
    if not isinstance(data, dict):
        return {}
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    meta = dict(info)
    if meta:
        meta["mediatype"] = "tvshow"
        metadata_set("series", series_id, meta)
    episodes = data.get("episodes") if isinstance(data.get("episodes"), dict) else {}
    for season_num, season_eps in episodes.items():
        if not isinstance(season_eps, list):
            continue
        for ep in season_eps:
            if not isinstance(ep, dict):
                continue
            ep_id = ep.get("id") or ep.get("episode_id")
            if ep_id in (None, ""):
                continue
            ep_info = ep.get("info") if isinstance(ep.get("info"), dict) else {}
            title = ep.get("title") or ep.get("name") or ep_info.get("name") or "Episode"
            ep_num = ep.get("episode_num") or ep.get("episode") or ep_info.get("episode")
            merged = dict(info)
            merged.update(ep_info)
            merged.update({
                "title": title,
                "name": title,
                "mediatype": "episode",
                "season": int(season_num) if str(season_num).isdigit() else season_num,
                "episode": int(ep_num) if str(ep_num).isdigit() else ep_num,
                "episode_num": int(ep_num) if str(ep_num).isdigit() else ep_num,
                "plot": ep_info.get("plot") or ep_info.get("description") or ep.get("plot") or ep.get("description") or info.get("plot") or info.get("description") or "",
                "releasedate": ep_info.get("releasedate") or ep_info.get("releaseDate") or ep_info.get("air_date") or "",
            })
            metadata_set("episode", ep_id, merged)
    return meta


def process_item(item: Dict[str, Any]) -> bool:
    content_type = str(item.get("type") or "")
    item_id = str(item.get("id") or "")
    if content_type not in {"vod", "series"} or not item_id:
        return True
    if metadata_get(content_type, item_id):
        return True
    if content_type == "vod":
        meta = fetch_vod(item_id)
    else:
        meta = fetch_series(item_id)
    if meta:
        metadata_set(content_type, item_id, meta)
        return True
    return False


def run() -> None:
    monitor = xbmc.Monitor()
    log("Background metadata service started")
    while not monitor.abortRequested():
        if not setting_bool("background_metadata_service", True) or not setting_bool("enhanced_metadata", True):
            monitor.waitForAbort(IDLE_SLEEP)
            continue
        user, pwd = get_creds()
        if not user or not pwd:
            monitor.waitForAbort(IDLE_SLEEP)
            continue
        queue = read_queue()
        if not queue:
            preload_startup_data()
            smart_live_background_check(False)
            monitor.waitForAbort(IDLE_SLEEP)
            continue
        # Current page metadata is more important than startup EPG/channel preload.
        queue = sorted(queue, key=lambda i: 0 if isinstance(i, dict) and i.get("priority") else 1)
        write_queue(queue)
        remaining = queue[:]
        processed = 0
        changed = False
        while remaining and processed < MAX_PER_CYCLE and not monitor.abortRequested():
            item = remaining.pop(0)
            if process_item(item):
                changed = True
            else:
                # Put failed items at the end, but do not hammer the server.
                remaining.append(item)
            processed += 1
            write_queue(remaining)
            monitor.waitForAbort(RATE_SLEEP)
        if changed:
            # Safe and light refresh: lets descriptions appear after the cache is filled.
            try:
                xbmc.executebuiltin("Container.Refresh")
            except Exception:
                pass
        monitor.waitForAbort(IDLE_SLEEP)
    log("Background metadata service stopped")


if __name__ == "__main__":
    run()
