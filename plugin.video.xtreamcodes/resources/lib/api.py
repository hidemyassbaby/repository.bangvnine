import requests

class XtreamAPI:
    def __init__(self, server_url, username, password):
        self.server_url = server_url
        self.username = username
        self.password = password

    def get_auth_url(self):
        return f"{self.server_url}/player_api.php?username={self.username}&password={self.password}"

    def get_live_categories(self):
        url = f"{self.get_auth_url()}&action=get_live_categories"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_live_streams(self, category_id):
        url = f"{self.get_auth_url()}&action=get_live_streams&category_id={category_id}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_vod_streams(self):
        url = f"{self.get_auth_url()}&action=get_vod_streams"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []

    def get_series(self):
        url = f"{self.get_auth_url()}&action=get_series"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []
