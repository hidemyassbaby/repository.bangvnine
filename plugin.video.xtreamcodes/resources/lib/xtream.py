import requests

class XtreamAPI:
    def __init__(self, server, username, password):
        self.server = server
        self.username = username
        self.password = password
        self.base_url = f"{server}/player_api.php"

    def get_live_categories(self):
        """ Fetch Live TV categories """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_live_streams(self, category_id):
        """ Fetch Live TV channels for a category """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_vod_categories(self):
        """ Fetch VOD categories """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_vod_categories"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_vod_streams(self, category_id):
        """ Fetch VOD movies/shows """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_vod_streams&category_id={category_id}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []
