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

def test_filter_videos():
    video_list = [
        {'id': 'v1', 'title': 'Short Video', 'channel': 'c1'},
        {'id': 'v2', 'title': 'Long Video', 'channel': 'c1'},
        {'id': 'v3', 'title': 'Movie Trailer', 'channel': 'c1'}
    ]
    shorts_cache = {'v1'}

    filtered = auto_watch_later.filter_videos(video_list, shorts_cache)

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

def test_fetch_or_create_playlist_existing(mock_youtube_client):
    # Mock list()
    mock_list_request = MagicMock()
    mock_youtube_client.playlists().list.return_value = mock_list_request

    # Mock response: playlist exists
    mock_list_request.execute.return_value = {
        'items': [{'snippet': {'title': 'Automated Watch Later'}, 'id': 'PL123'}]
    }
    mock_youtube_client.playlists().list_next.return_value = None

    pid = auto_watch_later._fetch_or_create_playlist(mock_youtube_client)
    assert pid == 'PL123'

def test_fetch_or_create_playlist_new(mock_youtube_client):
    # Mock list()
    mock_list_request = MagicMock()
    mock_youtube_client.playlists().list.return_value = mock_list_request

    # Mock response: playlist does not exist
    mock_list_request.execute.return_value = {'items': []}
    mock_youtube_client.playlists().list_next.return_value = None

    # Mock insert
    mock_youtube_client.playlists().insert().execute.return_value = {'id': 'PL_NEW'}

    pid = auto_watch_later._fetch_or_create_playlist(mock_youtube_client)
    assert pid == 'PL_NEW'

def test_get_playlist_id_cached_valid(mock_youtube_client, mocker):
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data="PL_CACHED"))
    
    mock_list_request = MagicMock()
    mock_youtube_client.playlists().list.return_value = mock_list_request
    mock_list_request.execute.return_value = {'items': [{'id': 'PL_CACHED'}]}
    
    pid = auto_watch_later.get_playlist_id(mock_youtube_client)
    assert pid == 'PL_CACHED'
    mock_youtube_client.playlists().list.assert_called_with(part="id", id="PL_CACHED")

def test_get_playlist_id_cached_invalid(mock_youtube_client, mocker):
    mocker.patch('os.path.exists', return_value=True)
    mock_open_func = mock_open(read_data="PL_CACHED")
    mocker.patch('builtins.open', mock_open_func)
    
    mock_list_request = MagicMock()
    mock_youtube_client.playlists().list.return_value = mock_list_request
    mock_list_request.execute.return_value = {'items': []} # invalid/deleted playlist
    
    mocker.patch('auto_watch_later._fetch_or_create_playlist', return_value="PL_NEW")
    
    pid = auto_watch_later.get_playlist_id(mock_youtube_client)
    assert pid == 'PL_NEW'
    auto_watch_later._fetch_or_create_playlist.assert_called_once()

def test_get_playlist_id_no_cache(mock_youtube_client, mocker):
    mocker.patch('os.path.exists', return_value=False)
    mock_open_func = mock_open()
    mocker.patch('builtins.open', mock_open_func)
    
    mocker.patch('auto_watch_later._fetch_or_create_playlist', return_value="PL_NEW")
    
    pid = auto_watch_later.get_playlist_id(mock_youtube_client)
    assert pid == 'PL_NEW'
    auto_watch_later._fetch_or_create_playlist.assert_called_once()

def test_add_to_watch_later(mock_youtube_client, mocker):
    mocker.patch('time.sleep') # Speed up test

    mock_list_request = MagicMock()
    mock_youtube_client.playlistItems().list.return_value = mock_list_request
    # Mock existing items in the playlist (only v2 is in the playlist)
    mock_list_request.execute.return_value = {
        'items': [{'contentDetails': {'videoId': 'v2'}}]
    }
    # Mock list_next to return None to prevent infinite loop
    mock_youtube_client.playlistItems().list_next.return_value = None

    added_count, remaining = auto_watch_later.add_to_watch_later(
        mock_youtube_client,
        [{'id': 'v1'}, {'id': 'v2'}],
        'PL123'
    )

    # v1 added, v2 skipped
    assert added_count == 1
    assert remaining == []
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
    mocker.patch('auto_watch_later.get_channel_videos', return_value=[{'id': 'v1', 'title': 'New Video', 'channel': 'C1'}])

    videos, scan_state = auto_watch_later.get_new_videos_with_shorts_filtering(mock_youtube_client, ['c1'], '2025-01-01Z')

    assert len(videos) == 1
    assert videos[0]['id'] == 'v1'
    assert scan_state['last_channel_index'] == 1

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

