import copy
import os
import typing as T

import requests

from util import log


class GooglePlacesAPI:
    HEADERS = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "",
        "X-Goog-FieldMask": "",
    }
    DEFAULT_FIELDS = "places.formattedAddress,places.displayName"

    def __init__(self, api_key) -> None:
        self.api_key = api_key
        self.HEADERS["X-Goog-Api-Key"] = api_key
        self.base_url = "https://places.googleapis.com/v1"

    def search_places(
        self, query: str, fields: T.Optional[T.List[str]] = None
    ) -> T.Dict[T.Any, T.Any]:
        json_data = {
            "textQuery": query,
        }
        headers = copy.deepcopy(self.HEADERS)

        if fields:
            headers["X-Goog-FieldMask"] = ",".join(fields)
        else:
            headers["X-Goog-FieldMask"] = self.DEFAULT_FIELDS

        url = os.path.join(self.base_url, "places:searchText")
        try:
            response = requests.post(url, headers=headers, json=json_data, timeout=10.0).json()
            if not isinstance(response, dict):
                log.print_fail(f"Could not search for {query}")
                log.print_warn(response)
                return {}

            return response
        except Exception as exception:  # pylint: disable=broad-except
            log.print_fail(f"Could not search for {query}")
            log.print_warn(exception)
            return {}
