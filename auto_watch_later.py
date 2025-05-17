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

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl'
]

# File to store the last check time
LAST_CHECK_FILE = 'last_check_time.txt'

def get_authenticated_service():
    """Get authenticated YouTube API service."""
    credentials = None

    # Token pickle stores the user's credentials from previously successful logins
    token_file = 'token.pickle'
    if os.path.exists(token_file):
        print("Loading saved credentials...")
        with open(token_file, 'rb') as token:
            credentials = pickle.load(token)

    # If there are no valid credentials available, let the user log in
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("Refreshing credentials...")
            credentials.refresh(Request())
        else:
            print("Getting new credentials...")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secrets.json', SCOPES)
                credentials = flow.run_local_server(port=0)
            except FileNotFoundError:
                print("ERROR: You need to download the 'client_secrets.json' file from Google Cloud Console.")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project and enable YouTube Data API v3")
                print("3. Create OAuth 2.0 credentials (Desktop application)")
                print("4. Download the JSON file and rename it to 'client_secrets.json'")
                print("5. Place it in the same directory as this script")
                sys.exit(1)

        # Save the credentials for the next run
        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)

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
    one_day_ago = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat('T') + 'Z'
    return one_day_ago

def save_check_time():
    """Save the current time as the last check time."""
    current_time = datetime.datetime.now(datetime.UTC).isoformat('T') + 'Z'
    with open(LAST_CHECK_FILE, 'w') as f:
        f.write(current_time)
    return current_time

def _get_channel_new_videos(youtube, channel_id, last_check_time):
    """Helper to get new uploaded videos for a single channel."""
    videos = []
    try:
        request = youtube.activities().list(
            part="snippet,contentDetails",
            channelId=channel_id,
            publishedAfter=last_check_time,
            maxResults=10
        )
        response = request.execute()
        for item in response.get('items', []):
            if item['snippet']['type'] == 'upload' and 'upload' in item.get('contentDetails', {}):
                video_id = item['contentDetails']['upload']['videoId']
                title = item['snippet']['title']
                channel_title = item['snippet']['channelTitle']
                videos.append({
                    'id': video_id,
                    'title': title,
                    'channel': channel_title
                })
                print(f"Found new video: {title} ({channel_title})")
    except Exception as e:
        print(f"Error fetching activities for channel {channel_id}: {str(e)}")
        if "quota" in str(e).lower():
            print("Quota limit reached. Stopping further processing.")
            return videos
    return videos

def get_new_videos(youtube, channel_ids, last_check_time):
    """Get new videos from subscribed channels published after the last check time.

    This implementation is more quota-efficient by:
    1. Using activities.list instead of search.list when possible
    2. Batching the channel requests
    """
    print(f"Checking for new videos since {last_check_time}...")
    new_videos = []

    # Process channels in batches to avoid hitting quota limits too quickly
    batch_size = 5
    for i in range(0, len(channel_ids), batch_size):
        batch_channels = channel_ids[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1} of {len(channel_ids)//batch_size + 1} ({len(batch_channels)} channels)")

        for channel_id in batch_channels:
            try:
                channel_videos = _get_channel_new_videos(youtube, channel_id, last_check_time)
                new_videos.extend(channel_videos)
            except Exception as e:
                if "quota" in str(e).lower():
                    return new_videos

    print(f"Found {len(new_videos)} new videos.")
    return new_videos

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
        new_videos = get_new_videos(youtube, channel_ids, last_check_time)

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
