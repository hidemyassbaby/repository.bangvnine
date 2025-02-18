import xbmcaddon
import xbmcplugin
import xbmcgui
import sys
import urllib.parse
import requests

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_ID = ADDON.getAddonInfo('id')
BASE_URL = 'http://m3ufilter.media4u.top'
USERNAME = 'media4u'
PASSWORD = 'media4u'

API_URL = f'{BASE_URL}/player_api.php?username={USERNAME}&password={PASSWORD}'

def main_menu():
    add_directory('Live TV', 'live_tv', 'icon.png')
    add_directory('Movies', 'movies', 'icon.png')
    add_directory('TV Shows', 'tv_shows', 'icon.png')
    add_directory('Account Info', 'account_info', 'icon.png')
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def add_directory(name, action, icon):
    url = f'{sys.argv[0]}?action={action}'
    li = xbmcgui.ListItem(name)
    li.setArt({'icon': icon})
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, li, True)

def live_tv():
    response = requests.get(f'{API_URL}&action=get_live_categories').json()
    for category in response:
        add_directory(category['category_name'], f'live_category&cat_id={category["category_id"]}', 'icon.png')
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def movies():
    response = requests.get(f'{API_URL}&action=get_vod_categories').json()
    for category in response:
        add_directory(category['category_name'], f'movie_category&cat_id={category["category_id"]}', 'icon.png')
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def tv_shows():
    response = requests.get(f'{API_URL}&action=get_series_categories').json()
    for category in response:
        add_directory(category['category_name'], f'series_category&cat_id={category["category_id"]}', 'icon.png')
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def account_info():
    response = requests.get(f'{API_URL}&action=user_info').json()
    xbmcgui.Dialog().ok('Account Info', f"Username: {response['user_info']['username']}\nExpiry: {response['user_info']['exp_date']}")

def router(params):
    if params.get('action') == 'live_tv':
        live_tv()
    elif params.get('action') == 'movies':
        movies()
    elif params.get('action') == 'tv_shows':
        tv_shows()
    elif params.get('action') == 'account_info':
        account_info()
    else:
        main_menu()

if __name__ == '__main__':
    params = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
    router(params)
