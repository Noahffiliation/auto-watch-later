import pytest
from unittest.mock import MagicMock, call, patch, mock_open
import sys
import os
import datetime
import pickle # Added missing import

# Add the parent directory to sys.path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auto_watch_later

@pytest.fixture
def mock_youtube_client():
    return MagicMock()

def test_setup_logging(mocker):
    mocker.patch('os.makedirs')
    mocker.patch('os.path.exists', return_value=False) # Ensure makedirs is called
    mock_open_func = mocker.mock_open()
    mocker.patch('builtins.open', mock_open_func)
    mocker.patch('datetime.datetime')

    auto_watch_later.setup_logging()

    os.makedirs.assert_called_with('logs')
    assert auto_watch_later.log_file is not None

def test_cleanup_logging(mocker):
    # Setup mock log file
    mock_file = MagicMock()
    auto_watch_later.log_file = mock_file

    auto_watch_later.cleanup_logging()

    mock_file.close.assert_called_once()

def test_log_print(capsys):
    # Mock log_file
    mock_file = MagicMock()
    auto_watch_later.log_file = mock_file

    message = "Test message"
    auto_watch_later.log_print(message)

    # Check stdout
    captured = capsys.readouterr()
    assert message in captured.out

    # Check file write
    mock_file.write.assert_called()

def test_get_channel_shorts_playlist_id():
    # Valid channel ID
    assert auto_watch_later.get_channel_shorts_playlist_id("UC12345") == "UUSH12345"
    # Invalid channel ID
    assert auto_watch_later.get_channel_shorts_playlist_id("XY12345") is None

def test_is_teaser_or_trailer():
    assert auto_watch_later.is_teaser_or_trailer("Official Trailer") is True
    assert auto_watch_later.is_teaser_or_trailer("Movie Teaser") is True
    assert auto_watch_later.is_teaser_or_trailer("Regular Video") is False
    assert auto_watch_later.is_teaser_or_trailer("TRAILER compilation") is True

def test_get_last_check_time(mocker):
    # Case 1: File exists and has valid content
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data="2023-01-01T12:00:00+00:00"))

    dt = auto_watch_later.get_last_check_time()
    assert isinstance(dt, str)
    assert dt == "2023-01-01T12:00:00+00:00"

    # Case 2: File exists but empty/invalid (should return now - 1 day roughly)
    mocker.patch('builtins.open', mock_open(read_data=""))
    dt_default = auto_watch_later.get_last_check_time()
    assert isinstance(dt_default, str)

    # Case 3: File does not exist
    mocker.patch('os.path.exists', return_value=False)
    dt_no_file = auto_watch_later.get_last_check_time()
    assert isinstance(dt_no_file, str)

def test_save_check_time(mocker):
    mock_open_func = mocker.mock_open()
    mocker.patch('builtins.open', mock_open_func)

    auto_watch_later.save_check_time()

    mock_open_func.assert_called_with(auto_watch_later.LAST_CHECK_FILE, 'w')
    # Check that something was written (timestamp)
    mock_open_func().write.assert_called()

def test_is_youtube_short_efficient():
    shorts_cache = {'vid1', 'vid2'}
    assert auto_watch_later.is_youtube_short_efficient('vid1', shorts_cache) is True
    assert auto_watch_later.is_youtube_short_efficient('vid3', shorts_cache) is False

def test_filter_out_shorts_and_teasers():
    video_list = [
        {'id': 'v1', 'title': 'Short Video', 'channel': 'c1'},
        {'id': 'v2', 'title': 'Long Video', 'channel': 'c1'},
        {'id': 'v3', 'title': 'Movie Trailer', 'channel': 'c1'}
    ]
    shorts_cache = {'v1'}

    filtered = auto_watch_later.filter_out_shorts_and_teasers(video_list, shorts_cache)

    assert len(filtered) == 1
    assert filtered[0]['id'] == 'v2'

def test_get_subscriptions(mock_youtube_client):
    # Mock list() to return a request object
    mock_list_request = MagicMock()
    mock_youtube_client.subscriptions().list.return_value = mock_list_request

    # Mock responses
    response1 = {
        'items': [{'snippet': {'resourceId': {'channelId': 'c1'}}}],
        'nextPageToken': 'token'
    }
    response2 = {
        'items': [{'snippet': {'resourceId': {'channelId': 'c2'}}}]
    }

    mock_list_request.execute.side_effect = [response1, response2]

    # Mock list_next to return the request object ONCE, then None to stop loop
    mock_youtube_client.subscriptions().list_next.side_effect = [mock_list_request, None]

    subs = auto_watch_later.get_subscriptions(mock_youtube_client)

    assert len(subs) == 2
    assert 'c1' in subs
    assert 'c2' in subs

