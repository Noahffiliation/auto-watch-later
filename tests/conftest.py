import pytest
from unittest.mock import MagicMock
import sys
import os

# Add the parent directory to sys.path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(autouse=True)
def mock_google_auth(mocker):
    """
    Globally mock Google Authentication flow to prevent
    tests from attempting real authentication or opening the browser.
    """
    # Mock InstalledAppFlow to prevent browser opening
    mock_flow = MagicMock()
    mocker.patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file', return_value=mock_flow)

    # Mock build to prevent API connection attempts
    mocker.patch('googleapiclient.discovery.build')

    # Mock credentials loading to return None or a mock by default if not tailored
    # We don't want to break tests that test loading logic, so we just ensure
    # the FLOW part (which interacts with user/browser) is mocked.
    # The individual tests dealing with load_credentials usually mock it themselves.

    return mock_flow
