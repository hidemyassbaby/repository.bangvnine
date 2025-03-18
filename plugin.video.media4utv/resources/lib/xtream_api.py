import requests
import json
import xbmcaddon
import xbmc

class XtreamAPI:
    BASE_URL = "https://m3ufilter.media4u.top/player_api.php"

    def __init__(self):
        """Initialize Xtream API by reading username & password from settings.xml"""
        self.addon = xbmcaddon.Addon(id="plugin.video.media4utv")
        self.username = self.addon.getSetting("username")
        self.password = self.addon.getSetting("password")
        self.session = requests.Session()

    def get_api_url(self, action, extra_params=""):
        """Generate full API request URL."""
        return f"{self.BASE_URL}?username={self.username}&password={self.password}&action={action}{extra_params}"

    def fetch_data(self, url):
        """Fetch data from API and return parsed JSON."""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and not data:
                return None  # Handle empty lists gracefully
            return data
        except requests.exceptions.RequestException as e:
            xbmc.log(f"[Media4U TV] API Request Failed: {e}", xbmc.LOGERROR)
            return None

    def validate_credentials(self):
        """Check if credentials are valid and fetch account info."""
        url = self.get_api_url("user_info")
        data = self.fetch_data(url)
        if not data or "user_info" not in data:
            return None
        return data["user_info"]

    def get_live_categories(self):
        """Retrieve all Live TV categories."""
        url = self.get_api_url("get_live_categories")
        data = self.fetch_data(url)
        return data if data else []

    def get_live_streams(self, category_id):
        """Retrieve live streams for a specific category."""
        url = self.get_api_url("get_live_streams", f"&category_id={category_id}")
        data = self.fetch_data(url)
        return data if data else []

    def search_streams(self, query):
        """Search streams by name."""
        categories = self.get_live_categories()
        if not categories:
            return []

        results = []
        for category in categories:
            streams = self.get_live_streams(category["category_id"])
            if streams:
                results.extend([s for s in streams if query.lower() in s["name"].lower()])
        return results

if __name__ == "__main__":
    # Testing API
    api = XtreamAPI()
    print("Validating Credentials...")
    user_info = api.validate_credentials()
    if user_info:
        print(json.dumps(user_info, indent=4))
    else:
        print("Invalid Credentials or Server Unreachable.")

    print("\nFetching Live Categories...")
    categories = api.get_live_categories()
    if categories:
        print(json.dumps(categories[:5], indent=4))  # Display only first 5 categories
    else:
        print("No categories found.")

    print("\nFetching Live Streams from First Category...")
    if categories:
        streams = api.get_live_streams(categories[0]["category_id"])
        if streams:
            print(json.dumps(streams[:5], indent=4))  # Display only first 5 streams
        else:
            print("No streams found.")