def test_get_channel_shorts_video_ids(mock_youtube_client):
    # Mock list() return value
    mock_list_request = MagicMock()
    mock_youtube_client.playlistItems().list.return_value = mock_list_request

    # Mock response
    response = {
        'items': [
            {'snippet': {'resourceId': {'videoId': 'v1'}, 'publishedAt': '2025-01-01T12:00:00Z'}, 'contentDetails': {'videoId': 'v1'}},
            {'snippet': {'resourceId': {'videoId': 'v2'}, 'publishedAt': '2025-01-01T12:00:00Z'}, 'contentDetails': {'videoId': 'v2'}}
        ]
    }
    mock_list_request.execute.return_value = response

    # IMPORTANT: mock list_next to return None to prevent infinite loop
    mock_youtube_client.playlistItems().list_next.return_value = None

    shorts = auto_watch_later.get_channel_shorts_video_ids(mock_youtube_client, 'UC123', '2024-01-01T00:00:00Z')

    assert 'v1' in shorts
    assert 'v2' in shorts

def test_get_videos_from_activities(mock_youtube_client):
    # Mock list() return value
    mock_list_request = MagicMock()
    mock_youtube_client.activities().list.return_value = mock_list_request

    # Mock response
    response = {
        'items': [
            {'snippet': {'type': 'upload', 'title': 'Video 1', 'channelTitle': 'Channel 1'}, 'contentDetails': {'upload': {'videoId': 'v1'}}},
            {'snippet': {'type': 'like'}, 'contentDetails': {}} # Should be ignored
        ]
    }
    mock_list_request.execute.return_value = response

    videos = auto_watch_later.get_videos_from_activities(mock_youtube_client, 'UC123', '2024-01-01Z', set())

    assert len(videos) == 1
    assert videos[0]['id'] == 'v1'
    assert videos[0]['title'] == 'Video 1'

def test_get_videos_from_search(mock_youtube_client):
    # Mock list()
    mock_list_request = MagicMock()
    mock_youtube_client.search().list.return_value = mock_list_request

    # Mock response
    response = {
        'items': [
            {'id': {'videoId': 'v1'}, 'snippet': {'title': 'Video 1', 'channelTitle': 'Channel 1'}}
        ]
    }
    mock_list_request.execute.return_value = response

    videos = auto_watch_later.get_videos_from_search(mock_youtube_client, 'UC123', '2024-01-01Z', set())

    assert len(videos) == 1
    assert videos[0]['id'] == 'v1'
    assert videos[0]['title'] == 'Video 1'

def test_create_or_get_custom_watch_later_existing(mock_youtube_client):
    # Mock list()
    mock_list_request = MagicMock()
    mock_youtube_client.playlists().list.return_value = mock_list_request

    # Mock response: playlist exists
    mock_list_request.execute.return_value = {
        'items': [{'snippet': {'title': 'Automated Watch Later'}, 'id': 'PL123'}]
    }
    mock_youtube_client.playlists().list_next.return_value = None

    pid = auto_watch_later.create_or_get_custom_watch_later(mock_youtube_client)
    assert pid == 'PL123'

def test_create_or_get_custom_watch_later_new(mock_youtube_client):
    # Mock list()
    mock_list_request = MagicMock()
    mock_youtube_client.playlists().list.return_value = mock_list_request

    # Mock response: playlist does not exist
    mock_list_request.execute.return_value = {'items': []}
    mock_youtube_client.playlists().list_next.return_value = None

    # Mock insert
    mock_youtube_client.playlists().insert().execute.return_value = {'id': 'PL_NEW'}

    pid = auto_watch_later.create_or_get_custom_watch_later(mock_youtube_client)
    assert pid == 'PL_NEW'

