#!/usr/bin/env python3
"""
YouTube Subscription Auto-Adder with Logging

This script automatically finds new videos from your YouTube subscriptions
and adds them to a custom "Automated Watch Later" playlist.

Requirements:
- Python 3.6+
- google-api-python-client
- google-auth-oauthlib
- google-auth-httplib2

Setup (two modes):

  Mode 1 - Desktop/PC (browser available):
    1. Create a project in Google Cloud Console (https://console.cloud.google.com/)
    2. Enable YouTube Data API v3
    3. Create OAuth 2.0 credentials (Desktop application)
    4. Download the JSON file, rename it to 'client_secrets.json' and place it next to this script
    5. Install requirements: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
    6. Run the script — a browser window will open automatically for authentication

  Mode 2 - Headless/Docker/Server (no browser):
    1. Create a project in Google Cloud Console (https://console.cloud.google.com/)
    2. Enable YouTube Data API v3
    3. Create OAuth 2.0 credentials (TVs and Limited Input devices)
    4. Set environment variables: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET
       (or place client_secrets.json next to the script as a fallback)
    5. Install requirements: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
    6. Run the script — it will display a short URL and code to validate from any device

The script detects automatically which mode to use based on browser availability.
"""

import os
import pickle
import datetime
import time
import sys
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

# If modifying these SCOPES, delete the file token.pickle.
# Note: youtube.force-ssl is intentionally omitted — it is incompatible with the
# Device Flow (headless/Docker mode) and redundant since the API uses HTTPS by default.
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube',
]

# File to store the last check time
LAST_CHECK_FILE = 'last_check_time.txt'

# ---------------------------------------------------------------------------
# Content filter settings — controlled via environment variables
#
# INCLUDE_SHORTS=true/false        Include YouTube Shorts  (default: false)
# INCLUDE_TEASERS=true/false       Include teasers/trailers by title keyword (default: false)
#
# Examples (docker-compose.yml):
#   environment:
#     - INCLUDE_SHORTS=true
#     - INCLUDE_TEASERS=true
# ---------------------------------------------------------------------------

def _env_bool(name, default):
    """Read a boolean environment variable. Accepts 'true'/'false' (case-insensitive)."""
    val = os.environ.get(name, '').strip().lower()
    if val == 'true':
        return True
    if val == 'false':
        return False
    return default

INCLUDE_SHORTS    = _env_bool('INCLUDE_SHORTS',    default=False)
INCLUDE_TEASERS   = _env_bool('INCLUDE_TEASERS',   default=False)

# File to cache subscribed channel IDs
SUBSCRIPTIONS_CACHE_FILE = 'subscriptions_cache.json'

# How many hours before refreshing the subscriptions cache
SUBSCRIPTIONS_CACHE_TTL_HOURS = 24

# File to persist videos discovered but not yet added to the playlist
PENDING_VIDEOS_FILE = 'pending_videos.json'

# File to persist scan progress (last channel index + partial shorts cache)
SCAN_PROGRESS_FILE = 'scan_progress.json'

# File to cache the "Automated Watch Later" playlist ID
PLAYLIST_ID_CACHE_FILE = 'playlist_id.txt'

# Global log file handle
log_file = None

class QuotaTracker:
    """
    Tracks YouTube Data API v3 quota consumption during a run.

    Google does not expose a real-time quota endpoint, so this class
    counts units locally based on known costs per endpoint.
    The reported total reflects only what this script consumed — other
    apps on the same Google Cloud project may have used additional quota.

    Quota resets daily at midnight Pacific Time.
    Daily limit: 10,000 units.
    """

    COSTS = {
        'subscriptions.list':    1,
        'activities.list':       1,
        'playlistItems.list':    1,
        'playlistItems.insert':  50,
        'playlists.list':        1,
        'playlists.insert':      50,
        'channels.list':         1,
        'search.list':           100,
    }
    DAILY_LIMIT = 10_000

    def __init__(self):
        self._total = 0
        self._calls = {}

    def track(self, endpoint):
        """Record one call to the given endpoint."""
        cost = self.COSTS.get(endpoint, 1)
        self._total += cost
        self._calls[endpoint] = self._calls.get(endpoint, 0) + 1

    @property
    def total(self):
        return self._total

    def report(self):
        """Log a summary of quota consumed during this run."""
        log_print("\n=== API Quota consumed ===")
        for ep, count in sorted(self._calls.items(), key=lambda x: -x[1] * self.COSTS.get(x[0], 1)):
            unit = self.COSTS.get(ep, 1)
            total_cost = count * unit
            log_print(f"  {ep}: {count}× ({unit} unit/call) = {total_cost} units")
        pct = round(self._total / self.DAILY_LIMIT * 100, 1)
        log_print(f"  Total: {self._total} / {self.DAILY_LIMIT} units ({pct}% of daily quota)")
        if self._total > self.DAILY_LIMIT * 0.8:
            log_print("  WARNING: more than 80% of the daily quota consumed.")
        log_print("")

quota = QuotaTracker()

class QuotaExceededException(Exception):
    """Raised when the YouTube API quota is exceeded."""
    pass

def setup_logging():
    """Setup logging to file in log folder."""
    global log_file

    # Create log folder if it doesn't exist
    log_folder = 'logs'
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    # Create log filename with current date and time
    current_time = datetime.datetime.now()
    log_filename = current_time.strftime("%Y-%m-%d_%H-%M-%S.txt")
    log_path = os.path.join(log_folder, log_filename)

    # Open log file for writing
    log_file = open(log_path, 'w', encoding='utf-8')

    # Write header to log file
    log_file.write(f"YouTube Auto-Adder Log - {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.write("=" * 50 + "\n\n")
    log_file.flush()

    return log_path

def log_print(message):
    """Print message to console and write to log file."""
    global log_file
    print(message)
    if log_file:
        log_file.write(message + "\n")
        log_file.flush()

def cleanup_logging():
    """Close log file."""
    global log_file
    if log_file:
        log_file.close()

def load_credentials(token_file):
    """Load credentials from token file if it exists."""
    if os.path.exists(token_file):
        log_print("Loading saved credentials...")
        with open(token_file, 'rb') as token:
            return pickle.load(token)
    return None

def handle_refresh_error(token_file):
    """Handle token refresh error by removing the invalid token file."""
    if os.path.exists(token_file):
        os.remove(token_file)
        log_print("Deleted invalid token file.")
    return None

def _has_browser():
    """Detect whether a runnable browser is available on this system."""
    import webbrowser
    try:
        webbrowser.get()
        return True
    except webbrowser.Error:
        return False

def _get_client_credentials():
    """
    Retrieve client_id and client_secret from environment variables or client_secrets.json.

    Priority:
      1. YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET environment variables
      2. client_secrets.json file in the current directory

    Returns:
        Tuple (client_id, client_secret)
    """
    client_id = os.environ.get('YOUTUBE_CLIENT_ID')
    client_secret = os.environ.get('YOUTUBE_CLIENT_SECRET')

    if client_id and client_secret:
        log_print("Using OAuth credentials from environment variables.")
        return client_id, client_secret

    if os.path.exists('client_secrets.json'):
        import json
        log_print("Using OAuth credentials from client_secrets.json.")
        with open('client_secrets.json') as f:
            secrets = json.load(f)
        cfg = secrets.get('installed') or secrets.get('web')
        if not cfg:
            log_print("ERROR: client_secrets.json format not recognized.")
            sys.exit(1)
        return cfg['client_id'], cfg['client_secret']

    log_print("ERROR: No OAuth credentials found.")
    log_print("Provide YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET environment variables,")
    log_print("or place a client_secrets.json file in the working directory.")
    sys.exit(1)

def _get_credentials_browser_flow(client_id, client_secret):
    """
    Authenticate via browser (Desktop/PC mode).
    Opens a local browser window and handles the OAuth redirect automatically.
    """
    import json
    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    }
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    return flow.run_local_server(port=0)

