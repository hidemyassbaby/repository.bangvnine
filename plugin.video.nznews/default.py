import sys, urllib.parse, xbmcplugin, xbmcgui
from resources.lib.scraper import get_articles

url = sys.argv[0]
handle = int(sys.argv[1])

def list_articles():
    for item in get_articles():
        li = xbmcgui.ListItem(label=item['title'])
        li.setInfo('video', {'title': item['title'], 'plot': item['content']})
        xbmcplugin.addDirectoryItem(handle, url + "?id=" + urllib.parse.quote(item['title']), li, False)
    xbmcplugin.endOfDirectory(handle)

if __name__ == "__main__":
    list_articles()