def test_has_browser(mocker):
    # Case 1: Browser is available
    mocker.patch('webbrowser.get', return_value=MagicMock())
    assert auto_watch_later._has_browser() is True

    # Case 2: Browser not available
    import webbrowser
    mocker.patch('webbrowser.get', side_effect=webbrowser.Error)
    assert auto_watch_later._has_browser() is False

def test_get_client_credentials_env(mocker):
    mocker.patch.dict('os.environ', {'YOUTUBE_CLIENT_ID': 'env_id', 'YOUTUBE_CLIENT_SECRET': 'env_secret'})
    client_id, client_secret = auto_watch_later._get_client_credentials()
    assert client_id == 'env_id'
    assert client_secret == 'env_secret'

def test_get_client_credentials_file_installed(mocker):
    mocker.patch.dict('os.environ', {}, clear=True)
    mocker.patch('os.path.exists', return_value=True)
    mock_open_func = mock_open(read_data='{"installed": {"client_id": "file_id", "client_secret": "file_secret"}}')
    mocker.patch('builtins.open', mock_open_func)
    
    client_id, client_secret = auto_watch_later._get_client_credentials()
    assert client_id == 'file_id'
    assert client_secret == 'file_secret'

def test_get_client_credentials_file_web(mocker):
    mocker.patch.dict('os.environ', {}, clear=True)
    mocker.patch('os.path.exists', return_value=True)
    mock_open_func = mock_open(read_data='{"web": {"client_id": "file_id_web", "client_secret": "file_secret_web"}}')
    mocker.patch('builtins.open', mock_open_func)
    
    client_id, client_secret = auto_watch_later._get_client_credentials()
    assert client_id == 'file_id_web'
    assert client_secret == 'file_secret_web'

def test_get_client_credentials_file_invalid(mocker):
    mocker.patch.dict('os.environ', {}, clear=True)
    mocker.patch('os.path.exists', return_value=True)
    mock_open_func = mock_open(read_data='{"other": {}}')
    mocker.patch('builtins.open', mock_open_func)
    mocker.patch('sys.exit', side_effect=SystemExit)
    
    with pytest.raises(SystemExit):
        auto_watch_later._get_client_credentials()

def test_get_client_credentials_missing(mocker):
    mocker.patch.dict('os.environ', {}, clear=True)
    mocker.patch('os.path.exists', return_value=False)
    mocker.patch('sys.exit', side_effect=SystemExit)
    
    with pytest.raises(SystemExit):
        auto_watch_later._get_client_credentials()

def test_get_credentials_browser_flow(mocker):
    mock_flow = MagicMock()
    mocker.patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config', return_value=mock_flow)
    mock_flow.run_local_server.return_value = 'browser_creds'
    
    creds = auto_watch_later._get_credentials_browser_flow('id', 'secret')
    assert creds == 'browser_creds'

def test_get_credentials_device_flow_success(mocker):
    # Mock urllib.request.urlopen
    mock_response1 = MagicMock()
    mock_response1.read.return_value = b'{"device_code": "dev_code", "user_code": "user_code", "verification_url": "http://verify", "interval": 1}'
    
    mock_response2 = MagicMock()
    mock_response2.read.return_value = b'{"access_token": "token123", "refresh_token": "refresh123"}'
    
    mocker.patch('urllib.request.urlopen', side_effect=[mock_response1, mock_response2])
    mocker.patch('time.sleep') # do not sleep

    creds = auto_watch_later._get_credentials_device_flow('id', 'secret')
    
    assert creds.token == 'token123'
    assert creds.refresh_token == 'refresh123'
    assert creds.client_id == 'id'
    assert creds.client_secret == 'secret'