def _get_credentials_device_flow(client_id, client_secret):
    """
    Authenticate via Device Flow (headless/Docker/server mode).
    Displays a short URL and user code — validate from any device, no interaction needed here.
    """
    import json
    import urllib.request
    import urllib.parse

    # Step 1: Request device code and user code
    data = urllib.parse.urlencode({
        'client_id': client_id,
        'scope': ' '.join(SCOPES)
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/device/code', data=data)
    response = json.loads(urllib.request.urlopen(req).read())

    device_code = response['device_code']
    interval = response.get('interval', 5)

    log_print("\n=== AUTHENTIFICATION REQUISE ===")
    log_print(f"1. Va sur : {response['verification_url']}")
    log_print(f"2. Entre le code : {response['user_code']}")
    log_print("En attente de la validation...\n")

    # Step 2: Poll until the user completes authentication
    while True:
        time.sleep(interval)
        poll_data = urllib.parse.urlencode({
            'client_id': client_id,
            'client_secret': client_secret,
            'device_code': device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
        }).encode()

        try:
            poll_req = urllib.request.Request('https://oauth2.googleapis.com/token', data=poll_data)
            token_response = json.loads(urllib.request.urlopen(poll_req).read())

            from google.oauth2.credentials import Credentials
            log_print("Authentification réussie.")
            return Credentials(
                token=token_response['access_token'],
                refresh_token=token_response.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES
            )
        except urllib.error.HTTPError as e:
            error = json.loads(e.read())
            if error.get('error') == 'authorization_pending':
                continue
            elif error.get('error') == 'slow_down':
                interval += 5
                continue
            else:
                log_print(f"Erreur d'authentification : {error}")
                sys.exit(1)

def get_new_credentials():
    """
    Get new OAuth credentials using the appropriate flow:
    - Browser flow if a browser is available (Desktop/PC)
    - Device flow if running headless (Docker/server)

    Credentials source (in priority order):
    1. YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET environment variables
    2. client_secrets.json file in the current directory
    """
    client_id, client_secret = _get_client_credentials()

    if _has_browser():
        log_print("Browser detected — using browser-based authentication flow.")
        return _get_credentials_browser_flow(client_id, client_secret)
    else:
        log_print("No browser detected — using Device Flow (headless mode).")
        return _get_credentials_device_flow(client_id, client_secret)

def save_credentials(credentials, token_file):
    """Save credentials to token file."""
    with open(token_file, 'wb') as token:
        pickle.dump(credentials, token)
        log_print("Saved new credentials.")

def get_authenticated_service():
    """Get authenticated YouTube API service."""
    token_file = 'token.pickle'
    credentials = load_credentials(token_file)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            log_print("Refreshing credentials...")
            try:
                credentials.refresh(Request())
            except RefreshError as e:
                log_print(f"Token refresh failed: {e}")
                log_print("The stored token has expired or been revoked.")
                log_print("Deleting the token file and requesting new authentication...")
                credentials = handle_refresh_error(token_file)

        if not credentials or not credentials.valid:
            log_print("Getting new credentials...")
            credentials = get_new_credentials()
            save_credentials(credentials, token_file)

    return build('youtube', 'v3', credentials=credentials)

def load_subscriptions_cache():
    """
    Load subscriptions from local cache if it exists and is still fresh.

    Returns:
        List of channel IDs if cache is valid, None otherwise.
    """
    import json
    if not os.path.exists(SUBSCRIPTIONS_CACHE_FILE):
        return None

    try:
        with open(SUBSCRIPTIONS_CACHE_FILE, 'r') as f:
            cache = json.load(f)

        cached_at = datetime.datetime.fromisoformat(cache['cached_at'])
        age_hours = (datetime.datetime.now(datetime.UTC) - cached_at).total_seconds() / 3600

        if age_hours < SUBSCRIPTIONS_CACHE_TTL_HOURS:
            channel_ids = cache['channel_ids']
            log_print(f"Using cached subscriptions ({len(channel_ids)} channels, "
                      f"cached {age_hours:.1f}h ago, refresh in {SUBSCRIPTIONS_CACHE_TTL_HOURS - age_hours:.1f}h).")
            return channel_ids
        else:
            log_print(f"Subscriptions cache expired ({age_hours:.1f}h old). Refreshing...")
            return None

    except Exception as e:
        log_print(f"Could not read subscriptions cache: {e}. Fetching from API...")
        return None

def save_subscriptions_cache(channel_ids):
    """Save channel IDs to local cache with a timestamp."""
    import json
    cache = {
        'cached_at': datetime.datetime.now(datetime.UTC).isoformat(),
        'channel_ids': channel_ids,
    }
    with open(SUBSCRIPTIONS_CACHE_FILE, 'w') as f:
        json.dump(cache, f)
    log_print(f"Subscriptions cache saved ({len(channel_ids)} channels).")

def fetch_subscriptions_from_api(youtube):
    """Fetch all subscribed channel IDs from the YouTube API."""
    log_print("Fetching subscriptions from YouTube API...")

    channel_ids = []
    request = youtube.subscriptions().list(
        part="snippet",
        mine=True,
        maxResults=50
    )

    while request:
        response = request.execute()
        quota.track('subscriptions.list')
        for item in response['items']:
            channel_ids.append(item['snippet']['resourceId']['channelId'])
        request = youtube.subscriptions().list_next(request, response)

    log_print(f"Found {len(channel_ids)} subscriptions.")
    return channel_ids

def get_subscriptions(youtube, force_refresh=False):
    """
    Get list of subscribed channel IDs, using a local cache when possible.

    The cache is stored in SUBSCRIPTIONS_CACHE_FILE and refreshed automatically
    after SUBSCRIPTIONS_CACHE_TTL_HOURS hours, or immediately if force_refresh=True.

    Args:
        youtube: Authenticated YouTube API client
        force_refresh: If True, bypass cache and fetch from API

    Returns:
        List of channel IDs
    """
    if not force_refresh:
        cached = load_subscriptions_cache()
        if cached is not None:
            return cached

    channel_ids = fetch_subscriptions_from_api(youtube)
    save_subscriptions_cache(channel_ids)
    return channel_ids

def get_last_check_time():
    """Get the timestamp of the last time we checked for new videos."""
    if os.path.exists(LAST_CHECK_FILE):
        with open(LAST_CHECK_FILE, 'r') as f:
            timestamp = f.read().strip()
            if timestamp:
                return timestamp

    # Default to 1 day ago if no last check time is saved
    one_day_ago = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return one_day_ago

def save_check_time():
    """Save the current time as the last check time."""
    current_time = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(LAST_CHECK_FILE, 'w') as f:
        f.write(current_time)
    return current_time

# ---------------------------------------------------------------------------
# Pending videos persistence
# ---------------------------------------------------------------------------

def load_pending_videos():
    """
    Load the list of videos discovered but not yet added to the playlist.

    Returns:
        List of video dicts with 'id', 'title', 'channel', or [] if none.
    """
    import json
    if not os.path.exists(PENDING_VIDEOS_FILE):
        return []
    try:
        with open(PENDING_VIDEOS_FILE, 'r') as f:
            data = json.load(f)
        log_print(f"Resuming: {len(data)} pending videos found from previous interrupted run.")
        return data
    except Exception as e:
        log_print(f"Could not read pending videos file: {e}. Starting fresh.")
        return []

def save_pending_videos(videos):
    """Persist the pending video list to disk (atomic write)."""
    import json
    tmp = PENDING_VIDEOS_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(videos, f)
    os.replace(tmp, PENDING_VIDEOS_FILE)

def clear_pending_videos():
    """Remove the pending videos file once all videos have been added."""
    if os.path.exists(PENDING_VIDEOS_FILE):
        os.remove(PENDING_VIDEOS_FILE)

# ---------------------------------------------------------------------------
# Scan progress persistence
# ---------------------------------------------------------------------------

def load_scan_progress():
    """
    Load scan progress from a previous interrupted run.

    Returns:
        Dict with 'last_channel_index' (int) and 'shorts_cache' (list),
        or None if no progress file exists.
    """
    import json
    if not os.path.exists(SCAN_PROGRESS_FILE):
        return None
    try:
        with open(SCAN_PROGRESS_FILE, 'r') as f:
            data = json.load(f)
        log_print(f"Resuming scan from channel index {data['last_channel_index']} "
                  f"({data['last_channel_index']} channels already processed).")
        return data
    except Exception as e:
        log_print(f"Could not read scan progress file: {e}. Starting scan from scratch.")
        return None

def save_scan_progress(last_channel_index, shorts_cache):
    """Persist current scan position and shorts cache to disk (atomic write)."""
    import json
    tmp = SCAN_PROGRESS_FILE + '.tmp'
    data = {
        'last_channel_index': last_channel_index,
        'shorts_cache': list(shorts_cache),
    }
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, SCAN_PROGRESS_FILE)

def clear_scan_progress():
    """Remove the scan progress file once a full scan completes successfully."""
    if os.path.exists(SCAN_PROGRESS_FILE):
        os.remove(SCAN_PROGRESS_FILE)

def get_channel_shorts_playlist_id(channel_id):
    """
    Convert a channel ID to its corresponding Shorts playlist ID.

    Args:
        channel_id: YouTube channel ID (starts with "UC")

    Returns:
        Shorts playlist ID (starts with "UUSH") or None if invalid channel ID
    """
    if not channel_id or not channel_id.startswith("UC"):
        return None

    # Replace "UC" with "UUSH" to get the Shorts playlist
    return "UUSH" + channel_id[2:]

def process_playlist_item(item, cutoff_time):
    """Process a single playlist item and return video ID if it's recent enough."""
    from datetime import datetime
    published_at_str = item['snippet']['publishedAt']
    published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))

    if published_at > cutoff_time:
        return item['contentDetails']['videoId']
    return None

