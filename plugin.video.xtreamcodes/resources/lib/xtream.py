import requests

class XtreamAPI:
    def __init__(self, server, username, password):
        self.server = server
        self.username = username
        self.password = password
        self.base_url = f"{server}/player_api.php"

    def get_live_categories(self):
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_live_streams(self, category_id):
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_vod_categories(self):
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_vod_categories"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_vod_streams(self, category_id):
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_vod_streams&category_id={category_id}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_series_categories(self):
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_series_categories"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_series(self, category_id):
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_series&category_id={category_id}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_epg(self, stream_id):
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_short_epg&stream_id={stream_id}&limit=10"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []
