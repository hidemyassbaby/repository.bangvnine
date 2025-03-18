import requests
import xbmc

class XtreamAPI:
    def __init__(self, base_url, username, password):
        """Initialize API with user credentials."""
        self.base_url = base_url
        self.username = username
        self.password = password

    def _request(self, action, params=None):
        """Send a request to the Xtream API."""
        if params is None:
            params = {}

        params.update({"username": self.username, "password": self.password, "action": action})
        try:
            response = requests.get(self.base_url, params=params, timeout=10)

            if response.status_code != 200 or not response.text.strip():
                xbmc.log(f"[Media4u TV] API Error: {response.status_code}", xbmc.LOGERROR)
                return None

            return response.json()
        except requests.exceptions.RequestException as e:
            xbmc.log(f"[Media4u TV] API Request Error: {e}", xbmc.LOGERROR)
            return None

    def get_live_categories(self):
        """Get live TV categories."""
        data = self._request("get_live_categories")
        return data if isinstance(data, list) else []

    def get_live_streams(self, category_id):
        """Get live streams for a given category."""
        data = self._request("get_live_streams", {"category_id": category_id})
        return data if isinstance(data, list) else []

    def get_stream_url(self, stream_id):
        """Get the stream URL for a favorite stream."""
        return f"{self.base_url}?username={self.username}&password={self.password}&stream_id={stream_id}&action=play"
