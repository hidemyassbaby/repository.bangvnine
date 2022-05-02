from ..DI import DI

from ..plugin import Plugin
import json, xbmcgui

try:
    from resources.lib.util.common import *
except ImportError:
    from .resources.lib.util.common import *


class TMDB(Plugin):
    name = "tmdb"

    def get_list(self, url):
        if url.startswith("tmdb"):
            api = TMDB_API()
            if "tmdb_tv_show" in url:
                show_id = url.replace("tmdb_tv_show(", "")[:-1].split(",")
                return api.handle_show(show_id)
            elif "tmdb_tv_season" in url:
                show_id, season = url.replace("tmdb_tv_season(", "")[:-1].split(",")
                return api.handle_season(show_id, season)
            else:
                splitted = url.split("/")
                kind = splitted[1]                
                if len(splitted) == 3:
                    list_id = splitted[2]                    
                else:
                    genre_kind = splitted[2]
                    list_id = splitted[3]
                if kind == "list":
                    return api.handle_list(list_id)
                elif kind == "movie":
                    return api.handle_movies(list_id)
                elif kind == "tvshow":
                    return api.handle_show(list_id)
                elif kind == "tvshow_list":
                    return api.handle_shows(list_id)
                elif kind == "keyword":
                    return api.handle_keyword(list_id)
                elif kind == "collection":
                    return api.handle_collection(list_id)
                elif kind == "genre":
                    return api.handle_genre(list_id, genre_kind)
                elif kind == "company":
                    return api.handle_company(list_id, genre_kind)
                elif kind == "year":
                    return api.handle_year(list_id, genre_kind)

    def process_item(self, item):
        tag = item["type"]
        tmdb_tag = item.get("tmdb", False)
        if tag == "dir" and tmdb_tag:
            link = f"/get_list/tmdb/{tmdb_tag}"
            is_dir = True
            thumbnail = item.get("thumbnail", "")
            fanart = item.get("fanart", "")
            list_item = xbmcgui.ListItem(
                item.get("title", item.get("name", "")), offscreen=True
            )
            list_item.setArt({"thumb": thumbnail, "fanart": fanart})
            item["list_item"] = list_item
            item["link"] = link
            item["is_dir"] = is_dir
            return item
        try:
            if "imdb_id" in item and "tmdb_id" not in item:
                api = TMDB_API()
                item["tmdb_id"] = api.get_tmdb_id(item["imdb_id"])
            if "tmdb_id" in item:
                api = TMDB_API()
                if item.get("content") == "movie":
                    movie = api.get_movie(item["tmdb_id"])
                    thumbnail = api.image_url + movie.get("poster_path", "")
                    fanart = api.image_url + movie.get("backdrop_path", "")
                    summary = movie.get("overview", "<empty summary>")
                    list_item = xbmcgui.ListItem(
                        item.get("title", item.get("name", "")), offscreen=True
                    )
                    list_item.setArt({"thumb": thumbnail, "fanart": fanart})
                    list_item.setInfo(
                        "video",
                        {"plot": summary, "plotoutline": summary, "mediatype": "movie"},
                    )
                    item["imdb_id"] = movie["imdb_id"]
                    item["year"] = movie["release_date"].split("-")[0]
                    item[
                        "link"
                    ] = f'microjenscrapers/play/{item["content"]}|{movie["title"]}|{movie["imdb_id"]}|{item["year"]}'
                elif item.get("content") == "episode":
                    show = api.get_show(item["tmdb_id"])
                    thumbnail = api.image_url + show.get("poster_path", "")
                    fanart = api.image_url + show.get("backdrop_path", "")
                    summary = show.get("overview", "<empty summary>")
                    list_item = xbmcgui.ListItem(
                        item.get("title", item.get("name", "")), offscreen=True
                    )
                    list_item.setArt({"thumb": thumbnail, "fanart": fanart})
                    list_item.setInfo(
                        "video",
                        {
                            "plot": summary,
                            "plotoutline": summary,
                            "mediatype": "episode",
                        },
                    )
                    item["year"] = show["first_air_date"].split("-")[0]
                    item["tv_show_title"] = show["name"]
                    item[
                        "link"
                    ] = f'microjenscrapers/play/{item["content"]}|{show["title"]}|{show["tmdb_id"]}|{item["year"]}'
                item["thumbnail"] = thumbnail
                item["fanart"] = fanart
                item["summary"] = summary
                item["list_item"] = list_item
                item["is_dir"] = False
                return item
            else:
                return False
        except:
            pass