def fetch_playlist_page(youtube, request, cutoff_time, shorts_video_ids, max_results):
    """Fetch and process a single page of playlist items."""
    try:
        if not request:
            return None
        response = request.execute()
        quota.track('playlistItems.list')
        should_continue = False

        for item in response.get('items', []):
            video_id = process_playlist_item(item, cutoff_time)
            if video_id:
                shorts_video_ids.add(video_id)
                should_continue = True
            else:
                return None  # Stop if we hit an old video

        if should_continue and len(shorts_video_ids) < max_results:
            return youtube.playlistItems().list_next(request, response)
        return None

    except Exception as e:
        error_msg = str(e).lower()
        if "quota" in error_msg:
            raise QuotaExceededException()
        if "not found" in error_msg or "forbidden" in error_msg:
            return None
        log_print(f"Error fetching playlist page: {str(e)}")
        return None

def get_channel_shorts_video_ids(youtube, channel_id, published_after, max_results=50):
    """
    Get video IDs from a channel's Shorts playlist published after a certain time.

    Args:
        youtube: YouTube API client
        channel_id: Channel ID to check
        published_after: ISO 8601 timestamp to filter videos after
        max_results: Maximum number of Shorts to retrieve

    Returns:
        Set of video IDs that are Shorts published after the given time
    """
    shorts_playlist_id = get_channel_shorts_playlist_id(channel_id)
    if not shorts_playlist_id:
        return set()

    try:
        from datetime import datetime
        shorts_video_ids = set()
        cutoff_time = datetime.fromisoformat(published_after.replace('Z', '+00:00'))

        request = youtube.playlistItems().list(
            part="contentDetails,snippet",
            playlistId=shorts_playlist_id,
            maxResults=min(max_results, 50)
        )

        while request and len(shorts_video_ids) < max_results:
            request = fetch_playlist_page(youtube, request, cutoff_time, shorts_video_ids, max_results)

        return shorts_video_ids

    except QuotaExceededException:
        raise
    except Exception:
        return set()

