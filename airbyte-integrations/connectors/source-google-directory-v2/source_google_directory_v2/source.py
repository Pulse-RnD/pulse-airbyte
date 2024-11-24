#
# Copyright (c) 2024 Airbyte, Inc., all rights reserved.
#
import json
from abc import ABC
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import pendulum
import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from googleapiclient.discovery import build
from google.oauth2 import service_account


# TODO: Add my_customer constant to the base class

class GoogleDirectoryV2Stream(HttpStream, ABC):
    """Base stream for Google Directory API"""

    """
    This class represents a stream output by the connector.
    This is an abstract base class meant to contain all the common functionality at the API level e.g: the API base URL, pagination strategy,
    parsing responses etc..

    Each stream should extend this class (or another abstract subclass of it) to specify behavior unique to that stream.

    Typically for REST APIs each stream corresponds to a resource in the API. For example if the API
    contains the endpoints
        - GET v1/customers
        - GET v1/employees

    then you should have three classes:
    `class GoogleDirectoryV2Stream(HttpStream, ABC)` which is the current class
    `class Customers(GoogleDirectoryV2Stream)` contains behavior to pull data for customers using v1/customers
    `class Employees(GoogleDirectoryV2Stream)` contains behavior to pull data for employees using v1/employees

    If some streams implement incremental sync, it is typical to create another class
    `class IncrementalGoogleDirectoryV2Stream((GoogleDirectoryV2Stream), ABC)` then have concrete stream implementations extend it. An example
    is provided below.

    See the reference docs for the full list of configurable options.
    """

    url_base = "https://admin.googleapis.com/admin/directory/v1/"

    def __init__(self, credentials: service_account.Credentials):
        super().__init__()
        self.service = build('admin', 'directory_v1', credentials=credentials)

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """
        This method should return a Mapping (e.g: dict) containing whatever information required to make paginated requests. This dict is passed
        to most other methods in this class to help you form headers, request bodies, query params, etc..

        For example, if the API accepts a 'page' parameter to determine which page of the result to return, and a response from the API contains a
        'page' number, then this method should probably return a dict {'page': response.json()['page'] + 1} to increment the page count by 1.
        The request_params method should then read the input next_page_token and set the 'page' param to next_page_token['page'].

        :param response: the most recent response from the API
        :return If there is another page in the result, a mapping (e.g: dict) containing information needed to query the next page in the response.
                If there are no more pages in the result, return None.
        """

        """
        In Airbyte's CDK, there are two main ways to handle pagination:

        Using HttpStream with requests.Response (the default approach)
        Custom pagination using your own logic (which we need for the Google API client)
        
        Since we're using the Google API client library and not making raw HTTP requests,
        we don't need to implement next_page_token with requests.Response
        """
        return None

    def request_params(
            self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        """
        Required by HttpStream but not used since we're using Google API client
        """
        return {}

    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        """
        We still need to implement this method from HttpStream,
        but since we're not using direct HTTP responses, we'll return empty
        """
        yield from []


class Users(GoogleDirectoryV2Stream):
    """
    Stream for Google Workspace Directory Users
    """

    name = "users"
    primary_key = "id"

    def path(self, **kwargs) -> str:
        return "users"  # Required by HttpStream but not actually used

    def read_records(
            self,
            sync_mode: str,
            cursor_field: List[str] = None,
            stream_slice: Mapping[str, Any] = None,
            stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        page_token = None

        while True:
            users_request = self.service.users().list(
                customer='my_customer',
                maxResults=100,
                pageToken=page_token,
                orderBy='email'
            )
            users_response = users_request.execute()

            for user in users_response.get('users', []):
                yield user

            page_token = users_response.get('nextPageToken')
            if not page_token:
                break


class Groups(GoogleDirectoryV2Stream):
    """
    Stream for Google Workspace Groups
    """

    name = "groups"
    primary_key = "id"

    def path(self, **kwargs) -> str:
        return "groups"  # Required by HttpStream but not actually used

    def read_records(
            self,
            sync_mode: str,
            cursor_field: List[str] = None,
            stream_slice: Mapping[str, Any] = None,
            stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        page_token = None

        while True:
            groups_request = self.service.groups().list(
                customer='my_customer',
                maxResults=100,
                pageToken=page_token,
                orderBy='email'
            )
            groups_response = groups_request.execute()

            for group in groups_response.get('groups', []):
                yield group

            page_token = groups_response.get('nextPageToken')
            if not page_token:
                break


class OAuthAppsByUser(GoogleDirectoryV2Stream):
    """
    Stream for OAuth Apps by User and the respective scopes
    """

    name = "oauth_apps_by_user"
    primary_key = "userId"

    def path(self, **kwargs) -> str:
        return f"users/{kwargs['userId']}/tokens"

    def read_records(
            self,
            sync_mode: str,
            cursor_field: List[str] = None,
            stream_slice: Mapping[str, Any] = None,
            stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        user_email = stream_slice.get("userEmail")
        page_token = stream_state.get("pageToken", None)

        while True:
            tokens_request = self.service.tokens().list(
                userKey=user_email,
                pageToken=page_token,
                maxResults=100
            )
            tokens_response = tokens_request.execute()

            oauth_apps = []
            for token in tokens_response.get("items", []):
                app_info = {
                    "appId": token.get("clientId", ""),
                    "appName": token.get("displayText", ""),
                    "scopes": token.get("scopes", []),
                    "anonymous": token.get("anonymous", False),
                    "nativeApp": token.get("nativeApp", False),
                    "issuedTime": token.get("issued", ""),
                    "lastAccessTime": token.get("lastAccessTime", "Never"),
                    "instalationType": "user-specific",
                    "appType": "oauth",
                    "status": None,
                    "etag": None,
                }
                oauth_apps.append(app_info)

            yield {
                "userId": stream_slice.get("userId"),
                "userEmail": stream_slice.get("userEmail"),
                "oauthApps": oauth_apps,
            }

            page_token = tokens_response.get("nextPageToken")
            if not page_token:
                break

            yield from self.update_state(stream_state, "pageToken", page_token)

    def get_updated_state(self, current_stream_state: Mapping[str, Any], latest_record: Mapping[str, Any]) -> Mapping[str, Any]:
        new_state = current_stream_state.copy()
        new_state["pageToken"] = latest_record.get("pageToken")
        return new_state

    def stream_slices(self, **kwargs) -> Iterable[Mapping[str, Any]]:
        users_request = self.service.users().list(
            customer='my_customer',
            maxResults=100,
            orderBy='email'
        )
        users_response = users_request.execute()

        for user in users_response.get('users', []):
            yield {
                "userId": user["id"],
                "userEmail": user["primaryEmail"],
                "pageToken": None # Initialize page token
            }


class IncrementalGoogleDirectoryV2Stream(GoogleDirectoryV2Stream, ABC):
    """Base class for incremental streams in Google Directory"""

    state_checkpoint_interval = 100  # Save state every 100 records

    def get_updated_state(
            self,
            current_stream_state: MutableMapping[str, Any],
            latest_record: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Update the state with the latest cursor value"""
        latest_cursor_value = latest_record.get(self.cursor_field)
        current_state_value = current_stream_state.get(self.cursor_field)

        if latest_cursor_value:
            latest_cursor_dt = pendulum.parse(latest_cursor_value)
            if current_state_value:
                current_state_dt = pendulum.parse(current_state_value)
                return {self.cursor_field: max(latest_cursor_dt, current_state_dt).isoformat()}
            return {self.cursor_field: latest_cursor_dt.isoformat()}

        return current_stream_state


class IncrementalUsers(IncrementalGoogleDirectoryV2Stream):
    """Incremental stream for Users based on creation time"""

    name = "users_incremental"
    primary_key = "id"
    cursor_field = "creationTime"

    def path(self, **kwargs) -> str:
        return "users"

    def read_records(
            self,
            sync_mode: str,
            cursor_field: List[str] = None,
            stream_slice: Mapping[str, Any] = None,
            stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        stream_state = stream_state or {}
        page_token = None

        last_sync = stream_state.get(self.cursor_field, "2000-01-01T00:00:00Z")
        last_sync_date = pendulum.parse(last_sync).format("YYYY-MM-DD")

        while True:
            try:
                request = self.service.users().list(
                    customer='my_customer',
                    maxResults=100,
                    pageToken=page_token,
                    orderBy='email',
                    query=f'creationTime>{last_sync_date}'
                )
                response = request.execute()

                # Since API is already filtering by creationTime,
                # we can directly yield all users in the response
                yield from response.get('users', [])

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            except Exception as e:
                self.logger.error(f"Error fetching users: {str(e)}")
                raise

"""
There isn't even a creationTime field. This means we can't reliably implement incremental sync for Groups since there's no timestamp field to track changes.
"""
# class IncrementalGroups(IncrementalGoogleDirectoryV2Stream):
#     """Incremental stream for Groups"""
#
#     name = "groups_incremental"  # This will show in the UI
#     primary_key = "id"
#     cursor_field = "updated"  # Groups have an 'updated' field we can use
#
#     def path(self, **kwargs) -> str:
#         return "groups"
#
#     def read_records(
#             self,
#             sync_mode: str,
#             cursor_field: List[str] = None,
#             stream_slice: Mapping[str, Any] = None,
#             stream_state: Mapping[str, Any] = None,
#     ) -> Iterable[Mapping[str, Any]]:
#         stream_state = stream_state or {}
#         page_token = None
#
#         # Get the last sync time from state
#         last_sync = stream_state.get(self.cursor_field) or "2000-01-01T00:00:00.000Z"
#
#         while True:
#             request = self.service.groups().list(
#                 customer='my_customer',
#                 maxResults=100,
#                 pageToken=page_token,
#                 orderBy='email',
#                 # Query for groups updated after our last sync
#                 query=f'updated>={last_sync}'
#             )
#             response = request.execute()
#
#             for group in response.get('groups', []):
#                 # Add cursor field if it doesn't exist
#                 group[self.cursor_field] = group.get(self.cursor_field, last_sync)
#                 yield group
#
#             page_token = response.get('nextPageToken')
#             if not page_token:
#                 break


class SourceGoogleDirectoryV2(AbstractSource):
    """
    Google Directory API Source
    """

    @staticmethod
    def create_credentials(config: Mapping[str, Any]) -> service_account.Credentials:
        required_keys = ["credentials_json", "admin_email"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required configuration parameter: {key}")

        try:
            credentials_json = config.get("credentials_json")
            admin_email = config["admin_email"]
            account_info = json.loads(credentials_json)
            creds = service_account.Credentials.from_service_account_info(account_info, scopes=[
                    'https://www.googleapis.com/auth/admin.directory.user.readonly',
                    'https://www.googleapis.com/auth/admin.directory.group.readonly',
                    'https://www.googleapis.com/auth/admin.directory.user.security'
                ])
            creds = creds.with_subject(admin_email)
            return creds
        except ValueError as e:
            raise ValueError(f"Invalid configuration format: {str(e)}")

    def check_connection(self, logger, config) -> Tuple[bool, any]:
        try:
            credentials = self.create_credentials(config)
            service = build('admin', 'directory_v1', credentials=credentials)
            service.users().list(customer='my_customer', maxResults=1, orderBy='email').execute()

            return True, None

        except KeyError as e:
            return False, f"Missing required configuration parameter: {str(e)}"

        except ValueError as e:
            return False, f"Invalid configuration format: {str(e)}"

        except Exception as e:
            error_msg = str(e)
            if "invalid_grant" in error_msg.lower():
                return False, "Invalid credentials or insufficient permissions. Make sure the service account has proper access and admin_email is correct."
            elif "access_denied" in error_msg.lower():
                return False, "Access denied. Check if the service account has the required permissions and admin_email is correct."
            elif "invalid_client" in error_msg.lower():
                return False, "Invalid client configuration. Check your service account credentials."
            else:
                return False, f"Unable to connect to Google Directory API: {error_msg}"

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        try:
            credentials = self.create_credentials(config)
        except ValueError as e:
            raise ValueError(f"Invalid configuration format: {str(e)}")

        return [
            # Regular full refresh streams
            Groups(credentials=credentials),
            Users(credentials=credentials),
            OAuthAppsByUser(credentials=credentials),
            # Incremental streams
            # IncrementalGroups(credentials=credentials),
            IncrementalUsers(credentials=credentials)
        ]