def test_add_to_watch_later(mock_youtube_client, mocker):
    mocker.patch('time.sleep') # Speed up test

    mock_list_request = MagicMock()
    mock_youtube_client.playlistItems().list.return_value = mock_list_request

    # Scenario: first video not in playlist (empty items), second video IS in playlist
    mock_list_request.execute.side_effect = [
        {'items': []},         # For v1: Not found -> Add
        {'items': [{'id': 'exists'}]} # For v2: Found -> Skip
    ]

    added_count = auto_watch_later.add_to_watch_later(mock_youtube_client, ['v1', 'v2'], 'PL123')

    # v1 added, v2 skipped
    assert added_count == 1
    # Check insert called once for v1
    mock_youtube_client.playlistItems().insert.assert_called_once()

def test_check_quota_usage(mock_youtube_client):
    # Case 1: Success
    mock_youtube_client.channels().list().execute.return_value = {}
    assert auto_watch_later.check_quota_usage(mock_youtube_client) is True

    # Case 2: Quota exceeded
    mock_youtube_client.channels().list().execute.side_effect = Exception("quotaExceeded")
    assert auto_watch_later.check_quota_usage(mock_youtube_client) is False

def test_process_playlist_item(mocker):
    # Tests logic for date filtering
    import datetime
    # Use timezone-aware datetime for comparison
    cutoff = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)

    # Recent video
    item_recent = {
        'snippet': {'publishedAt': '2025-01-02T12:00:00Z'},
        'contentDetails': {'videoId': 'v1'}
    }
    assert auto_watch_later.process_playlist_item(item_recent, cutoff) == 'v1'

    # Old video
    item_old = {
        'snippet': {'publishedAt': '2024-12-31T12:00:00Z'},
        'contentDetails': {'videoId': 'v1'}
    }
    assert auto_watch_later.process_playlist_item(item_old, cutoff) is None

def test_build_shorts_cache_for_channels(mock_youtube_client, mocker):
    # Mock the helper directly to avoid complex mocking of get_channel_shorts_video_ids internals again
    mocker.patch('auto_watch_later.get_channel_shorts_video_ids', side_effect=[{'s1'}, {'s2'}])

    cache = auto_watch_later.build_shorts_cache_for_channels(mock_youtube_client, ['c1', 'c2'], '2025-01-01Z')

    assert 's1' in cache
    assert 's2' in cache

def test_get_new_videos_with_shorts_filtering(mock_youtube_client, mocker):
    mocker.patch('auto_watch_later.build_shorts_cache_for_channels', return_value=set())
    # Mock processing batch to return some videos
    mocker.patch('auto_watch_later.process_channel_batch', return_value=[{'id': 'v1', 'title': 'New Video', 'channel': 'C1'}])

    videos = auto_watch_later.get_new_videos_with_shorts_filtering(mock_youtube_client, ['c1'], '2025-01-01Z')

    assert len(videos) == 1
    assert videos[0]['id'] == 'v1'

def test_process_channel_batch(mock_youtube_client, mocker):
    mocker.patch('auto_watch_later.get_channel_videos', return_value=[{'id': 'v1'}])
    videos = auto_watch_later.process_channel_batch(mock_youtube_client, ['c1'], '2025-01-01Z', set())
    assert len(videos) == 1

def test_get_channel_videos(mock_youtube_client, mocker):
    # Case 1: Activities works
    mocker.patch('auto_watch_later.get_videos_from_activities', return_value=[{'id': 'v1'}])
    assert len(auto_watch_later.get_channel_videos(mock_youtube_client, 'c1', 'date', set())) == 1

    # Case 2: Activities fails (returns None), Search works
    mocker.patch('auto_watch_later.get_videos_from_activities', return_value=None)
    mocker.patch('auto_watch_later.get_videos_from_search', return_value=[{'id': 'v2'}])
    assert len(auto_watch_later.get_channel_videos(mock_youtube_client, 'c1', 'date', set())) == 1

# Credentials tests
def test_load_credentials(mocker):
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('pickle.load', return_value='creds')
    mocker.patch('builtins.open', mock_open())
    assert auto_watch_later.load_credentials('token') == 'creds'

    mocker.patch('os.path.exists', return_value=False)
    assert auto_watch_later.load_credentials('token') is None

def test_handle_refresh_error(mocker):
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.remove')
    auto_watch_later.handle_refresh_error('token')
    os.remove.assert_called_with('token')

def test_save_credentials(mocker):
    mocker.patch('builtins.open', mock_open())
    mocker.patch('pickle.dump')
    auto_watch_later.save_credentials('creds', 'token')
    pickle.dump.assert_called()

