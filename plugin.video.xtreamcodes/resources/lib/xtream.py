import requests
import xbmcaddon

class XtreamAPI:
    def __init__(self):
        """ Initialize Xtream Codes API with User-Defined Credentials """
        addon = xbmcaddon.Addon()
        self.username = addon.getSetting("username").strip()
        self.password = addon.getSetting("password").strip()
        self.base_url = "https://m3ufilter.media4u.top/player_api.php"

    def test_connection(self):
        """ Test Connection to Xtream Codes API """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        response = self._send_request(url)

        if response and isinstance(response, list):
            print("✅ API is reachable, categories exist!")
            return True  # API is working
        print("❌ API connection failed!")
        return False

    def get_live_categories(self):
        """ Fetch Live TV Categories (Handles Empty Response) """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        response = self._send_request(url)
        return response if response else []

    def get_live_streams(self, category_id):
        """ Fetch Live TV Streams (Handles Empty Response) """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        response = self._send_request(url)
        return response if response else []

    def _send_request(self, url):
        """ Send GET Request and Handle Errors """
        print(f"🌐 API Request: {url}")  # Debugging output
        try:
            response = requests.get(url, timeout=10)
            print(f"🔍 API Response: {response.text}")  # Debugging output
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ XtreamAPI Error: {str(e)}")
        return None