def test_get_credentials_device_flow_pending_then_success(mocker):
    import urllib.error
    from io import BytesIO

    mock_response1 = MagicMock()
    mock_response1.read.return_value = b'{"device_code": "dev_code", "user_code": "user_code", "verification_url": "http://verify", "interval": 1}'
    
    # First poll returns authorization_pending error, second returns success
    fp = BytesIO(b'{"error": "authorization_pending"}')
    err = urllib.error.HTTPError('url', 400, 'Bad Request', {}, fp)
    
    mock_response2 = MagicMock()
    mock_response2.read.return_value = b'{"access_token": "token123", "refresh_token": "refresh123"}'
    
    mocker.patch('urllib.request.urlopen', side_effect=[mock_response1, err, mock_response2])
    mocker.patch('time.sleep')

    creds = auto_watch_later._get_credentials_device_flow('id', 'secret')
    assert creds.token == 'token123'

def test_get_credentials_device_flow_slow_down_then_success(mocker):
    import urllib.error
    from io import BytesIO

    mock_response1 = MagicMock()
    mock_response1.read.return_value = b'{"device_code": "dev_code", "user_code": "user_code", "verification_url": "http://verify", "interval": 1}'
    
    # First poll returns slow_down error, second returns success
    fp = BytesIO(b'{"error": "slow_down"}')
    err = urllib.error.HTTPError('url', 400, 'Bad Request', {}, fp)
    
    mock_response2 = MagicMock()
    mock_response2.read.return_value = b'{"access_token": "token123", "refresh_token": "refresh123"}'
    
    mocker.patch('urllib.request.urlopen', side_effect=[mock_response1, err, mock_response2])
    mocker.patch('time.sleep')

    creds = auto_watch_later._get_credentials_device_flow('id', 'secret')
    assert creds.token == 'token123'

def test_get_credentials_device_flow_other_error(mocker):
    import urllib.error
    from io import BytesIO

    mock_response1 = MagicMock()
    mock_response1.read.return_value = b'{"device_code": "dev_code", "user_code": "user_code", "verification_url": "http://verify", "interval": 1}'
    
    # First poll returns access_denied error
    fp = BytesIO(b'{"error": "access_denied"}')
    err = urllib.error.HTTPError('url', 400, 'Bad Request', {}, fp)
    
    mocker.patch('urllib.request.urlopen', side_effect=[mock_response1, err])
    mocker.patch('time.sleep')
    mocker.patch('sys.exit', side_effect=SystemExit)

    with pytest.raises(SystemExit):
        auto_watch_later._get_credentials_device_flow('id', 'secret')

def test_get_new_credentials_browser(mocker):
    mocker.patch('auto_watch_later._get_client_credentials', return_value=('id', 'secret'))
    mocker.patch('auto_watch_later._has_browser', return_value=True)
    mocker.patch('auto_watch_later._get_credentials_browser_flow', return_value='browser_creds')
    
    assert auto_watch_later.get_new_credentials() == 'browser_creds'

def test_get_new_credentials_device(mocker):
    mocker.patch('auto_watch_later._get_client_credentials', return_value=('id', 'secret'))
    mocker.patch('auto_watch_later._has_browser', return_value=False)
    mocker.patch('auto_watch_later._get_credentials_device_flow', return_value='device_creds')
    
    assert auto_watch_later.get_new_credentials() == 'device_creds'

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
    mocker.patch('auto_watch_later.get_playlist_id', return_value='PL123')
    mocker.patch('auto_watch_later.get_subscriptions', return_value=['c1'])
    mocker.patch('auto_watch_later.get_last_check_time', return_value='time')
    mocker.patch('auto_watch_later.get_new_videos_with_shorts_filtering', return_value=([{'id': 'v1', 'title': 'T', 'channel': 'C'}], {'last_channel_index': 1, 'shorts_cache': set()}))
    mocker.patch('auto_watch_later.add_to_watch_later', return_value=(1, []))
    mocker.patch('auto_watch_later.save_check_time')
    mocker.patch('auto_watch_later.load_pending_videos', return_value=[])
    mocker.patch('auto_watch_later.load_scan_progress', return_value=None)

    auto_watch_later.main()

    # Verify core flow steps happened
    auto_watch_later.get_authenticated_service.assert_called()
    auto_watch_later.get_subscriptions.assert_called()
    auto_watch_later.add_to_watch_later.assert_called()
    auto_watch_later.save_check_time.assert_called()

    # Test quota exceeded
    mocker.patch('auto_watch_later.check_quota_usage', return_value=False)
    auto_watch_later.main()

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

