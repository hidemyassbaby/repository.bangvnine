import requests
from bs4 import BeautifulSoup as bs
from urllib.parse import urlparse
import xbmc
from typing import List

class JetLink:
    def __init__(self, address, name=None, resolveurl=False):
        self.address = address
        self.name = name
        self.resolveurl = resolveurl

class JetItem:
    def __init__(self, name, links=[], icon=None, params=None):
        self.name = name
        self.links = links
        self.icon = icon
        self.params = params

class RugbyVideo:
    domains = ["rugby24.net"]
    user_agent = "Mozilla/5.0"
    timeout = 10

    def get_items(self, params=None):
        items = []
        base_url = f"https://{self.domains[0]}"
        url = f"{base_url}?page={params['page']}" if params else base_url
        headers = {"User-Agent": self.user_agent, "Referer": base_url}
        r = requests.get(url, headers=headers, timeout=self.timeout).text
        soup = bs(r, 'html.parser')
        matches = soup.find_all(class_='short_item block_elem')
        for match in matches:
            name = match.h3.a.text.replace('Full Game Replay ', '').rstrip(' Rugby')
            xbmc.sleep(50)
            link = f"{base_url}{match.a['href']}"
            icon = f"{base_url}{match.a.img['src']}"
            items.append(JetItem(name, links=[JetLink(link, resolveurl=True)], icon=icon))

        next_page = int(params['page']) + 1 if params else 2
        items.append(JetItem(f"[COLOR yellow]Page {next_page}[/COLOR]", links=[], params={"page": next_page}))
        return items

    def get_links(self, url: str) -> List[JetLink]:
        links = []
        base_url = f"https://{urlparse(url).netloc}/"
        headers = {"User-Agent": self.user_agent, "Referer": base_url}
        r = requests.get(url, headers=headers, timeout=self.timeout).text
        soup = bs(r, 'html.parser')

        for button in soup.find_all(class_='su-button'):
            link = button.get('href')
            if not link:
                continue
            if link.startswith('//'):
                link = f'https:{link}'
            if any(x in link for x in ['nfl-replays', 'nfl-video', 'basketball-video']):
                r = requests.get(link, headers=headers, timeout=self.timeout).text
                _soup = bs(r, 'html.parser')
                iframe = _soup.find('iframe')
                if iframe:
                    link = iframe.get('src')
                    if not link:
                        continue
            if link.startswith('//'):
                link = f'https:{link}'
            title = urlparse(link).netloc
            links.append(JetLink(link, name=title, resolveurl=True))

        for iframe in soup.find_all('iframe'):
            link = iframe.get('src')
            if link and link.startswith('//'):
                link = f'https:{link}'
            title = urlparse(link).netloc
            links.append(JetLink(link, name=title, resolveurl=True))
        return links