def build_shorts_cache_for_channels(youtube, channel_ids, published_after, max_shorts_per_channel=20):
    """
    Build a cache of Shorts video IDs published after a certain time for the given channels.

    Args:
        youtube: YouTube API client
        channel_ids: List of channel IDs to check
        published_after: ISO 8601 timestamp to filter Shorts after
        max_shorts_per_channel: Max recent Shorts to cache per channel

    Returns:
        Set of recent Shorts video IDs across all channels
    """
    log_print(f"Building cache of recent YouTube Shorts (since {published_after})...")
    all_shorts = set()
    channels_with_shorts = 0

    for i, channel_id in enumerate(channel_ids):
        if i % 10 == 0:  # Progress update every 10 channels
            log_print(f"Processing channel {i+1}/{len(channel_ids)} for recent Shorts...")

        try:
            channel_shorts = get_channel_shorts_video_ids(youtube, channel_id, published_after, max_shorts_per_channel)
            if channel_shorts:
                all_shorts.update(channel_shorts)
                channels_with_shorts += 1

        except QuotaExceededException:
            log_print("Quota exceeded while building Shorts cache. Stopping.")
            raise
        except Exception:
            # Continue processing other channels if one fails
            continue

    log_print(f"Recent Shorts cache built: {len(all_shorts)} Shorts from {channels_with_shorts} channels")
    return all_shorts

def is_youtube_short_efficient(video_id, shorts_cache):
    """
    Efficiently check if a video is a YouTube Short using pre-built cache.

    Args:
        video_id: ID of the video to check
        shorts_cache: Set of known Shorts video IDs

    Returns:
        Boolean indicating whether the video is a YouTube Short
    """
    return video_id in shorts_cache

def is_teaser_or_trailer(video_title):
    """
    Check if a video title contains 'teaser' or 'trailer' keywords.

    Args:
        video_title: The title of the video to check

    Returns:
        Boolean indicating whether the video is a teaser or trailer
    """
    title_lower = video_title.lower()
    return 'teaser' in title_lower or 'trailer' in title_lower

def filter_videos(video_list, shorts_cache, context=""):
    """
    Filter videos based on content type preferences.

    Filtering is controlled by environment variables:
      INCLUDE_SHORTS=true/false   (default: false — Shorts are excluded)
      INCLUDE_TEASERS=true/false  (default: false — teasers/trailers are excluded)

    Args:
        video_list: List of video dicts with 'id', 'title', 'channel'
        shorts_cache: Set of known Shorts video IDs
        context: Context string for logging

    Returns:
        Filtered list of videos according to current settings.
    """
    filtered_videos = []
    shorts_count = 0
    teaser_trailer_count = 0

    for video in video_list:
        video_id = video['id']
        video_title = video['title']

        if is_youtube_short_efficient(video_id, shorts_cache):
            if INCLUDE_SHORTS:
                filtered_videos.append(video)
                log_print(f"Found new Short ({context}): {video_title} ({video['channel']})")
            else:
                log_print(f"Skipping Short ({context}): {video_title} ({video['channel']})")
                shorts_count += 1

        elif is_teaser_or_trailer(video_title):
            if INCLUDE_TEASERS:
                filtered_videos.append(video)
                log_print(f"Found new teaser/trailer ({context}): {video_title} ({video['channel']})")
            else:
                log_print(f"Skipping teaser/trailer ({context}): {video_title} ({video['channel']})")
                teaser_trailer_count += 1

        else:
            filtered_videos.append(video)
            log_print(f"Found new video ({context}): {video_title} ({video['channel']})")

    if shorts_count > 0:
        log_print(f"Filtered out {shorts_count} Shorts from {context} results")
    if teaser_trailer_count > 0:
        log_print(f"Filtered out {teaser_trailer_count} teasers/trailers from {context} results")

    return filtered_videos

def get_videos_from_activities(youtube, channel_id, last_check_time, shorts_cache):
    """Try to get videos using the activities endpoint."""
    try:
        # Activities endpoint only costs 1 unit per request
        request = youtube.activities().list(
            part="snippet,contentDetails",
            channelId=channel_id,
            publishedAfter=last_check_time,
            maxResults=10
        )

        response = request.execute()
        quota.track('activities.list')
        candidate_videos = []

        for item in response.get('items', []):
            if item['snippet']['type'] == 'upload':
                if 'upload' in item.get('contentDetails', {}):
                    video_id = item['contentDetails']['upload']['videoId']
                    title = item['snippet']['title']
                    channel_title = item['snippet']['channelTitle']

                    candidate_videos.append({
                        'id': video_id,
                        'title': title,
                        'channel': channel_title
                    })

        # Filter videos according to content preferences
        return filter_videos(candidate_videos, shorts_cache, "activities")

    except Exception as e:
        error_msg = str(e)

        # If quota error, propagate immediately to stop all processing
        if "quota" in error_msg.lower():
            log_print("Quota exceeded in activities endpoint.")
            raise QuotaExceededException()

        log_print(f"Error fetching activities for channel {channel_id}: {error_msg}")
        # For other errors, return None to trigger fallback to search
        return None

