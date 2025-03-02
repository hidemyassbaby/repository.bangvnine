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
        if response.status_code == 200:
            return response.json()
        return []
