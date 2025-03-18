import requests
import time

class XtreamAPI:
    def __init__(self, base_url, username, password):
        """Initialize the API with user credentials."""
        self.base_url = base_url
        self.username = username
        self.password = password

    def _request(self, action, params=None, retries=5, delay=3):
        """Helper function to handle API requests with retries."""
        if params is None:
            params = {}
        
        params.update({"username": self.username, "password": self.password, "action": action})

        for attempt in range(retries):
            try:
                response = requests.get(self.base_url, params=params, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                print(f"[Media4u TV] ⚠ API request failed ({e}), attempt {attempt+1}/{retries}")
                time.sleep(delay)
        
        print(f"[Media4u TV] ❌ API request failed after {retries} retries: {action}")
        return None

    def get_live_categories(self):
        """Fetch live TV categories."""
        return self._request("get_live_categories")

    def get_live_streams(self, category_id):
        """Fetch live TV streams for a given category."""
        return self._request("get_live_streams", {"category_id": category_id})
