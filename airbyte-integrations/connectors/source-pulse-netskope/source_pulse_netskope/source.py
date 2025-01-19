from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from datetime import datetime
import time
import re
import logging
from airbyte_cdk.sources.streams.core import IncrementalMixin, Stream
from airbyte_cdk.sources import AbstractSource
from netskope_api.iterator.netskope_iterator import NetskopeIterator
from netskope_api.iterator.const import Const

logger = logging.getLogger("airbyte")

class NetskopeDataExportStream(Stream, IncrementalMixin):
    primary_key = None
    cursor_field = "timestamp"

    def __init__(
            self,
            event_type: str,
            start_timestamp: int,
            tenant_url: str,
            api_token: str,
    ):
        self.event_type = event_type
        self._start_timestamp = start_timestamp
        self.tenant_url = tenant_url
        self.api_token = api_token
        self.index_name = self._generate_consistent_index_name()

        logger.info(f"Initialized {self.event_type} stream with index name: {self.index_name}")

    @staticmethod
    def _sanitize_tenant_name(tenant_url: str) -> str:
        tenant_name = tenant_url.split('.')[0].lower()
        tenant_name = re.sub(r'[^a-z0-9]', '_', tenant_name)
        tenant_name = re.sub(r'_+', '_', tenant_name)
        tenant_name = tenant_name.strip('_')
        return tenant_name

    def _generate_consistent_index_name(self) -> str:
        tenant_name = self._sanitize_tenant_name(self.tenant_url)
        index_name = f"{tenant_name}_{self.event_type}_index"
        logger.debug(f"Generated consistent index name '{index_name}' from tenant URL '{self.tenant_url}' and event type '{self.event_type}'")
        return index_name

    def get_updated_state(
            self,
            current_stream_state: MutableMapping[str, Any],
            latest_record: Mapping[str, Any]
    ) -> MutableMapping[str, Any]:
        latest_state = current_stream_state or {}
        latest_cursor_value = latest_record.get(self.cursor_field, 0)
        current_cursor_value = latest_state.get(self.cursor_field, 0)

        new_state = {
            "timestamp": max(latest_cursor_value, current_cursor_value),
            "indexname": self.index_name
        }

        logger.debug(f"Updated state for {self.event_type}: {new_state}")
        return new_state

    def stream_slices(
            self,
            sync_mode,
            cursor_field: List[str] = None,
            stream_state: Mapping[str, Any] = None
    ) -> Iterable[Optional[Mapping[str, Any]]]:
        start_time = self._start_timestamp
        if stream_state:
            start_time = stream_state.get("timestamp", self._start_timestamp)

        end_time = int(time.time())

        logger.info(
            f"Creating stream slice for {self.event_type} from "
            f"timestamp {start_time} ({datetime.fromtimestamp(start_time)}) "
            f"to {end_time} ({datetime.fromtimestamp(end_time)})"
        )

        return [{"starttime": start_time, "endtime": end_time}]

    def read_records(
            self,
            sync_mode,
            cursor_field: List[str] = None,
            stream_slice: Mapping[str, Any] = None,
            stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        logger.info(
            f"Reading {self.event_type} records from {stream_slice['starttime']} "
            f"to {stream_slice['endtime']}"
        )

        try:
            params = {
                Const.NSKP_TOKEN: self.api_token,
                Const.NSKP_TENANT_HOSTNAME: self.tenant_url,
                Const.NSKP_EVENT_TYPE: self.event_type,
                Const.NSKP_ITERATOR_NAME: f"airbyte_{self.index_name}",
                "starttime": stream_slice["starttime"],
                "endtime": stream_slice["endtime"]
            }

            iterator = NetskopeIterator(params)
            record_count = 0

            while True:
                response = iterator.next()
                if not response:
                    break

                data = response.json()
                if "result" in data and len(data["result"]) > 0:
                    for record in data["result"]:
                        record_count += 1
                        yield record

                    # Honor the wait time from the API
                    wait_time = data.get("wait_time", 0.2)
                    logger.debug(f"Waiting {wait_time} seconds before next batch")
                    time.sleep(wait_time)
                else:
                    logger.debug("No more data to fetch")
                    break

            logger.info(f"Retrieved {record_count} {self.event_type} records")

        except Exception as e:
            logger.error(f"Error fetching {self.event_type} events: {str(e)}")
            raise

class SourcePulseNetskope(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        try:
            logger.info("Checking connection to Netskope API...")
            params = {
                Const.NSKP_TOKEN: config["token"],
                Const.NSKP_TENANT_HOSTNAME: config["tenant_url"],
                Const.NSKP_EVENT_TYPE: "application",
                Const.NSKP_ITERATOR_NAME: "airbyte_connection_test",
                "starttime": int(time.time()) - 300,  # Last 5 minutes
                "endtime": int(time.time())
            }

            iterator = NetskopeIterator(params)
            response = iterator.next()

            if response and response.status_code == 200:
                logger.info("Successfully connected to Netskope API")
                return True, None
            else:
                return False, "Failed to get response from Netskope API"

        except Exception as e:
            logger.error(f"Failed to connect to Netskope API: {str(e)}")
            return False, str(e)

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        logger.info("Initializing Netskope streams...")

        start_timestamp = config.get("start_timestamp", int(time.time()) - 86400)
        logger.info(f"Using start timestamp: {start_timestamp} ({datetime.fromtimestamp(start_timestamp)})")

        streams = []
        for event_type in ["application", "network", "connection"]:
            stream = NetskopeDataExportStream(
                event_type=event_type,
                start_timestamp=start_timestamp,
                tenant_url=config["tenant_url"],
                api_token=config["token"]
            )
            streams.append(stream)
            logger.info(f"Created stream for {event_type} events with index name {stream.index_name}")

        return streams
