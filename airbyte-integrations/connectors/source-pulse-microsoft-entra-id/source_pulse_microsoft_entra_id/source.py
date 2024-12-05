from abc import ABC
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple
import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.sources.streams.http.auth import TokenAuthenticator


def get_token(config: Mapping[str, Any]) -> str:
    """Retrieve access token from Microsoft Entra ID"""
    response = requests.post(
        url=f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/v2.0/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "scope": "https://graph.microsoft.com/.default"
        }
    )
    response.raise_for_status()
    return response.json()["access_token"]


class MicrosoftGraphStream(HttpStream, ABC):

    def __init__(self, config: Mapping[str, Any]):
        super().__init__(authenticator=TokenAuthenticator(token=get_token(config)))
        self.config = config
        self._delta_token = None

    url_base = "https://graph.microsoft.com/v1.0/"
    primary_key = "id"

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        json_response = response.json()

        # Check for deltaLink which indicates end of pagination
        if "@odata.deltaLink" in json_response:
            delta_link = json_response["@odata.deltaLink"]
            if "$deltatoken=" in delta_link:
                self._delta_token = delta_link.split("$deltatoken=")[1].split("&")[0]
            return None

        # Check for nextLink which contains skiptoken for pagination
        if "@odata.nextLink" in json_response:
            next_link = json_response["@odata.nextLink"]
            if "$skiptoken=" in next_link:
                skiptoken = next_link.split("$skiptoken=")[1].split("&")[0]
                return {"$skiptoken": skiptoken}

        return None

    def request_params(
            self,
            stream_state: Mapping[str, Any] = None,
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        params = {}

        # If we have a stored delta token in state, use it
        if stream_state and stream_state.get("delta_token"):
            params["$deltatoken"] = stream_state["delta_token"]

        # If we're paginating, add the skiptoken
        if next_page_token:
            params.update(next_page_token)

        return params

    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        json_response = response.json()
        records = json_response.get("value", [])

        for record in records:
            if "@removed" in record:
                record["_ab_cdc_deleted_at"] = True
            yield record

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]) -> Mapping[str, Any]:
        # If we've received a new delta token during sync, update the state
        if self._delta_token:
            return {"delta_token": self._delta_token}
        return current_stream_state or {}


class Users(MicrosoftGraphStream):
    def path(
            self,
            stream_state: Mapping[str, Any] = None,
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "users/delta"


class Groups(MicrosoftGraphStream):
    def path(
            self,
            stream_state: Mapping[str, Any] = None,
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "groups/delta"


class Applications(MicrosoftGraphStream):
    def path(
            self,
            stream_state: Mapping[str, Any] = None,
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "applications/delta"


class SourcePulseMicrosoftEntraId(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        try:
            token = get_token(config)
            url = f"{MicrosoftGraphStream.url_base}/users/delta"
            response = requests.get(
                url=url,
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return True, None
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        return [
            Users(config),
            Groups(config),
            Applications(config)
        ]
