import requests
import xbmcaddon
import re

class XtreamAPI:
    def __init__(self):
        """ Initialize Xtream Codes API with User Credentials """
        addon = xbmcaddon.Addon()
        self.username = addon.getSetting("username").strip()
        self.password = addon.getSetting("password").strip()
        self.base_url = "https://m3ufilter.media4u.top/player_api.php"
        self.stream_url = "https://m3ufilter.media4u.top/live"

    def test_connection(self):
        """ Test connection by checking account info """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=user_info"
        response = self._send_request(url)
        return bool(response and isinstance(response, dict) and "user_info" in response)

    def get_live_categories(self):
        """ Fetch Live TV Categories and Clean Names """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        categories = self._send_request(url)
        if not categories or not isinstance(categories, list):
            return []

        # Remove special characters from category names
        for category in categories:
            category["category_name"] = self._clean_text(category["category_name"])
        return categories

    def get_live_streams(self, category_id):
        """ Fetch Live TV Streams and Clean Names """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        streams = self._send_request(url)

        if not streams or not isinstance(streams, list):
            return []

        # Clean stream names
        for stream in streams:
            stream["title"] = self._clean_text(stream.get("title", "Unknown Stream"))
            stream["play_url"] = f"{self.stream_url}/{self.username}/{self.password}/{stream['stream_id']}.ts"
        return streams

    def _send_request(self, url):
        """ Send GET Request with Timeout Handling """
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and response.text.strip():
                return response.json()
        except requests.exceptions.RequestException:
            return None
        return None

    def _clean_text(self, text):
        """ Remove Emojis and Special Characters """
        return re.sub(r"[^\w\s\|]", "", text)  # Keeps letters, numbers, spaces, and pipes (|)
