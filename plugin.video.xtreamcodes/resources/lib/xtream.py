import requests

class XtreamAPI:
    def __init__(self, server, username, password):
        """ Initialize Xtream Codes API """
        self.server = server
        self.username = username
        self.password = password
        self.base_url = f"{server}/player_api.php"

    def test_connection(self):
        """ Test Connection to Xtream Codes API (Ensures login works) """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=user_info"
        response = self._send_request(url)
        if response and "user_info" in response:
            return True  # Login successful
        return False  # Login failed

    def get_user_info(self):
        """ Fetch User Account Information """
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
        response = self._send_request(url)
        return response if response else []

    def get_live_streams(self, category_id):
        """ Fetch Live TV Channels for a Specific Category """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        response = self._send_request(url)
        return response if response else []

    def _send_request(self, url):
        """ Send GET Request and Handle Errors """
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            print(f"XtreamAPI Error: {str(e)}")
        return None
