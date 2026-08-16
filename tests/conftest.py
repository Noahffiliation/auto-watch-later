import pytest
from unittest.mock import MagicMock
import sys
import os

# Add the parent directory to sys.path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def mock_google_auth(mocker):
    """
    Globally mock Google Authentication and API build to prevent
    tests from attempting real authentication, opening the browser,
    or making network calls.
    """
    # Mock InstalledAppFlow to prevent browser opening
    mock_flow = MagicMock()
    mocker.patch(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    )

    # Mock build to prevent real network calls to Google discovery API
    mocker.patch("googleapiclient.discovery.build")

    # Mock time.sleep to make all tests execute instantaneously
    mocker.patch("time.sleep")

    return mock_flow