def get_videos_from_search(youtube, channel_id, last_check_time, shorts_cache):
    """Fall back to search API to get videos."""
    try:
        log_print(f"Trying fallback search API for channel {channel_id}...")
        # Format date correctly for search API
        formatted_date = last_check_time
        if '+' in formatted_date:  # Remove any timezone offset if present
            formatted_date = formatted_date.split('+')[0] + 'Z'

        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            publishedAfter=formatted_date,
            maxResults=5,
            type="video",
            order="date"
        )

        response = request.execute()
        quota.track('search.list')
        candidate_videos = []

        for item in response.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            channel_title = item['snippet']['channelTitle']

            candidate_videos.append({
                'id': video_id,
                'title': title,
                'channel': channel_title
            })

        # Filter videos according to content preferences
        return filter_videos(candidate_videos, shorts_cache, "search")

    except Exception as search_error:
        error_msg = str(search_error)

        # If quota error, propagate immediately
        if "quota" in error_msg.lower():
            log_print("Quota exceeded in search fallback.")
            raise QuotaExceededException()

        log_print(f"Search fallback also failed: {error_msg}")
        return []

def get_new_videos_with_shorts_filtering(youtube, channel_ids, last_check_time, resume_progress=None):
    """
    Get new videos from subscribed channels with efficient Shorts filtering.

    Everything is kept in memory — no disk writes during the scan.
    On quota exceeded, the caller is responsible for persisting state.

    Args:
        youtube: Authenticated YouTube API client
        channel_ids: List of all subscribed channel IDs
        last_check_time: ISO 8601 timestamp to filter videos after
        resume_progress: Dict from load_scan_progress() to resume an interrupted scan,
                         or None to start fresh.

    Returns:
        Tuple (new_videos, scan_state) where scan_state is a dict with
        'last_channel_index' and 'shorts_cache' — used by the caller to
        persist on quota exceeded.

    Raises QuotaExceededException if the API quota is hit at any point.
    """
    log_print(f"Checking for new videos since {last_check_time}...")

    # --- Resume or start fresh ---
    if resume_progress:
        start_index = resume_progress['last_channel_index']
        shorts_cache = set(resume_progress['shorts_cache'])
        log_print(f"Resuming scan: {start_index}/{len(channel_ids)} channels already done, "
                  f"{len(shorts_cache)} Shorts in cache.")
    else:
        start_index = 0
        log_print("Building cache of recent YouTube Shorts...")
        shorts_cache = build_shorts_cache_for_channels(youtube, channel_ids, last_check_time)

    # Log active filter settings
    filters_off = []
    if INCLUDE_SHORTS:
        filters_off.append("Shorts included")
    else:
        filters_off.append("Shorts excluded")
    if INCLUDE_TEASERS:
        filters_off.append("teasers/trailers included")
    else:
        filters_off.append("teasers/trailers excluded")
    log_print(f"Content filters: {', '.join(filters_off)}.")
    log_print("(Set INCLUDE_SHORTS=true or INCLUDE_TEASERS=true to change.)")
    new_videos = []
    batch_size = 5
    remaining = channel_ids[start_index:]
    total = len(channel_ids)
    absolute_index = start_index

    for batch_offset in range(0, len(remaining), batch_size):
        batch = remaining[batch_offset:batch_offset + batch_size]
        log_print(f"Processing channels {absolute_index + 1}–"
                  f"{min(absolute_index + batch_size, total)}/{total}")

        for channel_id in batch:
            # QuotaExceededException propagates up — caller will persist state
            channel_videos = get_channel_videos(youtube, channel_id, last_check_time, shorts_cache)
            new_videos.extend(channel_videos)
            absolute_index += 1

    log_print(f"Found {len(new_videos)} new videos after filtering.")

    scan_state = {
        'last_channel_index': absolute_index,
        'shorts_cache': shorts_cache,
    }
    return new_videos, scan_state

def process_channel_batch(youtube, channel_ids, last_check_time, shorts_cache):
    """Process a batch of channels to find new videos."""
    new_videos = []

    for channel_id in channel_ids:
        channel_videos = get_channel_videos(youtube, channel_id, last_check_time, shorts_cache)
        new_videos.extend(channel_videos)

    return new_videos

def get_channel_videos(youtube, channel_id, last_check_time, shorts_cache):
    """Get new videos from a specific channel."""
    # Try using activities endpoint first
    videos_from_activities = get_videos_from_activities(youtube, channel_id, last_check_time, shorts_cache)
    if videos_from_activities is not None:
        return videos_from_activities

    # Fall back to search API if activities endpoint fails
    return get_videos_from_search(youtube, channel_id, last_check_time, shorts_cache)

