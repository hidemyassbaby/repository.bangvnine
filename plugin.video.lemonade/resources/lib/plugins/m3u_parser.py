import xbmcaddon
import requests
import os
import re
import json
from ..plugin import Plugin

addon_icon = xbmcaddon.Addon().getAddonInfo('icon')
PATH = xbmcaddon.Addon().getAddonInfo("path")

class m3u(Plugin):
    name = "m3u"
    description = "add support for m3u lists"
    priority = 2
    
    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36'
        self.headers = {"User-Agent":self.user_agent, "Connection":'keep-alive', 'Accept':'audio/webm,audio/ogg,udio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_list(self, url: str):
        if url.startswith('m3u|'):
            url = url.split('|')[1]
            if url.startswith("file://"):
                url = url.replace("file://", "")
                with open(os.path.join(PATH, "xml", url), 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            return self.session.get(url).text
    
    def parse_list(self, url: str, response):
        if url.endswith('.m3ua') or '#EXTINF' in response:
            if url.endswith('.m3ua'):
                url = url[:-1]
            if url.startswith('m3u|'):
                cat = url.split('|')[2]
                url = url.split('|')[1]
                return self.get_catlist(url, cat)
            return self.categories_menu(url)
        elif url.startswith('m3u|'):
            url = url.split('|')[1]
            cat = url.split('|')[2]
            return self.get_catlist(url, cat)
    
    def categories_menu(self, url):
        item_list = []
        for cat in self.get_categories(url):
            item_list.append(
                            {
                             'type': 'dir',
                             'title': cat,
                             'link': f'm3u|{url}|{cat}',
                             'thumbnail': addon_icon
                               }
                            )
        return item_list
    
    def get_categories(self, url):
        cats = []
        for v in json.loads(self.EpgRegex(url))['items']:
            cat = v.get('group_title')
            if not cat in cats:
                cats.append(cat)
        return sorted(cats)

    def EpgRegex(self, url):
        m3udata = []
        if url.startswith('http'):
            content = self.session.get(url).text
        elif url.startswith("file://"):
            url = url.replace("file://", "")
            with open(os.path.join(PATH, "xml", url), 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        match = re.compile(r'#EXTINF:(.+?),(.*?)[\n\r]+([^\n]+)').findall(content)
        for other,channel_name,stream_url in match:
            tvg_id='';tvg_name='';tvg_country='';tvg_language='';tvg_logo='';group_title=''
            if 'tvg-id' in other:
                tvg_id = self.re_me(other, 'tvg-id=[\'"](.*?)[\'"]').strip()
            if 'tvg-name' in other:
                tvg_name = self.re_me(other, 'tvg-name=[\'"](.*?)[\'"]').strip()
            if 'tvg-country' in other:
                tvg_country = self.re_me(other, 'tvg-country=[\'"](.*?)[\'"]').strip()
            if 'tvg-language' in other:
                tvg_language = self.re_me(other, 'tvg-language=[\'"](.*?)[\'"]').strip()
            if 'tvg-logo' in other:
                tvg_logo = self.re_me(other, 'tvg-logo=[\'"](.*?)[\'"]').strip()
            if 'group-title' in other:
                group_title = self.re_me(other, 'group-title=[\'"](.*?)[\'"]').strip()
            if group_title == '':
                if tvg_country != '':
                    group_title = tvg_country
                else:
                    group_title = 'Uncategorized'
            if tvg_name == '' and channel_name != '':
                tvg_name = channel_name
            if channel_name =='' and tvg_name !='':
                channel_name = tvg_name
            if tvg_id == '':
                tvg_id = f"{''.join(tvg_name.lower().split())}.{tvg_country}"
            m3udata.append(
                    {
                        "tvg_id": tvg_id,
                        "tvg_name": tvg_name,
                        "tvg_country": tvg_country,
                        "tvg_language": tvg_language,
                        "tvg_logo": tvg_logo,
                        "group_title": group_title,
                        "channel_name": channel_name,
                        "stream_url": stream_url.strip()
                        }
                            )
        return json.dumps({'items': m3udata})
        
    def get_catlist(self, url, category):
        item_list = []
        for v in json.loads(self.EpgRegex(url))['items']:
            if v.get('group_title') == category:
                title = v.get('tvg_name', 'Unknown Channel')
                link = v.get('stream_url', '')
                thumbnail = v.get('tvg_logo', addon_icon)
                item_list.append(
                        {
                         'type': 'item',
                         'title': title,
                         'link': link,
                         'thumbnail': thumbnail
                        }
                            )
        return item_list
    
    def re_me(self,data, re_patten):
        match = ''
        m = re.search(re_patten, data)
        if m is not None:
            match = m.group(1)
        else:
            match = ''
        return match