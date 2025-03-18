import requests

class XtreamAPI:
    def __init__(self, base_url, username, password):
        """Initialize XtreamAPI with user credentials"""
        self.base_url = base_url
        self.username = username
        self.password = password

    def _request(self, action, params=None):
        """Make a request to the Xtream API"""
        if params is None:
            params = {}
        params.update({
            "username": self.username,
            "password": self.password
        })
        url = f"{self.base_url}?action={action}"
        response = requests.get(url, params=params)
        return response.json() if response.status_code == 200 else None

    def get_live_categories(self):
        """Fetch live TV categories"""
        return self._request("get_live_categories")

    def get_live_streams(self, category_id):
        """Fetch streams from a category"""
        return self._request("get_live_streams", {"category_id": category_id})
