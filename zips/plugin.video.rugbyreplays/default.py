import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import os

from resources.lib.rugbyvideo import RugbyVideo

addon_handle = int(sys.argv[1])
args = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
xbmcplugin.setContent(addon_handle, 'videos')

extractor = RugbyVideo()

if 'action' in args and args['action'] == 'play':
    links = extractor.get_links(args['url'])
    if links:
        play_item = xbmcgui.ListItem(path=links[0].address)
        xbmcplugin.setResolvedUrl(addon_handle, True, listitem=play_item)
else:
    page = int(args.get('page', 1))
    items = extractor.get_items(params={"page": page})
    for item in items:
        if item.links:
            url = f"{sys.argv[0]}?action=play&url={urllib.parse.quote(item.links[0].address)}"
        else:
            url = f"{sys.argv[0]}?page={item.params['page']}"
        li = xbmcgui.ListItem(label=item.name)
        li.setArt({'thumb': item.icon or '', 'icon': item.icon or '', 'fanart': item.icon or ''})
        xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=not item.links)
    xbmcplugin.endOfDirectory(addon_handle)
