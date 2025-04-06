import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import json
import requests

addon = xbmcaddon.Addon()
handle = int(sys.argv[1])

params = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
mode = params.get("mode", "")
menu_url = params.get("url")
play_data = params.get("play")

# === SPECIAL NOTICE MODE ===
if mode == "notice":
    xbmcgui.Dialog().ok("SportShroud", "No live games at the moment.\nPlease check back later.")
    sys.exit()

# === PLAYBACK MODE ===
if mode == "play" and play_data:
    xbmc.log(f"[SportShroud] Playback triggered: {play_data}", xbmc.LOGINFO)
    try:
        sources = json.loads(play_data)
        if isinstance(sources, dict):
            sources = [sources]
        elif isinstance(sources, str):
            sources = [{"url": sources}]
    except Exception as e:
        xbmc.log(f"[SportShroud] Failed to parse play_data: {e}", xbmc.LOGERROR)
        sources = [{"url": play_data}]

    for source in sources:
        url = source.get("url")
        label = source.get("name", "Stream")
        plot = source.get("plot", "")
        thumb = source.get("thumb", "")

        if url:
            xbmc.log(f"[SportShroud] Playing: {label} | URL: {url}", xbmc.LOGINFO)
            li = xbmcgui.ListItem(label=label, path=url)
            li.setProperty("IsPlayable", "true")
            li.setInfo("video", {"title": label, "plot": plot})
            li.setArt({
                "thumb": thumb,
                "icon": thumb,
                "poster": thumb,
                "fanart": thumb
            })
            xbmcplugin.setResolvedUrl(handle, True, li)
            sys.exit()

    xbmcgui.Dialog().notification("Stream Error", "No valid stream available.", xbmcgui.NOTIFICATION_ERROR)
    xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
    sys.exit()

# === MAIN MENU FALLBACK ===
if not menu_url:
    menu_url = "https://raw.githubusercontent.com/hidemyassbaby/SportShroud/refs/heads/main/Main%20Menu/SportShroudMenu.json"

def build_url(query):
    return sys.argv[0] + '?' + urllib.parse.urlencode(query)

def get_json(url):
    try:
        xbmc.log(f"[SportShroud] Fetching JSON: {url}", xbmc.LOGINFO)
        response = requests.get(url)
        return response.json()
    except Exception as e:
        xbmc.log(f"[SportShroud] Failed to load JSON: {e}", xbmc.LOGERROR)
        return []

menu = get_json(menu_url)

def is_video_url(url):
    return url and any(url.lower().endswith(ext) for ext in [".m3u8", ".mp4", ".ts"])

def is_stream(item):
    return "fallback" in item or is_video_url(item.get("url", ""))

is_stream_list = isinstance(menu, list) and all(is_stream(i) for i in menu)

# === STREAM LIST MODE ===
if is_stream_list:
    xbmc.log(f"[SportShroud] Rendering stream list with {len(menu)} items", xbmc.LOGINFO)

    for item in menu:
        title = item.get("name", "Unnamed Stream")
        thumb = item.get("thumb", "")
        plot = item.get("plot", "")

        # Use fallback[0]'s metadata if outer has none
        if "fallback" in item and item["fallback"]:
            first = item["fallback"][0]
            thumb = first.get("thumb", thumb)
            plot = first.get("plot", plot)

        xbmc.log(f"[SportShroud] Stream Item - Title: {title}, Plot: {plot}, Thumb: {thumb}", xbmc.LOGINFO)

        if "fallback" in item:
            urls = [{
                "url": s.get("url"),
                "name": s.get("name", title),
                "plot": s.get("plot", plot),
                "thumb": s.get("thumb", thumb)
            } for s in item["fallback"]]
        else:
            urls = [{
                "url": item.get("url"),
                "name": title,
                "plot": plot,
                "thumb": thumb
            }]

        li = xbmcgui.ListItem(label=title)
        li.setProperty("IsPlayable", "true")
        li.setInfo("video", {"title": title, "plot": plot})
        li.setArt({
            "thumb": thumb,
            "icon": thumb,
            "poster": thumb,
            "fanart": thumb
        })

        play_url = build_url({"mode": "play", "play": json.dumps(urls)})
        xbmcplugin.addDirectoryItem(handle, play_url, li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)
    sys.exit()

# === FOLDER MENU MODE ===
xbmc.log(f"[SportShroud] Rendering folder menu with {len(menu)} items", xbmc.LOGINFO)
for item in menu:
    label = item.get("name", "Unknown")
    thumb = item.get("thumb", "")
    plot = item.get("plot", "")

    li = xbmcgui.ListItem(label=label)
    info = li.getVideoInfoTag()
    info.setTitle(label)
    info.setPlot(plot)
    if thumb:
        li.setArt({
            "thumb": thumb,
            "icon": thumb,
            "poster": thumb,
            "fanart": thumb
        })

    url = item.get("url", "")
    if url:
        dir_url = build_url({"name": label, "url": url})
        xbmcplugin.addDirectoryItem(handle, dir_url, li, isFolder=True)

xbmcplugin.endOfDirectory(handle)
    