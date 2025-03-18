import requests

class XtreamAPI:
    def __init__(self, username, password):
        """ Initialize Xtream Codes API with Custom API URL """
        self.username = username
        self.password = password
        self.base_url = f"https://m3ufilter.media4u.top/player_api.php"

    def test_connection(self):
        """ Test Connection to Xtream Codes API """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=user_info"
        response = self._send_request(url)
        if response and "user_info" in response:
            print("✅ Login successful!")
            return True  # Login successful
        print("❌ Login failed: Invalid credentials or server issue.")
        return False

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
        return self._send_request(url) or []

    def get_live_streams(self, category_id):
        """ Fetch Live TV Channels for a Specific Category """
        url = f"{self.base_url}?username={self.username}&password={self.password}&action=get_live_streams&category_id={category_id}"
        return self._send_request(url) or []

    def _send_request(self, url):
        """ Send GET Request and Handle Errors """
        print(f"🌐 Sending request: {url}")  # Debugging output
        try:
            response = requests.get(url, timeout=10)
            print(f"🔍 API Response: {response.text}")  # Debugging output
            if response.status_code == 200 and response.text.strip():
                return response.json()
            else:
                print(f"❌ Error: Received HTTP {response.status_code} or empty response.")
        except requests.exceptions.RequestException as e:
            print(f"❌ XtreamAPI Error: {str(e)}")
        return None