def test_get_new_credentials(mocker):
    # This is hard to test fully without mocking the flow object returned basically
    mock_flow = MagicMock()
    mocker.patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file', return_value=mock_flow)
    mock_flow.run_local_server.return_value = 'creds'

    assert auto_watch_later.get_new_credentials() == 'creds'

    # Test file not found
    mocker.patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file', side_effect=FileNotFoundError)
    mocker.patch('sys.exit')
    auto_watch_later.get_new_credentials()
    sys.exit.assert_called_with(1)

def test_get_authenticated_service(mocker):
    # Case 1: Valid credentials loaded (easiest)
    mock_creds = MagicMock()
    mock_creds.valid = True
    mocker.patch('auto_watch_later.load_credentials', return_value=mock_creds)
    mocker.patch('auto_watch_later.build')

    auto_watch_later.get_authenticated_service()
    auto_watch_later.build.assert_called()

def test_main(mocker):
    # Mock everything to avoid IO
    mocker.patch('auto_watch_later.setup_logging')
    mocker.patch('auto_watch_later.cleanup_logging')
    mocker.patch('auto_watch_later.get_authenticated_service')
    mocker.patch('auto_watch_later.check_quota_usage', return_value=True)
    mocker.patch('auto_watch_later.create_or_get_custom_watch_later', return_value='PL123')
    mocker.patch('auto_watch_later.get_subscriptions', return_value=['c1'])
    mocker.patch('auto_watch_later.get_last_check_time', return_value='time')
    mocker.patch('auto_watch_later.get_new_videos_with_shorts_filtering', return_value=[{'id': 'v1', 'title': 'T', 'channel': 'C'}])
    mocker.patch('auto_watch_later.add_to_watch_later')
    mocker.patch('auto_watch_later.save_check_time')

    auto_watch_later.main()

    # Verify core flow steps happened
    auto_watch_later.get_authenticated_service.assert_called()
    auto_watch_later.get_subscriptions.assert_called()
    auto_watch_later.add_to_watch_later.assert_called()
    auto_watch_later.save_check_time.assert_called()

    # Test quota exceeded
    mocker.patch('auto_watch_later.check_quota_usage', return_value=False)
    auto_watch_later.main()

def test_handle_quota_exceeded_fallback(mock_youtube_client, mocker):
    mocker.patch('builtins.input', side_effect=['v1', 'v2', '']) # Enter two IDs then finish
    mocker.patch('auto_watch_later.add_to_watch_later')

    auto_watch_later.handle_quota_exceeded_fallback(mock_youtube_client, 'PL123')

    auto_watch_later.add_to_watch_later.assert_called_with(mock_youtube_client, ['v1', 'v2'], 'PL123')

def test_get_authenticated_service_refresh(mocker):
    # Case: Credentials exist but expired, refresh successful
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = True

    # Simulate refresh making credentials valid
    def make_valid(*args, **kwargs):
        mock_creds.valid = True
    mock_creds.refresh.side_effect = make_valid

    mocker.patch('auto_watch_later.load_credentials', return_value=mock_creds)
    mocker.patch('auto_watch_later.build')
    mocker.patch('auto_watch_later.save_credentials')

    auto_watch_later.get_authenticated_service()

    mock_creds.refresh.assert_called()
    auto_watch_later.build.assert_called()
    # Verify we did NOT try to get new credentials or save them
    auto_watch_later.save_credentials.assert_not_called()

def test_get_authenticated_service_refresh_fail(mocker):
    # Case: Credentials expired, refresh failed -> get new creds
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = True

    # Refresh raises error
    from google.auth.exceptions import RefreshError
    mock_creds.refresh.side_effect = RefreshError("Fail")

    mocker.patch('auto_watch_later.load_credentials', return_value=mock_creds)
    mocker.patch('auto_watch_later.handle_refresh_error', return_value=None) # Clears creds
    mocker.patch('auto_watch_later.get_new_credentials', return_value='new_creds')
    mocker.patch('auto_watch_later.save_credentials')
    mocker.patch('auto_watch_later.build')

    auto_watch_later.get_authenticated_service()

    mock_creds.refresh.assert_called()
    auto_watch_later.handle_refresh_error.assert_called()
    auto_watch_later.get_new_credentials.assert_called()