def test_env_bool(mocker):
    mocker.patch.dict('os.environ', {'TEST_TRUE': 'true', 'TEST_FALSE': 'false', 'TEST_OTHER': 'maybe'})
    assert auto_watch_later._env_bool('TEST_TRUE', default=False) is True
    assert auto_watch_later._env_bool('TEST_FALSE', default=True) is False
    assert auto_watch_later._env_bool('TEST_OTHER', default=True) is True
    assert auto_watch_later._env_bool('TEST_MISSING', default=False) is False

def test_quota_tracker_and_report(capsys):
    qt = auto_watch_later.QuotaTracker()
    qt.track('playlists.list')
    assert qt.total == 1
    qt.track('playlists.insert')
    assert qt.total == 51
    
    # Check warning on 80% daily quota limit
    for _ in range(160):  # 160 * 50 = 8000
        qt.track('playlists.insert')
    qt.report()
    captured = capsys.readouterr()
    assert "WARNING" in captured.out

def test_subscriptions_cache_loading_and_saving(mocker):
    mocker.patch('os.path.exists', side_effect=lambda path: path == auto_watch_later.SUBSCRIPTIONS_CACHE_FILE)
    
    # 1. Loading successfully
    import json
    cached_data = {
        'cached_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'channel_ids': ['c1', 'c2']
    }
    mocker.patch('builtins.open', mock_open(read_data=json.dumps(cached_data)))
    assert auto_watch_later.load_subscriptions_cache() == ['c1', 'c2']
    
    # 2. Loading expired cache
    expired_cached_data = {
        'cached_at': (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)).isoformat(),
        'channel_ids': ['c1', 'c2']
    }
    mocker.patch('builtins.open', mock_open(read_data=json.dumps(expired_cached_data)))
    assert auto_watch_later.load_subscriptions_cache() is None

    # 3. Loading with JSON decode / other error
    mocker.patch('builtins.open', mock_open(read_data="invalid json"))
    assert auto_watch_later.load_subscriptions_cache() is None
    
    # 4. Save cache
    mock_open_func = mock_open()
    mocker.patch('builtins.open', mock_open_func)
    mocker.patch('os.path.exists', return_value=False)
    auto_watch_later.save_subscriptions_cache(['c1'])
    mock_open_func.assert_called_with(auto_watch_later.SUBSCRIPTIONS_CACHE_FILE, 'w')

def test_fetch_subscriptions_from_api(mock_youtube_client):
    mock_list_request = MagicMock()
    mock_youtube_client.subscriptions().list.return_value = mock_list_request
    mock_list_request.execute.return_value = {
        'items': [{'snippet': {'resourceId': {'channelId': 'c1'}}}]
    }
    mock_youtube_client.subscriptions().list_next.return_value = None
    
    channels = auto_watch_later.fetch_subscriptions_from_api(mock_youtube_client)
    assert channels == ['c1']

def test_get_subscriptions_force_refresh(mock_youtube_client, mocker):
    mocker.patch('auto_watch_later.load_subscriptions_cache', return_value=['c_cached'])
    mocker.patch('auto_watch_later.fetch_subscriptions_from_api', return_value=['c_api'])
    mocker.patch('auto_watch_later.save_subscriptions_cache')
    
    # force_refresh=True
    subs = auto_watch_later.get_subscriptions(mock_youtube_client, force_refresh=True)
    assert subs == ['c_api']
    
    # force_refresh=False
    subs_cached = auto_watch_later.get_subscriptions(mock_youtube_client, force_refresh=False)
    assert subs_cached == ['c_cached']

