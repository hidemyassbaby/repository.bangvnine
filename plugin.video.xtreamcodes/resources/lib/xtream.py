import requests
import xbmcaddon

class XtreamAPI:
    def __init__(self):
        """ Initialize Xtream Codes API with User-Defined Credentials """
        addon = xbmcaddon.Addon()
        self.username = addon.getSetting("username").strip()
        self.password = addon.getSetting("password").strip()
        self.base_url = "https://m3ufilter.media4u.top/player_api.php"
        self.stream_url = "https://m3ufilter.media4u.top/live"

    def test_connection(self):
        """ Test Connection to Xtream Codes API by Checking Live Categories """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        response = self._send_request(url)
        return response is not None and isinstance(response, list)

    def get_live_categories(self):
        """ Fetch Latest Live TV Categories """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        return self._send_request(url) or []

    def get_live_streams(self, category_id):
        """ Fetch Live TV Streams Dynamically """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        streams = self._send_request(url)

        if not streams:
            return []

        # Generate Playable URLs
        for stream in streams:
            stream["play_url"] = f"{self.stream_url}/{self.username}/{self.password}/{stream['stream_id']}.ts"

        return streams

    def _send_request(self, url):
        """ Send GET Request and Handle Errors """
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and response.text.strip():
                return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ XtreamAPI Error: {str(e)}")
        return None
