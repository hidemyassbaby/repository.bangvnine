import feedparser, requests
from bs4 import BeautifulSoup

FEEDS = [
    "https://www.rnz.co.nz/rss/national.xml",
    "https://www.stuff.co.nz/rss",
    "https://www.odt.co.nz/news/feed"
]

def get_full_content(link):
    try:
        html = requests.get(link, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        if "rnz" in link:
            body = soup.select_one(".article__body") or soup.select_one("article")
        elif "stuff" in link:
            body = soup.select_one("div[data-testid='body']") or soup.select_one("article")
        elif "odt" in link:
            body = soup.select_one("div.node-content")
        return body.get_text(separator="\n").strip() if body else "Content unavailable"
    except:
        return "Error loading article."

def get_articles():
    items = []
    for url in FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            content = get_full_content(entry.link)
            items.append({'title': entry.title, 'content': content})
    return items