def _fetch_or_create_playlist(youtube):
    """
    Scan the user's playlists for 'Automated Watch Later', creating it if absent.
    Always makes API calls — use get_playlist_id() for the cached version.
    """
    custom_playlist_name = "Automated Watch Later"

    request = youtube.playlists().list(
        part="snippet,id",
        mine=True,
        maxResults=50
    )
    while request:
        response = request.execute()
        quota.track('playlists.list')
        for playlist in response['items']:
            if playlist['snippet']['title'] == custom_playlist_name:
                log_print(f"Found existing '{custom_playlist_name}' playlist with ID: {playlist['id']}")
                return playlist['id']
        request = youtube.playlists().list_next(request, response)

    log_print(f"Creating new '{custom_playlist_name}' playlist...")
    result = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": custom_playlist_name,
                "description": "Automatically updated playlist with new videos from subscriptions."
            },
            "status": {"privacyStatus": "private"}
        }
    ).execute()
    quota.track('playlists.insert')
    log_print(f"Created new playlist with ID: {result['id']}")
    return result['id']

def get_playlist_id(youtube):
    """
    Return the 'Automated Watch Later' playlist ID, using a local cache.

    The ID is stored in PLAYLIST_ID_CACHE_FILE after the first lookup and
    reused on every subsequent run — no API call needed.
    If the cached ID is stale (playlist deleted/renamed), the API returns 404
    and this function falls back to a fresh scan automatically.
    """
    # Try cache first
    if os.path.exists(PLAYLIST_ID_CACHE_FILE):
        with open(PLAYLIST_ID_CACHE_FILE, 'r') as f:
            cached_id = f.read().strip()
        if cached_id:
            # Validate the cached ID with a cheap API call
            try:
                resp = youtube.playlists().list(
                    part="id",
                    id=cached_id
                ).execute()
                if resp.get('items'):
                    log_print(f"Using cached playlist ID: {cached_id}")
                    return cached_id
                else:
                    log_print("Cached playlist ID no longer valid. Scanning for playlist...")
            except Exception:
                log_print("Could not validate cached playlist ID. Scanning for playlist...")

    # Cache miss or invalid — fetch from API and cache the result
    playlist_id = _fetch_or_create_playlist(youtube)
    with open(PLAYLIST_ID_CACHE_FILE, 'w') as f:
        f.write(playlist_id)
    log_print(f"Playlist ID cached to {PLAYLIST_ID_CACHE_FILE}.")
    return playlist_id

def fetch_playlist_video_ids(youtube, playlist_id):
    """
    Fetch all video IDs currently in the playlist in a single paginated call.

    Instead of checking each video individually before inserting (1 API call per
    video), this fetches the entire playlist once and returns a set of IDs for
    fast local lookups. This reduces N API calls to ceil(playlist_size / 50).

    Args:
        youtube: Authenticated YouTube API client
        playlist_id: Target playlist ID

    Returns:
        Set of video ID strings currently in the playlist.

    Raises QuotaExceededException if the API quota is hit.
    """
    video_ids = set()
    request = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=playlist_id,
        maxResults=50
    )
    while request:
        try:
            response = request.execute()
            quota.track('playlistItems.list')
            for item in response.get('items', []):
                video_ids.add(item['contentDetails']['videoId'])
            request = youtube.playlistItems().list_next(request, response)
        except Exception as e:
            error_msg = str(e)
            if "quotaExceeded" in error_msg:
                log_print("Quota exceeded while fetching playlist contents.")
                raise QuotaExceededException()
            log_print(f"Error fetching playlist contents: {error_msg}")
            break

    log_print(f"Loaded {len(video_ids)} existing video IDs from playlist.")
    return video_ids