def test_pending_videos_io(mocker):
    # 1. load_pending_videos file exists
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data='[{"id": "v1"}]'))
    assert auto_watch_later.load_pending_videos() == [{'id': 'v1'}]

    # 2. load_pending_videos read error
    mocker.patch('builtins.open', side_effect=Exception("error"))
    assert auto_watch_later.load_pending_videos() == []

    # 3. save_pending_videos
    mock_open_func = mock_open()
    mocker.patch('builtins.open', mock_open_func)
    mocker.patch('os.replace')
    auto_watch_later.save_pending_videos([{'id': 'v1'}])
    mock_open_func.assert_called_with(auto_watch_later.PENDING_VIDEOS_FILE + '.tmp', 'w')
    
    # 4. clear_pending_videos
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.remove')
    auto_watch_later.clear_pending_videos()
    os.remove.assert_called_with(auto_watch_later.PENDING_VIDEOS_FILE)

def test_scan_progress_io(mocker):
    # 1. load_scan_progress exists
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data='{"last_channel_index": 2, "shorts_cache": ["s1"]}'))
    assert auto_watch_later.load_scan_progress() == {"last_channel_index": 2, "shorts_cache": ["s1"]}

    # 2. load_scan_progress read error
    mocker.patch('builtins.open', side_effect=Exception("error"))
    assert auto_watch_later.load_scan_progress() is None

    # 3. save_scan_progress
    mock_open_func = mock_open()
    mocker.patch('builtins.open', mock_open_func)
    mocker.patch('os.replace')
    auto_watch_later.save_scan_progress(3, {'s2'})
    mock_open_func.assert_called_with(auto_watch_later.SCAN_PROGRESS_FILE + '.tmp', 'w')

    # 4. clear_scan_progress
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.remove')
    auto_watch_later.clear_scan_progress()
    os.remove.assert_called_with(auto_watch_later.SCAN_PROGRESS_FILE)

def test_fetch_playlist_page_cases(mock_youtube_client):
    # Case: Encounter old video -> should return None
    mock_request = MagicMock()
    mock_request.execute.return_value = {
        'items': [{'snippet': {'publishedAt': '2024-01-01T00:00:00Z'}, 'contentDetails': {'videoId': 'old_vid'}}]
    }
    cutoff = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    shorts = set()
    res = auto_watch_later.fetch_playlist_page(mock_youtube_client, mock_request, cutoff, shorts, 50)
    assert res is None
    assert len(shorts) == 0

    # Case: quota error exception
    mock_request.execute.side_effect = Exception("quotaExceeded")
    with pytest.raises(auto_watch_later.QuotaExceededException):
        auto_watch_later.fetch_playlist_page(mock_youtube_client, mock_request, cutoff, shorts, 50)

    # Case: forbidden error exception -> should return None
    mock_request.execute.side_effect = Exception("forbidden")
    res = auto_watch_later.fetch_playlist_page(mock_youtube_client, mock_request, cutoff, shorts, 50)
    assert res is None

def test_get_channel_shorts_video_ids_cases(mock_youtube_client, mocker):
    # Invalid channel ID
    res = auto_watch_later.get_channel_shorts_video_ids(mock_youtube_client, "invalid", "2025-01-01Z")
    assert res == set()
    
    # Exception handling
    mocker.patch('auto_watch_later.get_channel_shorts_playlist_id', return_value='UUSH123')
    mock_youtube_client.playlistItems().list.side_effect = Exception("General Error")
    res = auto_watch_later.get_channel_shorts_video_ids(mock_youtube_client, "UC123", "2025-01-01Z")
    assert res == set()
    
    # QuotaExceededException handling
    mock_youtube_client.playlistItems().list.side_effect = auto_watch_later.QuotaExceededException()
    with pytest.raises(auto_watch_later.QuotaExceededException):
        auto_watch_later.get_channel_shorts_video_ids(mock_youtube_client, "UC123", "2025-01-01Z")

