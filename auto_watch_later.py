#!/usr/bin/env python3
"""
YouTube Subscription Auto-Adder

This script automatically finds new videos from your YouTube subscriptions
and adds them to a custom "Automated Watch Later" playlist.

Requirements:
- Python 3.6+
- google-api-python-client
- google-auth-oauthlib
- google-auth-httplib2

Setup:
1. Create a project in Google Cloud Console (https://console.cloud.google.com/)
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop application)
4. Download the client_secrets.json file and place it in the same directory as this script
5. Install requirements: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
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
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl'
]

# File to store the last check time
LAST_CHECK_FILE = 'last_check_time.txt'

def load_credentials(token_file):
    """Load credentials from token file if it exists."""
    if os.path.exists(token_file):
        print("Loading saved credentials...")
        with open(token_file, 'rb') as token:
            return pickle.load(token)
    return None

def handle_refresh_error(token_file):
    """Handle token refresh error by removing the invalid token file."""
    if os.path.exists(token_file):
        os.remove(token_file)
        print("Deleted invalid token file.")
    return None

def get_new_credentials():
    """Get new credentials using client secrets file."""
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_secrets.json', SCOPES)
        return flow.run_local_server(port=0)
    except FileNotFoundError:
        print("ERROR: You need to download the 'client_secrets.json' file from Google Cloud Console.")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project and enable YouTube Data API v3")
        print("3. Create OAuth 2.0 credentials (Desktop application)")
        print("4. Download the JSON file and rename it to 'client_secrets.json'")
        print("5. Place it in the same directory as this script")
        sys.exit(1)

def save_credentials(credentials, token_file):
    """Save credentials to token file."""
    with open(token_file, 'wb') as token:
        pickle.dump(credentials, token)
        print("Saved new credentials.")

def get_authenticated_service():
    """Get authenticated YouTube API service."""
    token_file = 'token.pickle'
    credentials = load_credentials(token_file)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("Refreshing credentials...")
            try:
                credentials.refresh(Request())
            except RefreshError as e:
                print(f"Token refresh failed: {e}")
                print("The stored token has expired or been revoked.")
                print("Deleting the token file and requesting new authentication...")
                credentials = handle_refresh_error(token_file)

        if not credentials or not credentials.valid:
            print("Getting new credentials...")
            credentials = get_new_credentials()
            save_credentials(credentials, token_file)

    return build('youtube', 'v3', credentials=credentials)

def get_subscriptions(youtube):
    """Get list of channel IDs that the user is subscribed to."""
    print("Fetching your subscriptions...")

    channel_ids = []
    request = youtube.subscriptions().list(
        part="snippet",
        mine=True,
        maxResults=50
    )

    # Keep fetching until all subscriptions are retrieved
    while request:
        response = request.execute()

        for item in response['items']:
            channel_ids.append(item['snippet']['resourceId']['channelId'])

        # Get the next page of results
        request = youtube.subscriptions().list_next(request, response)

    print(f"Found {len(channel_ids)} subscriptions.")
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

def parse_iso8601_duration(duration_str):
    """
    Parse ISO 8601 duration format (PT1H2M3S) to total seconds.

    Args:
        duration_str: String in ISO 8601 duration format

    Returns:
        Total duration in seconds
    """
    import re

    time_pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = time_pattern.match(duration_str)

    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds

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
        if "not found" in error_msg or "forbidden" in error_msg:
            return None
        print(f"Error fetching playlist page: {str(e)}")
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
    print(f"Building cache of recent YouTube Shorts (since {published_after})...")
    all_shorts = set()
    channels_with_shorts = 0

    for i, channel_id in enumerate(channel_ids):
        if i % 10 == 0:  # Progress update every 10 channels
            print(f"Processing channel {i+1}/{len(channel_ids)} for recent Shorts...")

        try:
            channel_shorts = get_channel_shorts_video_ids(youtube, channel_id, published_after, max_shorts_per_channel)
            if channel_shorts:
                all_shorts.update(channel_shorts)
                channels_with_shorts += 1

        except Exception:
            # Continue processing other channels if one fails
            continue

    print(f"Recent Shorts cache built: {len(all_shorts)} Shorts from {channels_with_shorts} channels")
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

def filter_out_shorts_and_teasers(video_list, shorts_cache, context=""):
    """
    Filter YouTube Shorts, teasers, and trailers from a list of videos using the cache.

    Args:
        video_list: List of video dictionaries with 'id', 'title', 'channel'
        shorts_cache: Set of known Shorts video IDs
        context: Context string for logging

    Returns:
        List of videos with Shorts, teasers, and trailers removed
    """
    filtered_videos = []
    shorts_count = 0
    teaser_trailer_count = 0

    for video in video_list:
        video_id = video['id']
        video_title = video['title']

        if is_youtube_short_efficient(video_id, shorts_cache):
            print(f"Skipping Short ({context}): {video_title} ({video['channel']})")
            shorts_count += 1
        elif is_teaser_or_trailer(video_title):
            print(f"Skipping teaser/trailer ({context}): {video_title} ({video['channel']})")
            teaser_trailer_count += 1
        else:
            filtered_videos.append(video)
            print(f"Found new video ({context}): {video_title} ({video['channel']})")

    if shorts_count > 0:
        print(f"Filtered out {shorts_count} Shorts from {context} results")

    if teaser_trailer_count > 0:
        print(f"Filtered out {teaser_trailer_count} teasers/trailers from {context} results")

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
        candidate_videos = []

        for item in response.get('items', []):
            # Check if this activity is an upload
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

        # Filter out Shorts using the cache
        return filter_out_shorts_and_teasers(candidate_videos, shorts_cache, "activities")

    except Exception as e:
        error_msg = str(e)
        print(f"Error fetching activities for channel {channel_id}: {error_msg}")

        # If quota error, signal to stop processing
        if "quota" in error_msg.lower():
            print("Quota limit reached. Stopping further processing.")
            return []

        # For other errors, return None to trigger fallback to search
        return None

def get_videos_from_search(youtube, channel_id, last_check_time, shorts_cache):
    """Fall back to search API to get videos."""
    try:
        print(f"Trying fallback search API for channel {channel_id}...")
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

        # Filter out Shorts using the cache
        return filter_out_shorts_and_teasers(candidate_videos, shorts_cache, "search")

    except Exception as search_error:
        print(f"Search fallback also failed: {str(search_error)}")

        # If quota error, signal to stop processing
        if "quota" in str(search_error).lower():
            print("Quota limit reached in search fallback. Stopping further processing.")

        # Return empty list when all methods fail
        return []

def get_new_videos_with_shorts_filtering(youtube, channel_ids, last_check_time):
    """Get new videos from subscribed channels with efficient Shorts filtering."""
    print(f"Checking for new videos since {last_check_time}...")

    # First, build a cache of recent Shorts from subscribed channels
    shorts_cache = build_shorts_cache_for_channels(youtube, channel_ids, last_check_time)

    print("NOTE: YouTube Shorts, teasers, and trailers will be automatically filtered out.")
    new_videos = []

    # Process channels in batches to avoid hitting quota limits too quickly
    batch_size = 5
    total_batches = len(channel_ids) // batch_size + (1 if len(channel_ids) % batch_size > 0 else 0)

    for i in range(0, len(channel_ids), batch_size):
        batch_channels = channel_ids[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1} of {total_batches} ({len(batch_channels)} channels)")

        batch_videos = process_channel_batch(youtube, batch_channels, last_check_time, shorts_cache)
        new_videos.extend(batch_videos)

        # If we got an empty list but should have videos, we might have hit quota limits
        if not batch_videos and i < len(channel_ids) - batch_size:
            print("No videos found in this batch. Possible quota limitation. Continuing with next batch.")

    print(f"Found {len(new_videos)} new videos (excluding Shorts, teasers, and trailers).")
    return new_videos

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

def create_or_get_custom_watch_later(youtube):
    """Create or get a custom 'Automated Watch Later' playlist.

    Since the actual Watch Later playlist can't be modified through the API,
    we'll create our own custom playlist as a workaround.
    """
    # First, check if we already have an "Automated Watch Later" playlist
    custom_playlist_name = "Automated Watch Later"

    # Get all playlists owned by the user
    request = youtube.playlists().list(
        part="snippet,id",
        mine=True,
        maxResults=50
    )

    while request:
        response = request.execute()

        # Check if our custom playlist already exists
        for playlist in response['items']:
            if playlist['snippet']['title'] == custom_playlist_name:
                print(f"Found existing '{custom_playlist_name}' playlist with ID: {playlist['id']}")
                return playlist['id']

        # Get the next page of results
        request = youtube.playlists().list_next(request, response)

    # If we're here, the playlist doesn't exist yet - create it
    print(f"Creating new '{custom_playlist_name}' playlist...")

    result = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": custom_playlist_name,
                "description": "Automatically updated playlist with new videos from subscriptions."
            },
            "status": {
                "privacyStatus": "private"
            }
        }
    ).execute()

    print(f"Created new playlist with ID: {result['id']}")
    return result['id']

def add_to_watch_later(youtube, video_ids, playlist_id):
    """Add videos to the specified playlist."""
    print(f"Adding {len(video_ids)} videos to playlist...")

    added_count = 0
    already_in_playlist_count = 0

    for video_id in video_ids:
        try:
            # Check if video is already in the playlist to avoid duplicates
            request = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                videoId=video_id,
                maxResults=1
            )
            response = request.execute()

            if response.get('items'):
                print(f"Video {video_id} is already in the playlist. Skipping.")
                already_in_playlist_count += 1
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

            added_count += 1
            print(f"Added: {video_id}")

            # Add a small delay to avoid rate limiting
            time.sleep(0.5)

        except Exception as e:
            # Print a more detailed error message
            print(f"Failed to add video {video_id}: {str(e)}")
            if "quotaExceeded" in str(e):
                print("API quota exceeded. Try again tomorrow or request higher quota limits.")
                break
            elif "videoNotFound" in str(e) or "notFound" in str(e):
                print("Video may have been removed or is not accessible.")
            elif "playlistForbidden" in str(e) or "forbidden" in str(e).lower():
                print("Access to playlist is restricted. Make sure you've granted the proper permissions.")

    print(f"Summary: Added {added_count} videos, {already_in_playlist_count} were already in the playlist.")
    return added_count

def check_quota_usage(youtube):
    """Check the current quota usage for the YouTube API."""
    try:
        # Make a minimal API call to check if quota is exceeded
        youtube.channels().list(
            part="id",
            mine=True
        ).execute()
        print("YouTube API quota is available.")
        return True
    except Exception as e:
        if "quota" in str(e).lower():
            print("YouTube API quota has been exceeded for today.")
            print("The quota resets at midnight Pacific Time.")
            return False
        else:
            print(f"Error checking quota: {str(e)}")
            return True  # Assume quota is available if error is not quota-related

def main():
    # Get authenticated YouTube API service
    youtube = get_authenticated_service()

    # Check quota status
    quota_available = check_quota_usage(youtube)
    if not quota_available:
        print("Quota exceeded. Cannot proceed.")
        return

    # Create or get custom playlist for automated watch later
    playlist_id = create_or_get_custom_watch_later(youtube)
    print(f"Using custom playlist ID: {playlist_id}")

    try:
        # Get subscribed channels
        channel_ids = get_subscriptions(youtube)

        # Get the last check time
        last_check_time = get_last_check_time()

        # Get new videos
        new_videos = get_new_videos_with_shorts_filtering(youtube, channel_ids, last_check_time)

        if new_videos:
            # Print new videos found
            print("\nNew videos found:")
            for i, video in enumerate(new_videos):
                print(f"{i+1}. {video['title']} - {video['channel']}")

            # Add videos to custom playlist
            video_ids = [video['id'] for video in new_videos]
            add_to_watch_later(youtube, video_ids, playlist_id)
        else:
            print("No new videos found since last check.")

        # Save the current time as the last check time
        current_time = save_check_time()
        print(f"Updated last check time to: {current_time}")

    except Exception as e:
        if "quota" in str(e).lower():
            print("\nAPI Quota exceeded during execution.")
            print("Try running the script again tomorrow when quota resets.")
        else:
            print(f"Error: {str(e)}")

def handle_quota_exceeded_fallback(youtube, watch_later_id):
    """A fallback method when API quota is exceeded.

    This prompts the user to manually provide YouTube video IDs.
    """
    print("\n=== QUOTA EXCEEDED FALLBACK ===")
    print("The YouTube API quota has been exceeded.")
    print("As a fallback, you can manually enter YouTube video IDs to add to your Watch Later playlist.")
    print("To get a video ID, go to the YouTube video and look at the URL.")
    print("Example: In https://www.youtube.com/watch?v=dQw4w9WgXcQ, the ID is 'dQw4w9WgXcQ'")

    video_ids = []
    while True:
        video_id = input("\nEnter a YouTube video ID (or press Enter to finish): ").strip()
        if not video_id:
            break
        video_ids.append(video_id)

    if video_ids:
        add_to_watch_later(youtube, video_ids, watch_later_id)
    else:
        print("No videos were added.")

    print("\nTIP: To avoid quota issues in the future, try:")
    print("1. Creating a new project in Google Cloud Console")
    print("2. Requesting a quota increase for your project")
    print("3. Running this script less frequently (e.g., once per week instead of daily)")
    print("4. Using the scheduling option in the script to run during off-peak hours")

if __name__ == '__main__':
    main()