def add_to_watch_later(youtube, videos, playlist_id):
    """
    Add videos to the specified playlist.

    Fetches all existing video IDs from the playlist once at the start, then
    performs duplicate checks locally in memory. This replaces N individual
    playlistItems.list calls (one per video) with ceil(playlist_size / 50) calls.

    Everything is kept in memory — no disk writes during the loop.
    On quota exceeded, raises QuotaExceededException; the caller is
    responsible for persisting the remaining (un-added) videos.

    Args:
        youtube: Authenticated YouTube API client
        videos: List of video dicts with 'id', 'title', 'channel'
        playlist_id: Target playlist ID

    Returns:
        Tuple (added_count, remaining_videos) where remaining_videos is the
        subset not yet added (empty list on full success).

    Raises QuotaExceededException if the API quota is hit.
    """
    log_print(f"Adding {len(videos)} videos to playlist...")

    # Fetch all existing video IDs once — avoids one API call per video
    existing_ids = fetch_playlist_video_ids(youtube, playlist_id)

    added_count = 0
    already_in_playlist_count = 0
    remaining = list(videos)

    for video in videos:
        video_id = video['id']
        try:
            # Local duplicate check — no API call needed
            if video_id in existing_ids:
                log_print(f"Video {video_id} is already in the playlist. Skipping.")
                already_in_playlist_count += 1
                remaining.remove(video)
                continue

            # Add the video to the playlist
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id
                        }
                    }
                }
            ).execute()
            quota.track('playlistItems.insert')

            added_count += 1
            existing_ids.add(video_id)  # keep in-memory set consistent
            log_print(f"Added: {video_id}")
            remaining.remove(video)

            # Small delay to avoid rate limiting
            time.sleep(0.5)

        except Exception as e:
            error_msg = str(e)
            if "quotaExceeded" in error_msg:
                log_print("Quota exceeded while adding videos. Remaining videos will be saved by caller.")
                raise QuotaExceededException()
            elif "videoNotFound" in error_msg or "notFound" in error_msg:
                log_print(f"Video {video_id} may have been removed or is not accessible.")
                remaining.remove(video)
            elif "playlistForbidden" in error_msg or "forbidden" in error_msg.lower():
                log_print("Access to playlist is restricted. Make sure you've granted the proper permissions.")
            else:
                log_print(f"Failed to add video {video_id}: {error_msg}")

    log_print(f"Summary: Added {added_count} videos, {already_in_playlist_count} already in playlist.")
    return added_count, remaining

def check_quota_usage(youtube):
    """Check the current quota usage for the YouTube API."""
    try:
        # Make a minimal API call to check if quota is exceeded
        youtube.channels().list(
            part="id",
            mine=True
        ).execute()
        quota.track('channels.list')
        log_print("YouTube API quota is available.")
        return True
    except Exception as e:
        if "quota" in str(e).lower():
            log_print("YouTube API quota has been exceeded for today.")
            log_print("The quota resets at midnight Pacific Time.")
            return False
        else:
            log_print(f"Error checking quota: {str(e)}")
            return True  # Assume quota is available if error is not quota-related

def main():
    # Setup logging
    log_path = setup_logging()
    log_print(f"Log file created: {log_path}")

    try:
        # Get authenticated YouTube API service
        youtube = get_authenticated_service()

        # Check quota status before doing anything
        quota_available = check_quota_usage(youtube)
        if not quota_available:
            log_print("Quota exceeded. Cannot proceed. Quota resets at midnight Pacific Time.")
            return

        # Get or create the watch later playlist (cached after first run)
        playlist_id = get_playlist_id(youtube)
        log_print(f"Using playlist ID: {playlist_id}")

        # In-memory state — only written to disk on quota exceeded
        pending_videos = []   # videos found but not yet added
        scan_state = None     # current scan position + shorts cache

        try:
            # --- Resume from previous quota-exceeded run if applicable ---
            saved_pending = load_pending_videos()
            saved_progress = load_scan_progress()

            if saved_pending:
                log_print(f"\nResuming: adding {len(saved_pending)} pending videos from previous run...")
                _, remaining = add_to_watch_later(youtube, saved_pending, playlist_id)
                if not remaining:
                    clear_pending_videos()
                    log_print("All pending videos processed. Proceeding with new scan.")
                # If remaining is non-empty, QuotaExceededException was raised above

            # --- Scan for new videos (in memory, resume if progress file exists) ---
            channel_ids = get_subscriptions(youtube)
            last_check_time = get_last_check_time()

            new_videos, scan_state = get_new_videos_with_shorts_filtering(
                youtube, channel_ids, last_check_time,
                resume_progress=saved_progress
            )

            if new_videos:
                log_print("\nNew videos found:")
                for i, video in enumerate(new_videos):
                    log_print(f"{i+1}. {video['title']} - {video['channel']}")

                pending_videos = new_videos  # track in memory before adding
                _, remaining = add_to_watch_later(youtube, new_videos, playlist_id)
                pending_videos = remaining   # update to only what's left

            else:
                log_print("No new videos found since last check.")

            # Full run completed — clear state files and update last check time
            clear_pending_videos()
            clear_scan_progress()
            current_time = save_check_time()
            log_print(f"Updated last check time to: {current_time}")

        except QuotaExceededException:
            # Only write to disk here — quota exceeded is the one predictable interruption
            log_print("\nYouTube API quota exceeded during execution.")
            if pending_videos:
                save_pending_videos(pending_videos)
                log_print(f"Saved {len(pending_videos)} pending videos to {PENDING_VIDEOS_FILE}.")
            if scan_state:
                save_scan_progress(scan_state['last_channel_index'], scan_state['shorts_cache'])
                log_print(f"Saved scan progress at channel {scan_state['last_channel_index']}.")
            log_print("The next run will resume exactly where this one stopped.")
            log_print("last_check_time has NOT been updated — no videos will be missed.")
            log_print("Quota resets at midnight Pacific Time.")

        except Exception as e:
            log_print(f"Unexpected error: {str(e)}")

    finally:
        quota.report()
        cleanup_logging()

if __name__ == '__main__':
    main()