class TMDB_API:
    @property
    def headers(self):
        return {
            "content-type": "application/json;charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
        }

    base_url = "https://api.themoviedb.org"
    image_url = "https://image.tmdb.org/t/p/w500"
    api_key = ownAddon.getSetting("tmdb.api_key") or ""
    access_token = ownAddon.getSetting("tmdb.access_token") or ""
    session = DI.session

    def get_list(self, list_id: int, page: int = 1):
        response = self.session.get(
            f"{self.base_url}/4/list/{list_id}?api_key={self.api_key}&page={page}",
            headers=self.headers,
        )
        tmdb_list = response.json()
        results = tmdb_list["results"]
        if tmdb_list["total_pages"] > page:
            results.extend(self.get_list(list_id, page + 1))
        return results

    def get_collection(self, list_id: int):
        response = self.session.get(
            f"{self.base_url}/3/collection/{list_id}?api_key={self.api_key}",
            headers=self.headers,
        )
        tmdb_list = response.json()
        results = tmdb_list["parts"]
        return results

    def get_company(self, list_id: int):
        response = self.session.get(
                f"{self.base_url}/3/discover/movie?api_key={self.api_key}&with_companies={list_id}",
                headers=self.headers,
                )
        tmdb_list = response.json()
        results = tmdb_list["results"]
        return results

    def get_year(self, list_id: int):
        response = self.session.get(
                f"{self.base_url}/3/discover/movie?api_key={self.api_key}&year={list_id}",
                headers=self.headers,
                )
        tmdb_list = response.json()
        results = tmdb_list["results"]
        return results

    def get_genre(self, list_id: int, kind):
        if kind == "movies":
            response = self.session.get(
                f"{self.base_url}/3/discover/movie?api_key={self.api_key}&with_genres={list_id}",
                headers=self.headers,
                )
        elif kind == "shows":
            response = self.session.get(
                f"{self.base_url}/3/discover/tv?api_key={self.api_key}&with_genres={list_id}",
                headers=self.headers,
                )
        tmdb_list = response.json()
        results = tmdb_list["results"]
        return results

    def get_keyword(self, list_id: int):
        response = self.session.get(
            f"{self.base_url}/3/keyword/{list_id}/movies?api_key={self.api_key}",
            headers=self.headers,
        )
        tmdb_list = response.json()
        results = tmdb_list["results"]
        return results

    def get_show(self, show_id: int):
        response = self.session.get(
            f"{self.base_url}/3/tv/{show_id}?api_key={self.api_key}",
            headers=self.headers,
        )
        tmdb_show = response.json()
        return tmdb_show

    def get_season(self, show_id: int, season: int):
        response = self.session.get(
            f"{self.base_url}/3/tv/{show_id}/season/{season}?api_key={self.api_key}",
            headers=self.headers,
        )
        tmdb_season = response.json()
        return tmdb_season

    def get_movie(self, movie_id: int):
        response = self.session.get(
            f"{self.base_url}/3/movie/{movie_id}?api_key={self.api_key}",
            headers=self.headers,
        )
        tmdb_movie = response.json()
        return tmdb_movie

    def get_movies(self, endpoint: str):
        response = self.session.get(
            f"{self.base_url}/3/movie/{endpoint}?api_key={self.api_key}",
            headers=self.headers,
        )
        tmdb_movie = response.json()
        return tmdb_movie["results"]

    def process_items(self, items):
        items = [self.handle_item(item) for item in items]
        return items

    def handle_item(self, item):
        media_type = item["media_type"]
        if media_type == "movie":
            return self.handle_movie_xml(item)
        elif media_type == "tv":
            return self.handle_show_xml(item)

    def handle_movie_xml(self, movie):
        if movie.get("poster_path"):
            thumbnail = self.image_url + movie["poster_path"]
        else:
            thumbnail = ""
        if movie.get("backdrop_path"):
            fanart = self.image_url + movie["backdrop_path"]
        else:
            fanart = ""
        return {
            "type": "item",
            "title": movie["title"],
            "content": "movie",
            "summary": movie["overview"],
            "tmdb_id": movie["id"],
            "thumbnail": thumbnail,
            "fanart": fanart,
            "link": ["search(Search)"],
        }

    def handle_movies_xml(self, movies):
        return [self.handle_movie_xml(movie) for movie in movies]
    
    def get_shows(self, endpoint: str):
        response = self.session.get(
            f"{self.base_url}/3/tv/{endpoint}?api_key={self.api_key}",
            headers=self.headers,
        )
        tmdb_show = response.json()
        return tmdb_show["results"]

    def handle_show_xml(self, show):
        try:
            year = show["first_air_date"].split("-")[0]
        except KeyError:
            year = 0
        return {
            "type": "dir",
            "title": show["name"],
            "link": f'tmdb_tv_show({show["id"]}, {year}, {show["name"]})',
            "summary": show["overview"],
            "thumbnail": self.image_url + show.get("poster_path", ""),
            "fanart": self.image_url + show.get("backdrop_path", ""),
        }
    
    def handle_shows_xml(self, shows):
        return [self.handle_show_xml(show) for show in shows]
    
    def handle_shows(self, list_id: str):
        j = json.dumps({"items": self.handle_shows_xml(self.get_shows(list_id))})
        return j
    
    def handle_show(self, show_id: int):
        if isinstance(show_id, list):
            show_id = show_id[0]
        return json.dumps(
            {"items": self.handle_season_xml(self.get_show(show_id.strip()))}
        )

    def handle_season(self, show_id: int, season: int):
        api = TMDB_API()
        show = api.get_show(show_id)

        return json.dumps(
            {
                "items": self.handle_episodes_xml(
                    self.get_season(show_id.strip(), season.strip()), show
                )
            }
        )

    def handle_season_xml(self, show):
        result = []
        for season in show["seasons"]:
            if season["poster_path"]:
                thumbnail = self.image_url + season["poster_path"]
            else:
                thumbnail = ""
            result.append(
                {
                    "type": "dir",
                    "title": season["name"],
                    "link": f'tmdb_tv_season({show["id"]}, {season["season_number"]})',
                    "summary": season["overview"],
                    "thumbnail": thumbnail,
                    "fanart": self.image_url + show.get("backdrop_path", ""),
                }
            )
        return result

    def handle_episodes_xml(self, season, show):
        show_title = show["name"]
        year = show["first_air_date"].split("-")[0]
        result = []
        for episode in season["episodes"]:
            if episode.get("still_path"):
                thumbnail = self.image_url + episode["still_path"]
            else:
                thumbnail = ""
            if episode.get("poster_path"):
                fanart = self.image_url + episode["poster_path"]
            else:
                fanart = ""
            result.append(
                {
                    "type": "item",
                    "title": episode["name"],
                    "summary": episode["overview"],
                    "content": "episode",
                    "tmdb_id": episode["id"],
                    "thumbnail": thumbnail,
                    "tv_show_title": show_title,
                    "year": year,
                    "fanart": fanart,
                    "season": season["season_number"],
                    "episode": episode["episode_number"],
                    "premiered": episode["air_date"],
                    "link": ["search(Search)"],
                }
            )
        return result

    def handle_list(self, list_id: int):
        return json.dumps({"items": self.process_items(self.get_list(list_id))})

    def handle_collection(self, list_id: int):
        return json.dumps(
            {
                "items": [
                    self.handle_movie_xml(item) for item in self.get_collection(list_id)
                ]
            }
        )

    def handle_company(self, list_id: int, kind):
        return json.dumps(
            {
                "items": [
                    self.handle_movie_xml(item) for item in self.get_company(list_id)
                ]
            }
        )

    def handle_year(self, list_id: int, kind):
        return json.dumps(
            {
                "items": [
                    self.handle_movie_xml(item) for item in self.get_year(list_id)
                ]
            }
        )

    def handle_genre(self, list_id: int, kind):
        if kind == "movies":
            return json.dumps(
                {
                    "items": [
                        self.handle_movie_xml(item) for item in self.get_genre(list_id, kind)
                    ]
                }
            )
        elif kind == "shows":
            return json.dumps(
                {
                    "items": [
                        self.handle_show_xml(item) for item in self.get_genre(list_id, kind)
                    ]
                }
            )

    def handle_keyword(self, list_id: int):
        return json.dumps(
            {
                "items": [
                    self.handle_movie_xml(item) for item in self.get_keyword(list_id)
                ]
            }
        )

    def handle_movies(self, list_id: str):
        j = json.dumps({"items": self.handle_movies_xml(self.get_movies(list_id))})
        return j

    def get_tmdb_id(self, imdb_id: str):
        response = self.session.get(
            f"{self.base_url}/3/movie/{imdb_id}/external_ids?api_key={self.api_key}",
            headers=self.headers,
        )
        r = response.json()
        return r["id"]
