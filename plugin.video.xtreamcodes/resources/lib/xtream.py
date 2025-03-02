import requests

class XtreamAPI:
    def __init__(self, server, username, password):
        """ Initialize Xtream Codes API """
        self.server = server
        self.username = username
        self.password = password
        self.base_url = f"{server}/player_api.php"

    def get_user_info(self):
        """ Fetch User Account Information (Expiry Date, Active Connections, Status, etc.) """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=user_info"
        response = self._send_request(url)
        if response:
            user_info = response.get("user_info", {})
            return {
                "status": user_info.get("status", "Unknown"),
                "expiry_date": user_info.get("exp_date", "Unknown"),
                "active_cons": user_info.get("active_cons", "0"),
                "max_cons": user_info.get("max_connections", "0"),
                "is_trial": "Yes" if user_info.get("is_trial", "0") == "1" else "No",
                "created_at": user_info.get("created_at", "Unknown"),
                "allowed_output_formats": user_info.get("allowed_output_formats", "N/A")
            }
        return {}

    def get_live_categories(self):
        """ Fetch Live TV Categories """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_categories"
        return self._send_request(url) or []

    def get_live_streams(self, category_id):
        """ Fetch Live TV Channels for a Specific Category """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        return self._send_request(url) or []

    def get_vod_categories(self):
        """ Fetch VOD (Movies) Categories """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_vod_categories"
        return self._send_request(url) or []

    def get_vod_streams(self, category_id):
        """ Fetch VOD Movies/TV Shows for a Specific Category """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_vod_streams&category_id={category_id}"
        return self._send_request(url) or []

    def get_series_categories(self):
        """ Fetch TV Shows Categories """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_series_categories"
        return self._send_request(url) or []

    def get_series(self, category_id):
        """ Fetch TV Shows for a Specific Category """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_series&category_id={category_id}"
        return self._send_request(url) or []

    def get_series_info(self, series_id):
        """ Fetch Series Info (Episodes & Seasons) """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_series_info&series_id={series_id}"
        return self._send_request(url) or {}

    def get_episode_stream(self, episode_id):
        """ Fetch Stream URL for a TV Show Episode """
        return f"{self.server}/series/{self.username}/{self.password}/{episode_id}.m3u8"

    def get_short_epg(self, stream_id, limit=10):
        """ Fetch Short EPG (Electronic Program Guide) for a Live TV Channel """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_short_epg&stream_id={stream_id}&limit={limit}"
        return self._send_request(url) or []

    def get_full_epg(self):
        """ Fetch Full EPG for All Available Channels """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_simple_data_table"
        return self._send_request(url) or []

    def test_connection(self):
        """ Test Connection to Xtream Codes API """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=user_info"
        response = self._send_request(url)
        return response if response else {}

    def logout(self):
        """ Logout by Clearing Stored Credentials """
        return {"status": "Logged Out"}

    def _send_request(self, url):
        """ Send GET Request and Handle Errors """
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            print(f"XtreamAPI Error: {str(e)}")
        return None