def test_build_shorts_cache_for_channels_cases(mock_youtube_client, mocker):
    # Exception handling in channels loop (should continue to next)
    mocker.patch('auto_watch_later.get_channel_shorts_video_ids', side_effect=[Exception("Error UC1"), {'s2'}])
    res = auto_watch_later.build_shorts_cache_for_channels(mock_youtube_client, ['UC1', 'UC2'], '2025-01-01Z')
    assert res == {'s2'}

    # QuotaExceededException handling (should stop and raise)
    mocker.patch('auto_watch_later.get_channel_shorts_video_ids', side_effect=auto_watch_later.QuotaExceededException())
    with pytest.raises(auto_watch_later.QuotaExceededException):
        auto_watch_later.build_shorts_cache_for_channels(mock_youtube_client, ['UC1'], '2025-01-01Z')

def test_filter_videos_with_options(mocker):
    mocker.patch('auto_watch_later.INCLUDE_SHORTS', True)
    mocker.patch('auto_watch_later.INCLUDE_TEASERS', True)
    
    videos = [
        {'id': 'v_short', 'title': 'Short', 'channel': 'C'},
        {'id': 'v_teaser', 'title': 'Official Teaser', 'channel': 'C'},
        {'id': 'v_normal', 'title': 'Normal', 'channel': 'C'}
    ]
    shorts_cache = {'v_short'}
    
    res = auto_watch_later.filter_videos(videos, shorts_cache)
    assert len(res) == 3

def test_get_videos_from_activities_exception(mock_youtube_client):
    # Quota exceeded exception
    mock_youtube_client.activities().list().execute.side_effect = Exception("quotaExceeded")
    with pytest.raises(auto_watch_later.QuotaExceededException):
        auto_watch_later.get_videos_from_activities(mock_youtube_client, 'UC123', '2025-01-01Z', set())
        
    # Other exception
    mock_youtube_client.activities().list().execute.side_effect = Exception("other")
    res = auto_watch_later.get_videos_from_activities(mock_youtube_client, 'UC123', '2025-01-01Z', set())
    assert res is None

def test_get_videos_from_search_cases(mock_youtube_client):
    # Date formatting + timezone offset handling
    mock_youtube_client.search().list().execute.return_value = {'items': []}
    auto_watch_later.get_videos_from_search(mock_youtube_client, 'UC123', '2025-01-01T00:00:00+00:00', set())
    
    # Quota exceeded exception
    mock_youtube_client.search().list().execute.side_effect = Exception("quotaExceeded")
    with pytest.raises(auto_watch_later.QuotaExceededException):
        auto_watch_later.get_videos_from_search(mock_youtube_client, 'UC123', '2025-01-01Z', set())

    # Other exception
    mock_youtube_client.search().list().execute.side_effect = Exception("other")
    res = auto_watch_later.get_videos_from_search(mock_youtube_client, 'UC123', '2025-01-01Z', set())
    assert res == []

def test_get_new_videos_with_shorts_filtering_resume(mock_youtube_client, mocker):
    mocker.patch('auto_watch_later.get_channel_videos', return_value=[])
    resume = {
        'last_channel_index': 1,
        'shorts_cache': ['s1']
    }
    videos, state = auto_watch_later.get_new_videos_with_shorts_filtering(
        mock_youtube_client, ['c1', 'c2'], '2025-01-01Z', resume_progress=resume
    )
    assert state['last_channel_index'] == 2
    assert 's1' in state['shorts_cache']

def test_get_playlist_id_validation_exception(mock_youtube_client, mocker):
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data="PL_CACHED"))
    
    # Exception during validation list()
    mock_youtube_client.playlists().list.side_effect = Exception("Validation error")
    mocker.patch('auto_watch_later._fetch_or_create_playlist', return_value="PL_NEW")
    
    pid = auto_watch_later.get_playlist_id(mock_youtube_client)
    assert pid == "PL_NEW"

