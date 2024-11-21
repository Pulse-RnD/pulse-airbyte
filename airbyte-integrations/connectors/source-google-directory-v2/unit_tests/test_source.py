from unittest.mock import MagicMock, patch
from source_google_directory_v2.source import SourceGoogleDirectoryV2


def test_check_connection(mocker):
    source = SourceGoogleDirectoryV2()
    logger_mock = MagicMock()
    config_mock = {
        "credentials_json": {
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "test",
            "private_key": "test",
            "client_email": "test@test.com",
            "client_id": "test",
            "token_uri": "https://oauth2.googleapis.com/token",  # Added this
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",  # Added this
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"  # Added this
        },
        "admin_email": "test@admin.com"
    }

    # Mock the create_credentials and service
    mock_credentials = MagicMock()
    mock_service = MagicMock()
    mocker.patch.object(source, 'create_credentials', return_value=mock_credentials)
    mocker.patch('source_google_directory_v2.source.build', return_value=mock_service)

    assert source.check_connection(logger_mock, config_mock) == (True, None)


def test_streams(mocker):
    source = SourceGoogleDirectoryV2()
    config_mock = {
        "credentials_json": {
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "test",
            "private_key": "test",
            "client_email": "test@test.com",
            "client_id": "test",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        },
        "admin_email": "test@admin.com"
    }

    # Mock the create_credentials method
    mocker.patch.object(source, 'create_credentials', return_value=MagicMock())
    streams = source.streams(config_mock)
    expected_streams_number = 3
    assert len(streams) == expected_streams_number
