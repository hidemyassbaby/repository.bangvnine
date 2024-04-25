import requests
from bs4 import BeautifulSoup
import xbmcgui
import xbmcplugin
import sys
import re

# Function to fetch HTML content from a URL
def fetch_html(url):
    response = requests.get(url)
    return response.text

# Function to extract movie information using BeautifulSoup
def extract_movies(html):
    soup = BeautifulSoup(html, 'html.parser')
    movies = []

    # Find movie elements
    for element in soup.find_all('div', {'class': 'flw-item'}):
        movie = {}

        # Extract movie title
        title_element = element.find('h2', {'class': 'film-name'})
        movie['title'] = title_element.a['title']

        # Extract movie URL
        movie['url'] = title_element.a['href']

        # Extract poster URL
        poster_element = element.find('img', {'class': 'film-poster-img'})
        movie['poster'] = poster_element['data-src']

        # Extract year and duration using regex
        info_element = element.find('div', {'class': 'fd-infor'})
        info_text = info_element.get_text()
        year_match = re.search(r'(\d{4})', info_text)
        duration_match = re.search(r'(\d+)m', info_text)
        movie['year'] = year_match.group(1) if year_match else ''
        movie['duration'] = duration_match.group(1) if duration_match else ''

        movies.append(movie)

    return movies

# Function to create a playable list for Kodi
def create_playlist(movies):
    playlist = []
    for index, movie in enumerate(movies):
        list_item = xbmcgui.ListItem(label=movie['title'])
        list_item.setArt({'thumb': movie['poster']})
        list_item.setInfo('video', {'plot': f"Year: {movie['year']}, Duration: {movie['duration']} minutes"})
        url = sys.argv[0] + '?action=play_movie&movie_index=' + str(index)
        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=list_item, isFolder=False)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

# Function to play a selected movie
def play_movie(movie_index):
    movie = playlist[int(movie_index)]
    play_url = movie['url']  # Here, you would provide the actual movie URL for playback
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, xbmcgui.ListItem(path=play_url))

# Main entry point
if __name__ == '__main__':
    url = 'https://zoechip.cc/movie?page=1'  # URL of the website with movie listings
    html_content = fetch_html(url)
    movies = extract_movies(html_content)
    create_playlist(movies)