def test_fetch_playlist_video_ids_exception(mock_youtube_client):
    # Quota exceeded exception
    mock_youtube_client.playlistItems().list().execute.side_effect = Exception("quotaExceeded")
    with pytest.raises(auto_watch_later.QuotaExceededException):
        auto_watch_later.fetch_playlist_video_ids(mock_youtube_client, "PL123")
        
    # Other exception (should return empty set)
    mock_youtube_client.playlistItems().list().execute.side_effect = Exception("other")
    res = auto_watch_later.fetch_playlist_video_ids(mock_youtube_client, "PL123")
    assert res == set()

def test_add_to_watch_later_exceptions(mock_youtube_client, mocker):
    mocker.patch('time.sleep')
    mocker.patch('auto_watch_later.fetch_playlist_video_ids', return_value=set())
    
    # 1. QuotaExceededException
    mock_youtube_client.playlistItems().insert().execute.side_effect = Exception("quotaExceeded")
    with pytest.raises(auto_watch_later.QuotaExceededException):
        auto_watch_later.add_to_watch_later(mock_youtube_client, [{'id': 'v1'}], 'PL123')
        
    # 2. videoNotFound exception (should just remove and continue)
    mock_youtube_client.playlistItems().insert().execute.side_effect = Exception("videoNotFound")
    added, remaining = auto_watch_later.add_to_watch_later(mock_youtube_client, [{'id': 'v1'}], 'PL123')
    assert added == 0
    assert remaining == []

    # 3. playlistForbidden exception (should print and continue)
    mock_youtube_client.playlistItems().insert().execute.side_effect = Exception("playlistForbidden")
    added, remaining = auto_watch_later.add_to_watch_later(mock_youtube_client, [{'id': 'v1'}], 'PL123')
    assert added == 0
    assert remaining == [{'id': 'v1'}]

def test_check_quota_usage_other_exception(mock_youtube_client):
    # Non-quota exception -> should return True
    mock_youtube_client.channels().list().execute.side_effect = Exception("Other random error")
    assert auto_watch_later.check_quota_usage(mock_youtube_client) is True

def test_main_resume_and_exception_paths(mocker):
    mocker.patch('auto_watch_later.setup_logging')
    mocker.patch('auto_watch_later.cleanup_logging')
    mocker.patch('auto_watch_later.get_authenticated_service')
    mocker.patch('auto_watch_later.check_quota_usage', return_value=True)
    mocker.patch('auto_watch_later.get_playlist_id', return_value='PL123')
    mocker.patch('auto_watch_later.get_subscriptions', return_value=['c1'])
    mocker.patch('auto_watch_later.get_last_check_time', return_value='time')
    
    # Mock resume scenario
    mocker.patch('auto_watch_later.load_pending_videos', return_value=[{'id': 'v_pending'}])
    mocker.patch('auto_watch_later.load_scan_progress', return_value={'last_channel_index': 0, 'shorts_cache': []})
    mocker.patch('auto_watch_later.add_to_watch_later', return_value=(1, []))
    mocker.patch('auto_watch_later.clear_pending_videos')
    
    mocker.patch('auto_watch_later.get_new_videos_with_shorts_filtering', return_value=([], {'last_channel_index': 1, 'shorts_cache': set()}))
    mocker.patch('auto_watch_later.save_check_time')
    mocker.patch('auto_watch_later.clear_scan_progress')
    
    auto_watch_later.main()
    auto_watch_later.clear_pending_videos.assert_called()

    # Mock QuotaExceededException in main flow
    mocker.patch('auto_watch_later.load_pending_videos', return_value=[])
    mocker.patch('auto_watch_later.load_scan_progress', return_value=None)
    mocker.patch('auto_watch_later.get_new_videos_with_shorts_filtering', side_effect=auto_watch_later.QuotaExceededException())
    mocker.patch('auto_watch_later.save_pending_videos')
    mocker.patch('auto_watch_later.save_scan_progress')
    
    # We trigger QuotaExceededException. Let's make sure it is handled gracefully in main.
    auto_watch_later.main()
    
    # Mock generic Exception in main flow
    mocker.patch('auto_watch_later.get_new_videos_with_shorts_filtering', side_effect=Exception("Generic Error"))
    auto_watch_later.main() # Should catch and log it
